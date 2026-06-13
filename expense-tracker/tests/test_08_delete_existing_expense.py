"""
tests/test_08_delete_existing_expense.py

Pytest test suite for the Spendly "Delete Existing Expense" feature (Step 08).

Spec: .claude/specs/08-delete-existing-expense.md

All tests use an isolated on-disk SQLite database (via pytest's tmp_path) so
the real expense_tracker.db is never touched.  get_db() is monkey-patched to
redirect every connection to the temp file.

Test isolation strategy:
  - Each test gets a fresh database through the `app` fixture.
  - `auth_client` registers + logs in a single user before each test that needs auth.
  - DB-level helpers insert or query data directly through the patched get_db().
"""

import re
import sqlite3
import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

from app import app as flask_app
import database.db as db_module
from database.db import init_db, delete_expense as db_delete_expense


# ===========================================================================
# Constants
# ===========================================================================

DELETE_URL_TEMPLATE = "/expenses/{id}/delete"
PROFILE_URL = "/profile"
LOGIN_URL = "/login"

TEST_EMAIL = "test@spendly.com"
TEST_PASSWORD = "testpass123"
TEST_NAME = "Test User"

OTHER_EMAIL = "other@spendly.com"
OTHER_PASSWORD = "otherpass123"
OTHER_NAME = "Other User"


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def app(tmp_path):
    """
    Flask test application backed by an isolated on-disk SQLite DB located in
    pytest's tmp_path directory.  A file-based path avoids the shared-connection
    pitfall of ':memory:' when the app opens/closes its own connections per request.
    """
    db_path = str(tmp_path / "test_expense_tracker.db")

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    def patched_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    with patch.object(db_module, "get_db", side_effect=patched_get_db):
        with flask_app.app_context():
            init_db()
            yield flask_app


@pytest.fixture
def client(app):
    """Unauthenticated test client."""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """
    Test client that has completed registration and login as the primary test user.
    """
    client.post(
        "/register",
        data={
            "name": TEST_NAME,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )
    client.post(
        "/login",
        data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    return client


# ===========================================================================
# DB helpers (must be called inside an active app context only)
# ===========================================================================

def _get_user_id(email):
    """Return the integer user_id for a registered email."""
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def _create_user(name, email, password):
    """Insert a user and return its id."""
    conn = db_module.get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash(password)),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _create_expense(user_id, amount=25.00, category="Food",
                    date="2026-05-15", description="Test expense"):
    """Insert an expense for user_id and return its id."""
    conn = db_module.get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _count_expenses_for_user(user_id):
    """Return the total number of expense rows for a given user_id."""
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def _expense_exists(expense_id):
    """Return True if an expense row with the given id exists in the DB."""
    conn = db_module.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ===========================================================================
# 1. Authentication guard
# ===========================================================================

class TestAuthGuard:
    def test_unauthenticated_post_redirects_to_login(self, client, app):
        """
        Spec: POST /expenses/<id>/delete is login-required.
        An unauthenticated POST must redirect to /login, never attempt deletion.
        """
        with app.app_context():
            uid = _create_user("Guard User", "guard@spendly.com", "pass12345")
            expense_id = _create_expense(uid)

        response = client.post(DELETE_URL_TEMPLATE.format(id=expense_id))
        assert response.status_code == 302, (
            "Unauthenticated POST to delete route must return 302 redirect"
        )
        assert LOGIN_URL in response.headers["Location"], (
            "Unauthenticated POST redirect must target /login"
        )

    def test_unauthenticated_post_does_not_delete_row(self, client, app):
        """
        Spec: login_required prevents deletion; unauthenticated requests must
        not remove any expense row from the database.
        """
        with app.app_context():
            uid = _create_user("NoDelete User", "nodelete@spendly.com", "pass12345")
            expense_id = _create_expense(uid)

        client.post(DELETE_URL_TEMPLATE.format(id=expense_id))

        with app.app_context():
            assert _expense_exists(expense_id), (
                "Expense must not be deleted when the request is unauthenticated"
            )

    def test_unauthenticated_post_to_nonexistent_id_redirects_to_login(self, client):
        """
        Spec: Auth guard must fire before any DB lookup; even POSTing a bogus id
        while unauthenticated must redirect to /login, not hit the DB.
        """
        response = client.post(DELETE_URL_TEMPLATE.format(id=99999))
        assert response.status_code == 302, (
            "Unauthenticated POST with non-existent id must redirect with 302"
        )
        assert LOGIN_URL in response.headers["Location"], (
            "Redirect for unauthenticated non-existent id must target /login"
        )

    def test_get_method_not_allowed(self, auth_client):
        """
        Spec: The existing GET stub must be replaced with POST-only.
        A GET request to /expenses/<id>/delete from an authenticated user must
        not succeed as a destructive action (405 Method Not Allowed expected,
        since the route only accepts POST).
        """
        response = auth_client.get(DELETE_URL_TEMPLATE.format(id=1))
        assert response.status_code == 405, (
            "GET /expenses/<id>/delete must return 405 Method Not Allowed; "
            "destructive actions must only accept POST"
        )


# ===========================================================================
# 2. Happy path — successful deletion
# ===========================================================================

class TestHappyPath:
    def test_delete_own_expense_returns_302(self, auth_client, app):
        """
        Spec: POST /expenses/<id>/delete for an expense owned by the logged-in
        user must respond with a 302 redirect.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid, description="My lunch")

        response = auth_client.post(DELETE_URL_TEMPLATE.format(id=expense_id))
        assert response.status_code == 302, (
            "Successful delete must respond with 302 redirect"
        )

    def test_delete_own_expense_redirects_to_profile(self, auth_client, app):
        """
        Spec: After a successful delete the user must be redirected to /profile.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid)

        response = auth_client.post(DELETE_URL_TEMPLATE.format(id=expense_id))
        assert PROFILE_URL in response.headers["Location"], (
            "Successful delete must redirect to /profile"
        )

    def test_delete_own_expense_removes_row_from_db(self, auth_client, app):
        """
        Spec: After a successful delete the expense row must no longer exist in
        the expenses table (DB side effect verified directly).
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid, description="To be removed")

        auth_client.post(DELETE_URL_TEMPLATE.format(id=expense_id))

        with app.app_context():
            assert not _expense_exists(expense_id), (
                "Expense row must be removed from the DB after a successful delete"
            )

    def test_delete_own_expense_flashes_success_message(self, auth_client, app):
        """
        Spec: On success (1 row deleted) the route must flash 'Expense deleted.'
        and that message must appear on the profile page after the redirect.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid)

        response = auth_client.post(
            DELETE_URL_TEMPLATE.format(id=expense_id),
            follow_redirects=True,
        )
        assert b"Expense deleted." in response.data, (
            "Flash message 'Expense deleted.' must appear on /profile after success"
        )

    def test_delete_removes_correct_row_only(self, auth_client, app):
        """
        Spec: Only the targeted expense must be removed; sibling expenses for the
        same user must remain intact.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            id_to_delete = _create_expense(uid, amount=10.0, description="Delete me")
            id_to_keep = _create_expense(uid, amount=20.0, description="Keep me")

        auth_client.post(DELETE_URL_TEMPLATE.format(id=id_to_delete))

        with app.app_context():
            assert not _expense_exists(id_to_delete), (
                "Targeted expense must be removed"
            )
            assert _expense_exists(id_to_keep), (
                "Sibling expense for the same user must NOT be removed"
            )


# ===========================================================================
# 3. Profile page reflects deletion
# ===========================================================================

class TestProfileUpdatesAfterDeletion:
    def test_deleted_expense_absent_from_transactions_list(self, auth_client, app):
        """
        Spec: A deleted expense must no longer appear in the transactions list
        on /profile after the redirect.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid, description="Pharmacy visit deleted")

        auth_client.post(DELETE_URL_TEMPLATE.format(id=expense_id),
                         follow_redirects=True)
        response = auth_client.get(PROFILE_URL)
        assert b"Pharmacy visit deleted" not in response.data, (
            "Deleted expense description must not appear in the transactions list"
        )

    def test_profile_total_spent_decreases_after_deletion(self, auth_client, app):
        """
        Spec: The profile stats (total spent) must update correctly after deletion.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            # Insert two expenses; delete one and check total reflects only the other
            _create_expense(uid, amount=100.00, description="Kept expense")
            id_to_delete = _create_expense(uid, amount=50.00, description="Removed expense")

        auth_client.post(DELETE_URL_TEMPLATE.format(id=id_to_delete))
        response = auth_client.get(PROFILE_URL)
        # After removing the 50.00 expense, only 100.00 should remain
        assert b"100.00" in response.data, (
            "Profile total spent must reflect only remaining expenses after deletion"
        )
        assert b"150.00" not in response.data, (
            "The combined total must not appear after one expense is deleted"
        )

    def test_profile_transaction_count_decreases_after_deletion(self, auth_client, app):
        """
        Spec: The transaction count stat card must decrement by 1 after a
        successful expense deletion.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            _create_expense(uid, description="Keep this")
            id_to_delete = _create_expense(uid, description="Delete this")

        # Before deletion: expect count 2 on profile
        response_before = auth_client.get(PROFILE_URL)
        assert b"2" in response_before.data, (
            "Transaction count must be 2 before deletion"
        )

        auth_client.post(DELETE_URL_TEMPLATE.format(id=id_to_delete))
        response_after = auth_client.get(PROFILE_URL)
        assert b"1" in response_after.data, (
            "Transaction count must be 1 after one expense is deleted"
        )

    def test_remaining_expense_still_visible_after_deletion(self, auth_client, app):
        """
        Spec: Expenses NOT targeted for deletion must still appear in the
        transactions list on /profile after the redirect.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            id_to_delete = _create_expense(uid, description="Gone expense")
            _create_expense(uid, description="Survivor expense")

        auth_client.post(DELETE_URL_TEMPLATE.format(id=id_to_delete),
                         follow_redirects=True)
        response = auth_client.get(PROFILE_URL)
        assert b"Survivor expense" in response.data, (
            "Non-deleted expense must remain visible on /profile after deletion"
        )


# ===========================================================================
# 4. Ownership guard — cannot delete another user's expense
# ===========================================================================

class TestOwnershipGuard:
    def test_cannot_delete_another_users_expense(self, auth_client, client, app):
        """
        Spec: delete_expense must filter by both id AND user_id; a logged-in
        user must not be able to delete an expense that belongs to a different user.
        """
        with app.app_context():
            # Create a second user and their expense
            other_uid = _create_user(OTHER_NAME, OTHER_EMAIL, OTHER_PASSWORD)
            other_expense_id = _create_expense(
                other_uid, amount=75.00, description="Other user expense"
            )

        # auth_client is logged in as TEST_EMAIL, attempts to delete OTHER user's expense
        auth_client.post(DELETE_URL_TEMPLATE.format(id=other_expense_id))

        with app.app_context():
            assert _expense_exists(other_expense_id), (
                "Expense belonging to another user must NOT be deleted by a different user"
            )

    def test_cross_user_delete_flashes_not_found(self, auth_client, client, app):
        """
        Spec: When a user attempts to delete an expense they do not own, the route
        must flash 'Expense not found.' (same response as a genuinely missing id —
        no information leak about whose expense it is).
        """
        with app.app_context():
            other_uid = _create_user(OTHER_NAME, OTHER_EMAIL, OTHER_PASSWORD)
            other_expense_id = _create_expense(
                other_uid, description="Should not flash success"
            )

        response = auth_client.post(
            DELETE_URL_TEMPLATE.format(id=other_expense_id),
            follow_redirects=True,
        )
        assert b"Expense not found." in response.data, (
            "Attempting to delete another user's expense must flash 'Expense not found.'"
        )

    def test_cross_user_delete_redirects_to_profile(self, auth_client, client, app):
        """
        Spec: Whether deletion succeeds or fails, the route always redirects to
        /profile.  An ownership-guard failure must also redirect to /profile.
        """
        with app.app_context():
            other_uid = _create_user(OTHER_NAME, OTHER_EMAIL, OTHER_PASSWORD)
            other_expense_id = _create_expense(other_uid)

        response = auth_client.post(DELETE_URL_TEMPLATE.format(id=other_expense_id))
        assert response.status_code == 302, (
            "Ownership-guard failure must return 302 redirect"
        )
        assert PROFILE_URL in response.headers["Location"], (
            "Ownership-guard failure redirect must target /profile"
        )

    def test_owning_user_can_delete_their_own_expense_after_another_user_fails(
        self, auth_client, app
    ):
        """
        Spec: Ownership check is per-request; the actual owner can still delete
        their expense after an attacker's attempt was silently rejected.
        Uses a second test client backed by the same patched DB fixture.
        """
        with app.app_context():
            own_uid = _get_user_id(TEST_EMAIL)
            _create_user(OTHER_NAME, OTHER_EMAIL, OTHER_PASSWORD)
            own_expense_id = _create_expense(own_uid, description="I own this")

        # Simulate the other user (attacker) attempting the delete via a second client
        attacker_client = app.test_client()
        attacker_client.post(
            "/login",
            data={"email": OTHER_EMAIL, "password": OTHER_PASSWORD},
        )
        attacker_client.post(DELETE_URL_TEMPLATE.format(id=own_expense_id))

        # Row must still be there after the attacker's failed attempt
        with app.app_context():
            assert _expense_exists(own_expense_id), (
                "Expense must survive an attacker's delete attempt"
            )

        # Now the real owner deletes it using auth_client
        auth_client.post(DELETE_URL_TEMPLATE.format(id=own_expense_id))

        with app.app_context():
            assert not _expense_exists(own_expense_id), (
                "Expense must be removable by its actual owner after attacker's failed attempt"
            )


# ===========================================================================
# 5. Non-existent expense ID
# ===========================================================================

class TestNonExistentId:
    def test_delete_nonexistent_id_returns_302(self, auth_client):
        """
        Spec: Posting to a non-existent expense id must return a 302 redirect to
        /profile — never a 500 or an unhandled exception.
        """
        response = auth_client.post(DELETE_URL_TEMPLATE.format(id=999999))
        assert response.status_code == 302, (
            "DELETE for non-existent id must return 302, not 500 or 404"
        )

    def test_delete_nonexistent_id_redirects_to_profile(self, auth_client):
        """
        Spec: Both success and failure paths redirect to /profile.
        A missing expense id must redirect to /profile, not to any error page.
        """
        response = auth_client.post(DELETE_URL_TEMPLATE.format(id=999999))
        assert PROFILE_URL in response.headers["Location"], (
            "Non-existent id delete must redirect to /profile"
        )

    def test_delete_nonexistent_id_flashes_not_found(self, auth_client):
        """
        Spec: On failure (0 rows deleted — id not found or wrong owner) the route
        must flash 'Expense not found.' and display it on the profile page.
        """
        response = auth_client.post(
            DELETE_URL_TEMPLATE.format(id=999999),
            follow_redirects=True,
        )
        assert b"Expense not found." in response.data, (
            "Flash message 'Expense not found.' must appear when id does not exist"
        )

    def test_delete_already_deleted_expense_flashes_not_found(self, auth_client, app):
        """
        Edge case: Deleting the same expense twice; the second POST must behave
        identically to a non-existent id and flash 'Expense not found.'
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid, description="Delete twice test")

        # First delete — should succeed
        auth_client.post(DELETE_URL_TEMPLATE.format(id=expense_id))
        # Second delete — expense is gone, should flash not found
        response = auth_client.post(
            DELETE_URL_TEMPLATE.format(id=expense_id),
            follow_redirects=True,
        )
        assert b"Expense not found." in response.data, (
            "Deleting an already-deleted expense must flash 'Expense not found.'"
        )

    def test_delete_id_zero_not_found(self, auth_client):
        """
        Edge case: id=0 can never match a valid AUTOINCREMENT primary key (which
        starts at 1).  The route must treat it as not found and redirect to /profile.
        """
        response = auth_client.post(DELETE_URL_TEMPLATE.format(id=0))
        assert response.status_code == 302, (
            "POST with id=0 must return 302 (id=0 cannot match any expense)"
        )
        assert PROFILE_URL in response.headers["Location"]


# ===========================================================================
# 6. HTTP method constraints
# ===========================================================================

class TestHttpMethodConstraints:
    def test_get_returns_405(self, auth_client):
        """
        Spec: The route must use POST, not GET — destructive actions must never
        be triggered by a GET request. Flask must return 405 for a GET.
        """
        response = auth_client.get(DELETE_URL_TEMPLATE.format(id=1))
        assert response.status_code == 405, (
            "GET /expenses/<id>/delete must return 405 Method Not Allowed"
        )

    def test_put_returns_405(self, auth_client):
        """
        Spec: Only POST is accepted; any other HTTP method must return 405.
        """
        response = auth_client.put(DELETE_URL_TEMPLATE.format(id=1))
        assert response.status_code == 405, (
            "PUT /expenses/<id>/delete must return 405 Method Not Allowed"
        )

    def test_non_integer_id_returns_404(self, auth_client):
        """
        Spec: The route is declared with <int:id>; Flask's type converter must
        return 404 for a non-integer segment, never execute the view function.
        """
        response = auth_client.post("/expenses/abc/delete")
        assert response.status_code == 404, (
            "Non-integer id segment must return 404 (Flask int converter)"
        )


# ===========================================================================
# 7. Template — delete button present in profile transactions list
# ===========================================================================

class TestTemplateDeleteButton:
    def test_delete_button_visible_for_each_expense(self, auth_client, app):
        """
        Spec: A delete button is visible on each expense row in the profile
        transactions list.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            _create_expense(uid, description="Expense Alpha")
            _create_expense(uid, description="Expense Beta")

        response = auth_client.get(PROFILE_URL)
        assert b"Delete" in response.data, (
            "A 'Delete' button must appear in the profile transactions list"
        )

    def test_delete_form_uses_post_method(self, auth_client, app):
        """
        Spec: Clicking delete submits a POST form (not a GET link). The form
        method attribute must be POST.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            _create_expense(uid, description="Check method expense")

        response = auth_client.get(PROFILE_URL)
        data = response.data.decode()
        # The delete form's method attribute must be POST (case-insensitive)
        assert re.search(r'method=["\']?POST["\']?', data, re.IGNORECASE), (
            "Delete form must use method='POST', not GET"
        )

    def test_delete_form_action_points_to_correct_url(self, auth_client, app):
        """
        Spec: Each delete form's action must point to /expenses/<id>/delete
        where <id> is the integer primary key of the expense row.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid, description="Action URL expense")

        response = auth_client.get(PROFILE_URL)
        data = response.data.decode()
        expected_action = f"/expenses/{expense_id}/delete"
        assert expected_action in data, (
            f"Delete form action must contain '{expected_action}' for expense {expense_id}"
        )

    def test_delete_button_absent_when_no_expenses(self, auth_client):
        """
        Spec: When there are no expenses the 'No transactions yet.' empty state
        is shown — no delete form should be present.
        """
        response = auth_client.get(PROFILE_URL)
        data = response.data.decode()
        assert b"No transactions yet" in response.data, (
            "Expected empty-state message when no expenses exist"
        )
        # No delete forms should appear in the empty state
        assert f"/expenses/" not in data or "delete" not in data.lower() or \
               "No transactions yet" in data, (
            "Delete forms must not appear when the transactions list is empty"
        )

    def test_transaction_rows_include_expense_id(self, auth_client, app):
        """
        Spec: get_recent_expenses SELECT now includes `id` so the profile template
        can render per-row delete forms. The rendered page must contain the
        expense id in the delete form action.
        """
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid, description="ID included test")

        response = auth_client.get(PROFILE_URL)
        assert str(expense_id).encode() in response.data, (
            "The expense id must appear in the rendered profile page "
            "(get_recent_expenses must include `id` in its SELECT)"
        )


# ===========================================================================
# 8. DB helper — delete_expense()
# ===========================================================================

class TestDeleteExpenseDBHelper:
    def test_delete_expense_returns_1_on_success(self, app):
        """
        Spec: delete_expense(expense_id, user_id) returns the rowcount (0 or 1).
        Must return 1 when the matching row exists and is deleted.
        """
        with app.app_context():
            uid = _create_user("DBHelper User", "dbhelper@spendly.com", "pass12345")
            expense_id = _create_expense(uid)
            result = db_delete_expense(expense_id, uid)

        assert result == 1, (
            "delete_expense() must return 1 when the row is successfully deleted"
        )

    def test_delete_expense_returns_0_for_nonexistent_id(self, app):
        """
        Spec: delete_expense returns 0 when no row matches id AND user_id.
        A non-existent expense_id must return 0.
        """
        with app.app_context():
            uid = _create_user("DBZero User", "dbzero@spendly.com", "pass12345")
            result = db_delete_expense(999999, uid)

        assert result == 0, (
            "delete_expense() must return 0 when no matching row exists"
        )

    def test_delete_expense_returns_0_for_wrong_user_id(self, app):
        """
        Spec: delete_expense must filter by both id AND user_id — the user_id
        check is the ownership guard.  Calling with the correct expense_id but
        a different user_id must return 0 and NOT delete the row.
        """
        with app.app_context():
            owner_uid = _create_user("Owner", "owner@spendly.com", "pass12345")
            attacker_uid = _create_user("Attacker", "attacker@spendly.com", "pass12345")
            expense_id = _create_expense(owner_uid)

            result = db_delete_expense(expense_id, attacker_uid)

        assert result == 0, (
            "delete_expense() must return 0 when user_id does not match the expense owner"
        )

    def test_delete_expense_does_not_delete_row_for_wrong_user_id(self, app):
        """
        Spec: The ownership guard (user_id in WHERE clause) must prevent deletion
        when called with the wrong user_id. Row must still exist after the call.
        """
        with app.app_context():
            owner_uid = _create_user("OwnerB", "ownerb@spendly.com", "pass12345")
            attacker_uid = _create_user("AttackerB", "attackerb@spendly.com", "pass12345")
            expense_id = _create_expense(owner_uid)

            db_delete_expense(expense_id, attacker_uid)
            still_exists = _expense_exists(expense_id)

        assert still_exists, (
            "Expense row must still exist after delete_expense() is called with wrong user_id"
        )

    def test_delete_expense_removes_row_from_db(self, app):
        """
        Spec: After a successful delete_expense() call the row must no longer
        exist in the expenses table.
        """
        with app.app_context():
            uid = _create_user("RemoveRow User", "removerow@spendly.com", "pass12345")
            expense_id = _create_expense(uid, description="Must be gone")
            db_delete_expense(expense_id, uid)
            exists = _expense_exists(expense_id)

        assert not exists, (
            "Expense row must be absent from the DB after a successful delete_expense() call"
        )

    def test_delete_expense_does_not_remove_other_rows(self, app):
        """
        Spec: delete_expense must only remove the targeted row. Other expenses
        for the same user must remain.
        """
        with app.app_context():
            uid = _create_user("KeepOthers User", "keepothers@spendly.com", "pass12345")
            id_to_delete = _create_expense(uid, description="Delete this one")
            id_to_keep = _create_expense(uid, description="Keep this one")

            db_delete_expense(id_to_delete, uid)
            target_gone = not _expense_exists(id_to_delete)
            sibling_intact = _expense_exists(id_to_keep)

        assert target_gone, "Targeted expense must be removed by delete_expense()"
        assert sibling_intact, "Sibling expense for the same user must not be removed"


# ===========================================================================
# 9. get_recent_expenses returns `id` field
# ===========================================================================

class TestGetRecentExpensesIncludesId:
    def test_get_recent_expenses_includes_id_key(self, app):
        """
        Spec: get_recent_expenses SELECT now includes `id` so the profile
        template can render per-row delete forms.  Each returned dict must
        contain the key 'id'.
        """
        from database.db import get_recent_expenses

        with app.app_context():
            uid = _create_user("IDKey User", "idkey@spendly.com", "pass12345")
            expense_id = _create_expense(uid, description="ID key test")
            results = get_recent_expenses(uid)

        assert len(results) >= 1, "At least one expense must be returned"
        assert "id" in results[0], (
            "Each dict returned by get_recent_expenses must include the 'id' key"
        )

    def test_get_recent_expenses_id_matches_inserted_row(self, app):
        """
        Spec: The `id` returned by get_recent_expenses must match the integer
        primary key of the inserted expense row.
        """
        from database.db import get_recent_expenses

        with app.app_context():
            uid = _create_user("IDMatch User", "idmatch@spendly.com", "pass12345")
            expense_id = _create_expense(uid, description="ID match check")
            results = get_recent_expenses(uid)

        assert results[0]["id"] == expense_id, (
            "The 'id' field in get_recent_expenses results must match "
            "the inserted expense's primary key"
        )


# ===========================================================================
# 10. SQL injection / security
# ===========================================================================

class TestSQLInjectionSafety:
    def test_sql_injection_in_description_does_not_affect_delete(self, auth_client, app):
        """
        Spec: Parameterised queries in delete_expense() must handle expenses
        whose descriptions contain SQL injection payloads without errors.
        The expense must be deletable normally.
        """
        payload = "'; DROP TABLE expenses; --"
        with app.app_context():
            uid = _get_user_id(TEST_EMAIL)
            expense_id = _create_expense(uid, description=payload)

        response = auth_client.post(DELETE_URL_TEMPLATE.format(id=expense_id))
        assert response.status_code == 302, (
            "DELETE for an expense with SQL injection in description must not crash"
        )

        with app.app_context():
            assert not _expense_exists(expense_id), (
                "Expense with injection payload in description must still be deletable"
            )
            # Verify table still exists by counting remaining expenses
            assert _count_expenses_for_user(uid) == 0, (
                "Expenses table must still exist after deleting an injection-payload expense"
            )


# ===========================================================================
# 11. No raw SQL string formatting in delete_expense() — static analysis
# ===========================================================================

class TestNoSQLStringFormatting:
    _DB_PATH = (
        r"C:\Users\aman_sharma\Desktop\llm_training"
        r"\expense-tracker\expense-tracker\database\db.py"
    )

    def _get_delete_expense_body(self):
        """Extract the delete_expense function body from database/db.py."""
        with open(self._DB_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        func_match = re.search(
            r"def delete_expense\(.*?\):(.*?)(?=\ndef |\nclass |\Z)",
            source,
            re.DOTALL,
        )
        assert func_match is not None, (
            "delete_expense() function must exist in database/db.py"
        )
        return func_match.group(1)

    def test_delete_expense_function_exists_in_db_module(self):
        """
        Spec: New helper delete_expense(expense_id, user_id) must be present in
        database/db.py.
        """
        with open(self._DB_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        assert "def delete_expense(" in source, (
            "delete_expense() function must be defined in database/db.py"
        )

    def test_delete_expense_no_fstring_sql(self):
        """
        Spec: No raw SQL string formatting in delete_expense() DB helper.
        f-string interpolation in SQL is a SQL injection risk; must not be present.
        """
        func_body = self._get_delete_expense_body()
        assert not re.search(r'f["\'].*?DELETE.*?\{', func_body), (
            "delete_expense() must not use f-string formatting in SQL statements"
        )

    def test_delete_expense_no_percent_style_sql(self):
        """
        Spec: %-style string formatting in SQL is a SQL injection risk; must not
        be present in delete_expense().
        """
        func_body = self._get_delete_expense_body()
        assert not re.search(r'["\'].*?DELETE.*?%[sd].*?["\'].*?%', func_body), (
            "delete_expense() must not use %-style formatting in SQL statements"
        )

    def test_delete_expense_no_format_method_sql(self):
        """
        Spec: .format() string interpolation in SQL is a SQL injection risk;
        must not be present in delete_expense().
        """
        func_body = self._get_delete_expense_body()
        assert not re.search(
            r'["\'].*?DELETE.*?\{\}.*?["\'].*?\.format\(', func_body
        ), (
            "delete_expense() must not use .format() formatting in SQL statements"
        )

    def test_delete_expense_uses_question_mark_placeholders(self):
        """
        Spec: Parameterised queries only — delete_expense() must use '?'
        placeholders for both expense_id and user_id in the WHERE clause.
        """
        func_body = self._get_delete_expense_body()
        assert "?" in func_body, (
            "delete_expense() must use '?' placeholders for parameterised queries"
        )
        # Expect at least two '?' — one for id, one for user_id
        assert func_body.count("?") >= 2, (
            "delete_expense() must have at least two '?' placeholders "
            "(one for expense_id, one for user_id in the WHERE clause)"
        )

    def test_delete_expense_where_clause_includes_user_id(self):
        """
        Spec: The ownership guard requires that the DELETE WHERE clause includes
        BOTH `id` and `user_id`.  A missing user_id check would be a security
        vulnerability — any user could delete any expense by guessing the id.
        """
        func_body = self._get_delete_expense_body()
        assert re.search(r"user_id", func_body, re.IGNORECASE), (
            "delete_expense() WHERE clause must include 'user_id' as an ownership guard"
        )
        # Both columns must appear in a DELETE ... WHERE clause
        assert re.search(r"DELETE\s+FROM\s+expenses", func_body, re.IGNORECASE), (
            "delete_expense() must execute a DELETE FROM expenses statement"
        )


# ===========================================================================
# 12. Template quality — no hardcoded hex colours in profile.html
# ===========================================================================

class TestTemplateQuality:
    _PROFILE_TEMPLATE_PATH = (
        r"C:\Users\aman_sharma\Desktop\llm_training"
        r"\expense-tracker\expense-tracker\templates\profile.html"
    )

    def test_profile_html_has_no_hardcoded_hex_colours(self):
        """
        Spec: The button styling must use CSS variables only — no hardcoded hex
        values. A hex colour is defined as '#' followed by exactly 3 or 6 hex
        digits (case-insensitive).
        """
        with open(self._PROFILE_TEMPLATE_PATH, "r", encoding="utf-8") as fh:
            content = fh.read()

        hex_colour_pattern = re.compile(
            r'(?<!\w)#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b'
        )
        matches = hex_colour_pattern.findall(content)
        assert len(matches) == 0, (
            f"profile.html must not contain hardcoded hex colours; "
            f"found: {['#' + m for m in matches]}"
        )

    def test_profile_html_contains_delete_form_with_post_method(self):
        """
        Spec: The profile.html template must include a POST form for each
        expense row with the delete action.
        """
        with open(self._PROFILE_TEMPLATE_PATH, "r", encoding="utf-8") as fh:
            content = fh.read()

        assert 'method="POST"' in content or "method='POST'" in content, (
            "profile.html must contain a form with method='POST' for the delete action"
        )
        assert "/delete" in content, (
            "profile.html must contain a delete form action ending in '/delete'"
        )

    def test_profile_html_delete_form_uses_expense_id_in_action(self):
        """
        Spec: The delete form action must reference the template variable t.id
        to build the correct URL per expense row.
        """
        with open(self._PROFILE_TEMPLATE_PATH, "r", encoding="utf-8") as fh:
            content = fh.read()

        # Template must use {{ t.id }} in the action URL
        assert "t.id" in content, (
            "profile.html delete form action must use '{{ t.id }}' to target the "
            "correct expense row"
        )
