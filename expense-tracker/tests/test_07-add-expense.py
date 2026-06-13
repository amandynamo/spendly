"""
tests/test_07-add-expense.py

Pytest test suite for the Spendly "Add Expense" feature (Step 07).

Spec: .claude/specs/07-add-expense.md

All tests use an isolated on-disk SQLite database (via pytest's tmp_path) so
the real expense_tracker.db is never touched.  get_db() is monkey-patched to
redirect every connection to the temp file.

Test isolation strategy:
  - Each test gets a fresh database through the `app` fixture.
  - `auth_client` registers + logs in a user before each test that needs auth.
  - DB-level helpers insert or query data directly through the patched get_db().
"""

import re
import sqlite3
import pytest
from datetime import date
from unittest.mock import patch
from werkzeug.security import generate_password_hash

import app as flask_app_module
from app import app as flask_app
import database.db as db_module
from database.db import init_db, insert_expense as db_add_expense


# ===========================================================================
# Constants
# ===========================================================================

ADD_EXPENSE_URL = "/expenses/add"
PROFILE_URL = "/profile"
LOGIN_URL = "/login"

VALID_CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"
]


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
    Test client that has completed registration and login.
    Returns the client object; tests that also need the user_id should call
    _get_user_id() inside an app context.
    """
    client.post(
        "/register",
        data={
            "name": "Test User",
            "email": "test@spendly.com",
            "password": "testpass123",
        },
    )
    client.post(
        "/login",
        data={"email": "test@spendly.com", "password": "testpass123"},
    )
    return client


# ===========================================================================
# DB helpers (used inside app context only)
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


def _get_expenses_for_user(user_id):
    """Return all expense rows for a given user_id as dicts."""
    conn = db_module.get_db()
    try:
        cursor = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _create_test_user(name="DB Test User", email="dbtest@spendly.com"):
    """Insert a bare-minimum user and return its id (for DB unit tests)."""
    conn = db_module.get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, generate_password_hash("testpass123")),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


# ===========================================================================
# 1. Authentication guard
# ===========================================================================

class TestAuthGuard:
    def test_unauthenticated_get_redirects_to_login(self, client):
        """
        Spec: GET /expenses/add is login-required.
        An unauthenticated request must return a 302 redirect to /login.
        """
        response = client.get(ADD_EXPENSE_URL)
        assert response.status_code == 302, (
            "Unauthenticated GET must redirect with 302"
        )
        assert LOGIN_URL in response.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_post_redirects_to_login(self, client):
        """
        Spec: POST /expenses/add is login-required.
        An unauthenticated POST must redirect to /login, never process the form.
        """
        response = client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "25.00",
                "category": "Food",
                "date": date.today().isoformat(),
                "description": "test meal",
            },
        )
        assert response.status_code == 302, (
            "Unauthenticated POST must redirect with 302"
        )
        assert LOGIN_URL in response.headers["Location"], (
            "Unauthenticated POST redirect target must be /login"
        )

    def test_unauthenticated_get_does_not_render_form(self, client):
        """
        Spec: The form must never be rendered for unauthenticated users; only the
        redirect response should be returned (no form HTML in body).
        """
        response = client.get(ADD_EXPENSE_URL, follow_redirects=False)
        assert b"<form" not in response.data, (
            "Add-expense form HTML must not be returned to unauthenticated users"
        )


# ===========================================================================
# 2. GET — form rendering
# ===========================================================================

class TestGetForm:
    def test_get_returns_200_for_logged_in_user(self, auth_client):
        """
        Spec: GET /expenses/add must return HTTP 200 for an authenticated user.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        assert response.status_code == 200, (
            "Expected HTTP 200 for authenticated GET /expenses/add"
        )

    def test_get_renders_add_expense_form(self, auth_client):
        """
        Spec: GET /expenses/add must render the add-expense form template.
        The page must include a form with method=POST.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        data = response.data.decode()
        assert 'method="POST"' in data or "method=POST" in data, (
            "Form must use POST method"
        )
        assert 'action="/expenses/add"' in data, (
            "Form action must point to /expenses/add"
        )

    def test_get_contains_amount_field(self, auth_client):
        """
        Spec: Form must contain an amount number input with step=0.01 and min=0.01.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        data = response.data.decode()
        assert 'name="amount"' in data, "Form must contain an amount input field"
        assert 'type="number"' in data, "Amount field must be type=number"

    def test_get_contains_category_select(self, auth_client):
        """
        Spec: Form must contain a category select with the seven valid options.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        data = response.data.decode()
        assert 'name="category"' in data, "Form must contain a category select field"
        for cat in VALID_CATEGORIES:
            assert cat in data, f"Category option '{cat}' must appear in the form"

    def test_get_contains_date_field(self, auth_client):
        """
        Spec: Form must contain a date input field.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        data = response.data.decode()
        assert 'name="date"' in data, "Form must contain a date input field"
        assert 'type="date"' in data, "Date field must be type=date"

    def test_get_contains_description_field(self, auth_client):
        """
        Spec: Form must contain an optional description text input.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        data = response.data.decode()
        assert 'name="description"' in data, (
            "Form must contain a description input field"
        )

    def test_get_contains_submit_button_labelled_add_expense(self, auth_client):
        """
        Spec: The form must contain a submit button labelled 'Add Expense'.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b"Add Expense" in response.data, (
            "Form must contain a submit button labelled 'Add Expense'"
        )

    def test_get_extends_base_template(self, auth_client):
        """
        Spec: add_expense.html extends base.html — the rendered page must include
        structural HTML elements present in the base template (e.g. <html>, <body>).
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        data = response.data.decode()
        assert "<html" in data, "Page must be a full HTML document (extends base.html)"
        assert "<body" in data, "Page must include a <body> tag from base.html"

    def test_get_no_error_shown_initially(self, auth_client):
        """
        Spec: On a clean GET request no error message should be displayed.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        data = response.data.decode()
        # The error div should not be present on a clean GET
        assert "auth-error" not in data, (
            "No error message should be shown on initial GET"
        )


# ===========================================================================
# 3. GET — today's date pre-fill
# ===========================================================================

class TestGetDatePrefill:
    def test_date_field_prefilled_with_today(self, auth_client):
        """
        Spec: The date input must default to today's date (date.today().isoformat())
        when the form is rendered via GET.
        """
        today_iso = date.today().isoformat()
        response = auth_client.get(ADD_EXPENSE_URL)
        assert today_iso.encode() in response.data, (
            f"Today's date ({today_iso}) must be pre-filled in the date field"
        )

    def test_date_field_value_is_iso_format(self, auth_client):
        """
        Spec: The pre-filled date must be in YYYY-MM-DD ISO format to match what
        <input type='date'> expects from the browser.
        """
        response = auth_client.get(ADD_EXPENSE_URL)
        data = response.data.decode()
        today_iso = date.today().isoformat()
        # Verify it contains a value attribute matching YYYY-MM-DD pattern
        iso_pattern = re.compile(r'value="\d{4}-\d{2}-\d{2}"')
        assert iso_pattern.search(data), (
            "Date field value must be in YYYY-MM-DD format"
        )
        assert today_iso in data, (
            "The YYYY-MM-DD date value must equal today's date"
        )


# ===========================================================================
# 4. POST — happy path
# ===========================================================================

class TestPostHappyPath:
    def test_valid_submission_redirects_to_profile(self, auth_client):
        """
        Spec: Submitting valid form data must redirect to /profile.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "42.50",
                "category": "Food",
                "date": "2026-05-15",
                "description": "Lunch at cafe",
            },
        )
        assert response.status_code == 302, (
            "Valid POST must respond with 302 redirect"
        )
        assert PROFILE_URL in response.headers["Location"], (
            "Redirect after valid POST must target /profile"
        )

    def test_valid_submission_inserts_row_in_expenses_table(self, auth_client, app):
        """
        Spec: Submitting valid data must insert exactly one row into the expenses
        table with the correct field values.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")

        auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "99.99",
                "category": "Transport",
                "date": "2026-06-01",
                "description": "Monthly bus pass",
            },
        )

        with app.app_context():
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 1, (
            "Exactly one expense row must be inserted after a valid POST"
        )
        row = expenses[0]
        assert row["user_id"] == uid, "Inserted row must belong to the logged-in user"
        assert row["amount"] == pytest.approx(99.99), (
            "Inserted amount must match submitted value"
        )
        assert row["category"] == "Transport", (
            "Inserted category must match submitted value"
        )
        assert row["date"] == "2026-06-01", (
            "Inserted date must match submitted value"
        )
        assert row["description"] == "Monthly bus pass", (
            "Inserted description must match submitted value"
        )

    def test_valid_submission_expense_appears_on_profile(self, auth_client):
        """
        Spec: The new expense must appear in the transactions list on /profile
        after a successful submission.
        """
        auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "75.00",
                "category": "Health",
                "date": "2026-05-20",
                "description": "Pharmacy visit",
            },
        )
        response = auth_client.get(PROFILE_URL)
        assert b"Pharmacy visit" in response.data, (
            "Newly added expense description must appear on /profile after submission"
        )
        assert b"75.00" in response.data, (
            "Newly added expense amount must appear on /profile after submission"
        )

    def test_valid_submission_amount_cast_to_float(self, auth_client, app):
        """
        Spec: amount must be cast to float before insertion. An amount submitted
        as a string with decimal places must be stored as a float in the DB.
        """
        auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "10.50",
                "category": "Shopping",
                "date": "2026-05-10",
                "description": "Book",
            },
        )
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 1
        assert isinstance(expenses[0]["amount"], float), (
            "Amount in the DB must be stored as a float, not a string"
        )
        assert expenses[0]["amount"] == pytest.approx(10.50)

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_valid_submission_accepts_all_valid_categories(self, auth_client, app, category):
        """
        Spec: Each of the seven valid categories must be accepted and stored.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "5.00",
                "category": category,
                "date": "2026-05-01",
                "description": f"Test {category}",
            },
        )
        assert response.status_code == 302, (
            f"Category '{category}' must be accepted; expected redirect"
        )
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert any(e["category"] == category for e in expenses), (
            f"Category '{category}' must be stored in the DB"
        )


# ===========================================================================
# 5. POST — description is optional
# ===========================================================================

class TestPostDescriptionOptional:
    def test_submission_without_description_succeeds(self, auth_client):
        """
        Spec: description is optional; omitting it must not cause a validation
        error — the form should submit successfully and redirect to /profile.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "12.00",
                "category": "Other",
                "date": "2026-05-05",
                # description intentionally omitted
            },
        )
        assert response.status_code == 302, (
            "Submission without description must succeed with 302 redirect"
        )
        assert PROFILE_URL in response.headers["Location"]

    def test_empty_description_stored_as_none_in_db(self, auth_client, app):
        """
        Spec: An empty description field must be stored as NULL (None) in the DB,
        never as an empty string, so the DB remains clean.
        """
        auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "8.00",
                "category": "Bills",
                "date": "2026-05-06",
                "description": "",
            },
        )
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 1
        assert expenses[0]["description"] is None, (
            "Empty description must be stored as NULL in the DB, not as empty string"
        )

    def test_whitespace_only_description_stored_as_none(self, auth_client, app):
        """
        Spec: A description containing only whitespace should be treated as absent
        (the route strips the value) and stored as NULL.
        """
        auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "3.00",
                "category": "Food",
                "date": "2026-05-07",
                "description": "   ",
            },
        )
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 1
        # After strip(), '   ' becomes '' which is falsy; stored as None
        assert expenses[0]["description"] is None, (
            "Whitespace-only description must be stored as NULL after stripping"
        )


# ===========================================================================
# 6. POST — amount validation errors
# ===========================================================================

class TestPostAmountValidation:
    def test_missing_amount_shows_error_and_rerenders_form(self, auth_client):
        """
        Spec: Submitting without an amount must show an error and re-render the
        add-expense form (not redirect to /profile).
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-05-15",
                "description": "Test",
            },
        )
        assert response.status_code == 200, (
            "Missing amount must re-render the form with status 200"
        )
        assert b"Add Expense" in response.data, (
            "Form must be re-rendered after amount validation failure"
        )

    def test_missing_amount_shows_user_friendly_error_message(self, auth_client):
        """
        Spec: The error message for missing/invalid amount must be user-friendly.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={"amount": "", "category": "Food", "date": "2026-05-15"},
        )
        data = response.data.decode()
        # The spec says: "Amount must be a number greater than 0."
        assert "Amount" in data, (
            "Error message must reference 'Amount' when amount field is invalid"
        )

    def test_zero_amount_shows_error(self, auth_client):
        """
        Spec: Amount must be greater than 0; zero must be rejected with an error.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-05-15",
                "description": "Zero test",
            },
        )
        assert response.status_code == 200, (
            "Zero amount must re-render the form, not redirect"
        )
        data = response.data.decode()
        assert "Amount" in data or "amount" in data or "0" in data, (
            "An error message must be shown for zero amount"
        )

    def test_negative_amount_shows_error(self, auth_client):
        """
        Spec: amount <= 0 is rejected.  A negative value must be treated the same
        as zero and produce an error response.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "-10.00",
                "category": "Food",
                "date": "2026-05-15",
                "description": "Negative test",
            },
        )
        assert response.status_code == 200, (
            "Negative amount must re-render the form, not redirect"
        )

    def test_non_numeric_amount_shows_error(self, auth_client):
        """
        Spec: Non-numeric input for amount must be rejected with a user-friendly
        error message.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-05-15",
                "description": "Non-numeric",
            },
        )
        assert response.status_code == 200, (
            "Non-numeric amount must re-render the form, not redirect"
        )
        data = response.data.decode()
        assert "Amount" in data, (
            "Error message for non-numeric amount must mention 'Amount'"
        )

    def test_amount_with_text_suffix_shows_error(self, auth_client):
        """
        Edge case: A value like '25abc' cannot be cast to float and must be rejected.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "25abc",
                "category": "Food",
                "date": "2026-05-15",
            },
        )
        assert response.status_code == 200, (
            "'25abc' is not a valid numeric amount; form must be re-rendered"
        )

    def test_invalid_amount_does_not_insert_db_row(self, auth_client, app):
        """
        Spec: On validation failure no DB row must be inserted.
        """
        auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "notanumber",
                "category": "Food",
                "date": "2026-05-15",
            },
        )
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 0, (
            "No DB row must be inserted when amount validation fails"
        )


# ===========================================================================
# 7. POST — category validation errors
# ===========================================================================

class TestPostCategoryValidation:
    def test_invalid_category_shows_error(self, auth_client):
        """
        Spec: A category not in the allowed list must be rejected with an error
        and the form must be re-rendered.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "15.00",
                "category": "Luxury",
                "date": "2026-05-15",
                "description": "Invalid category test",
            },
        )
        assert response.status_code == 200, (
            "Invalid category must re-render the form, not redirect"
        )
        data = response.data.decode()
        assert "category" in data.lower() or "valid" in data.lower() or "select" in data.lower(), (
            "Error message must indicate the category is invalid"
        )

    def test_empty_category_shows_error(self, auth_client):
        """
        Spec: An empty string for category is not in the valid list and must be
        rejected.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "15.00",
                "category": "",
                "date": "2026-05-15",
            },
        )
        assert response.status_code == 200, (
            "Empty category must re-render the form, not redirect"
        )

    @pytest.mark.parametrize("bad_category", [
        "food",          # wrong case
        "FOOD",          # all caps
        "Transport ",    # trailing space
        " Bills",        # leading space
        "Unknown",       # not in list at all
        "None",          # literal string 'None'
        "1",             # numeric string
    ])
    def test_various_invalid_categories_are_rejected(self, auth_client, bad_category):
        """
        Spec: Only exact matches from the allowed list are accepted; any other
        value must trigger a validation error.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "10.00",
                "category": bad_category,
                "date": "2026-05-15",
            },
        )
        assert response.status_code == 200, (
            f"Category '{bad_category}' must be rejected; expected form re-render"
        )

    def test_invalid_category_does_not_insert_db_row(self, auth_client, app):
        """
        Spec: No DB row must be inserted when category validation fails.
        """
        auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "10.00",
                "category": "InvalidCat",
                "date": "2026-05-15",
            },
        )
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 0, (
            "No DB row must be inserted when category validation fails"
        )


# ===========================================================================
# 8. POST — date validation errors
# ===========================================================================

class TestPostDateValidation:
    def test_malformed_date_shows_error(self, auth_client):
        """
        Spec: A date that cannot be parsed by datetime.strptime with '%Y-%m-%D'
        must be rejected and the form re-rendered with an error.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "15-05-2026",    # DD-MM-YYYY not accepted
                "description": "Wrong date format",
            },
        )
        assert response.status_code == 200, (
            "Malformed date must re-render the form, not redirect"
        )
        data = response.data.decode()
        assert "date" in data.lower() or "valid" in data.lower(), (
            "Error message must indicate the date is invalid"
        )

    def test_non_date_string_shows_error(self, auth_client):
        """
        Spec: A completely non-date string must be rejected.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "not-a-date",
            },
        )
        assert response.status_code == 200, (
            "Non-date string must re-render the form, not redirect"
        )

    def test_missing_date_shows_error(self, auth_client):
        """
        Spec: An empty date field must be rejected (strptime will fail on '').
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "",
            },
        )
        assert response.status_code == 200, (
            "Empty date must re-render the form, not redirect"
        )

    def test_impossible_date_shows_error(self, auth_client):
        """
        Spec: A semantically impossible date (month 13, day 32) must be rejected
        by datetime.strptime which raises ValueError for out-of-range values.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "2026-13-01",   # month 13 does not exist
            },
        )
        assert response.status_code == 200, (
            "Impossible date (month 13) must re-render the form, not redirect"
        )

    def test_date_with_slashes_shows_error(self, auth_client):
        """
        Edge case: MM/DD/YYYY (US format with slashes) is not YYYY-MM-DD and
        must be rejected.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "05/15/2026",
            },
        )
        assert response.status_code == 200, (
            "MM/DD/YYYY date format must be rejected; only YYYY-MM-DD is valid"
        )

    def test_invalid_date_does_not_insert_db_row(self, auth_client, app):
        """
        Spec: No DB row must be inserted when date validation fails.
        """
        auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "20.00",
                "category": "Food",
                "date": "baddate",
            },
        )
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 0, (
            "No DB row must be inserted when date validation fails"
        )


# ===========================================================================
# 9. POST — sticky form (re-population after validation failure)
# ===========================================================================

class TestStickyFormValues:
    def test_amount_repopulated_after_invalid_category(self, auth_client):
        """
        Spec: After a validation failure the previously submitted amount value
        must be re-populated in the form so the user does not lose their input.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "123.45",
                "category": "InvalidCat",
                "date": "2026-05-15",
                "description": "Sticky test",
            },
        )
        assert b"123.45" in response.data, (
            "Amount value '123.45' must be re-populated in the form after category error"
        )

    def test_description_repopulated_after_invalid_amount(self, auth_client):
        """
        Spec: After a validation failure all previously submitted values are
        re-populated. Description must be preserved after an amount error.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "abc",
                "category": "Food",
                "date": "2026-05-15",
                "description": "My description stays",
            },
        )
        assert b"My description stays" in response.data, (
            "Description value must be re-populated in the form after amount error"
        )

    def test_date_repopulated_after_invalid_amount(self, auth_client):
        """
        Spec: The submitted date must survive a validation failure and be
        re-populated in the form.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "0",
                "category": "Bills",
                "date": "2026-03-22",
                "description": "Date sticky",
            },
        )
        assert b"2026-03-22" in response.data, (
            "Date value must be re-populated in the form after amount=0 error"
        )

    def test_category_repopulated_after_invalid_date(self, auth_client):
        """
        Spec: The submitted category must be re-selected in the form after a date
        validation error so the user does not have to re-select it.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "50.00",
                "category": "Health",
                "date": "not-valid",
                "description": "Category sticky",
            },
        )
        # The template uses selected attribute for the matching option
        assert b"Health" in response.data, (
            "Category value must be re-populated in the form after date error"
        )

    def test_all_fields_repopulated_after_validation_failure(self, auth_client):
        """
        Spec: All valid field values must be re-populated in the form after any
        single validation failure.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "88.88",
                "category": "Entertainment",
                "date": "2026-04-10",
                "description": "Concert tickets",
            },
        )
        # Trigger failure by using an invalid category to test other fields survive
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "88.88",
                "category": "NotValid",
                "date": "2026-04-10",
                "description": "Concert tickets",
            },
        )
        data = response.data.decode()
        assert "88.88" in data, "amount must be re-populated"
        assert "2026-04-10" in data, "date must be re-populated"
        assert "Concert tickets" in data, "description must be re-populated"

    def test_error_message_displayed_above_form(self, auth_client):
        """
        Spec: The error variable must be displayed inline above the form on
        validation failure.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-05-15",
            },
        )
        data = response.data.decode()
        # The template renders the error inside a div with class 'auth-error'
        assert "auth-error" in data, (
            "Error message must be displayed using the auth-error div"
        )
        # The form must still be present after the error
        assert "<form" in data, (
            "Form must still be rendered below the error message"
        )


# ===========================================================================
# 10. POST — SQL injection safety
# ===========================================================================

class TestSQLInjectionSafety:
    def test_sql_injection_in_description_is_handled_safely(self, auth_client, app):
        """
        Spec: Parameterized queries must handle SQL injection attempts in the
        description field without crashing or corrupting the DB.
        """
        payload = "'; DROP TABLE expenses; --"
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "10.00",
                "category": "Other",
                "date": "2026-05-15",
                "description": payload,
            },
        )
        # The submission must succeed (302 redirect to /profile)
        assert response.status_code == 302, (
            "SQL injection in description must not cause a server error"
        )
        # The expenses table must still exist and contain the inserted row
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 1, (
            "Expenses table must survive SQL injection attempt in description"
        )
        assert expenses[0]["description"] == payload, (
            "SQL injection payload must be stored as literal text, not executed"
        )

    def test_sql_injection_in_amount_is_rejected_by_validation(self, auth_client, app):
        """
        Spec: A SQL injection attempt in the amount field must be caught by float()
        casting, return a validation error, and leave the DB unmodified.
        """
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data={
                "amount": "1 OR 1=1",
                "category": "Food",
                "date": "2026-05-15",
            },
        )
        assert response.status_code == 200, (
            "SQL injection in amount must be rejected at float() cast, not reach DB"
        )
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 0, (
            "No DB row must be inserted when amount contains SQL injection attempt"
        )


# ===========================================================================
# 11. DB helper unit tests — add_expense()
# ===========================================================================

class TestAddExpenseDBHelper:
    def test_add_expense_returns_new_row_id(self, app):
        """
        Spec: add_expense() must return the integer id of the newly inserted row.
        """
        with app.app_context():
            uid = _create_test_user()
            row_id = db_add_expense(uid, 50.0, "Food", "2026-05-01", "Test meal")

        assert isinstance(row_id, int), (
            "add_expense() must return an integer row id"
        )
        assert row_id > 0, "Returned row id must be a positive integer"

    def test_add_expense_inserts_correct_values(self, app):
        """
        Spec: The row inserted by add_expense() must have the exact values passed
        as arguments.
        """
        with app.app_context():
            uid = _create_test_user()
            row_id = db_add_expense(uid, 123.45, "Transport", "2026-06-10", "Bus fare")

            expenses = _get_expenses_for_user(uid)

        assert len(expenses) == 1, "Exactly one row must be inserted"
        row = expenses[0]
        assert row["id"] == row_id, "Returned id must match the inserted row's id"
        assert row["user_id"] == uid
        assert row["amount"] == pytest.approx(123.45)
        assert row["category"] == "Transport"
        assert row["date"] == "2026-06-10"
        assert row["description"] == "Bus fare"

    def test_add_expense_stores_none_description(self, app):
        """
        Spec: Passing None as description must store NULL in the DB.
        """
        with app.app_context():
            uid = _create_test_user()
            db_add_expense(uid, 10.0, "Other", "2026-05-01", None)
            expenses = _get_expenses_for_user(uid)

        assert expenses[0]["description"] is None, (
            "add_expense() with None description must store NULL in the DB"
        )

    def test_add_expense_multiple_calls_produce_distinct_ids(self, app):
        """
        Spec: Each call to add_expense() must produce a unique row id (AUTOINCREMENT).
        """
        with app.app_context():
            uid = _create_test_user()
            id1 = db_add_expense(uid, 10.0, "Food", "2026-05-01", "first")
            id2 = db_add_expense(uid, 20.0, "Bills", "2026-05-02", "second")

        assert id1 != id2, "Each add_expense() call must return a distinct row id"

    def test_add_expense_row_is_associated_with_correct_user(self, app):
        """
        Spec: Expenses must be associated with the correct user via user_id FK.
        An expense inserted for user A must not appear when querying user B.
        """
        with app.app_context():
            uid_a = _create_test_user(name="User A", email="usera@spendly.com")
            uid_b = _create_test_user(name="User B", email="userb@spendly.com")
            db_add_expense(uid_a, 50.0, "Food", "2026-05-01", "User A expense")

            expenses_a = _get_expenses_for_user(uid_a)
            expenses_b = _get_expenses_for_user(uid_b)

        assert len(expenses_a) == 1, "User A must have exactly one expense"
        assert len(expenses_b) == 0, (
            "User B must have no expenses; user_id FK must be respected"
        )


# ===========================================================================
# 12. Template quality — no hardcoded hex colours
# ===========================================================================

class TestTemplateQuality:
    def test_add_expense_html_has_no_hardcoded_hex_colours(self):
        """
        Spec: add_expense.html must not contain hardcoded hex colour values.
        All colours must use CSS variables (e.g. var(--primary)).
        A hex colour is defined as '#' followed by exactly 3 or 6 hex digits.
        """
        template_path = (
            "C:\\Users\\aman_sharma\\Desktop\\llm_training\\"
            "expense-tracker\\expense-tracker\\templates\\add_expense.html"
        )
        with open(template_path, "r", encoding="utf-8") as fh:
            content = fh.read()

        # Match #RGB or #RRGGBB (case-insensitive), not preceded by a word char
        # (to avoid matching hex values inside URL hashes or other non-colour contexts)
        hex_colour_pattern = re.compile(r'(?<!\w)#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')
        matches = hex_colour_pattern.findall(content)
        assert len(matches) == 0, (
            f"add_expense.html must not contain hardcoded hex colours; "
            f"found: {['#' + m for m in matches]}"
        )


# ===========================================================================
# 13. DB helper — no SQL string formatting (static analysis)
# ===========================================================================

class TestNoSQLStringFormatting:
    def test_add_expense_helper_uses_no_fstring_sql(self):
        """
        Spec: add_expense() must use parameterised queries only.
        No f-string, %-formatting, or .format() calls should appear in the
        SQL statement inside database/db.py's add_expense function.
        """
        db_path = (
            "C:\\Users\\aman_sharma\\Desktop\\llm_training\\"
            "expense-tracker\\expense-tracker\\database\\db.py"
        )
        with open(db_path, "r", encoding="utf-8") as fh:
            source = fh.read()

        # Extract only the add_expense function body for targeted analysis.
        # We find the function and read until the next top-level def or class.
        func_match = re.search(
            r"def insert_expense\(.*?\):(.*?)(?=\ndef |\nclass |\Z)",
            source,
            re.DOTALL,
        )
        assert func_match is not None, (
            "insert_expense() function must exist in database/db.py"
        )
        func_body = func_match.group(1)

        # f-string SQL: f"... INSERT ... {variable} ..."
        assert not re.search(r'f["\'].*?INSERT.*?\{', func_body), (
            "insert_expense() must not use f-string formatting in SQL statements"
        )
        # %-style SQL: "INSERT ... %s" % value
        assert not re.search(r'["\'].*?INSERT.*?%[sd].*?["\'].*?%', func_body), (
            "insert_expense() must not use %-style formatting in SQL statements"
        )
        # .format() SQL: "INSERT ... {}".format(value)
        assert not re.search(r'["\'].*?INSERT.*?\{\}.*?["\'].*?\.format\(', func_body), (
            "insert_expense() must not use .format() formatting in SQL statements"
        )

    def test_add_expense_helper_uses_question_mark_placeholders(self):
        """
        Spec: Parameterised queries use '?' placeholders in sqlite3.
        The add_expense() function must use VALUES (?, ?, ?, ?, ?) syntax.
        """
        db_path = (
            "C:\\Users\\aman_sharma\\Desktop\\llm_training\\"
            "expense-tracker\\expense-tracker\\database\\db.py"
        )
        with open(db_path, "r", encoding="utf-8") as fh:
            source = fh.read()

        func_match = re.search(
            r"def insert_expense\(.*?\):(.*?)(?=\ndef |\nclass |\Z)",
            source,
            re.DOTALL,
        )
        assert func_match is not None
        func_body = func_match.group(1)

        # Must contain at least one '?' placeholder in the SQL
        assert "?" in func_body, (
            "insert_expense() must use '?' placeholders for parameterised queries"
        )
        # Must contain VALUES with placeholders
        assert re.search(r"VALUES\s*\(\s*\?", func_body, re.IGNORECASE), (
            "insert_expense() INSERT statement must use VALUES (?, ...) placeholders"
        )
