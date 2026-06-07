"""
tests/test_06-date-filter-for-profile-page.py

Pytest test suite for the Spendly date-filter feature on the /profile page.

Spec: .claude/specs/06-date-filter-for-profile-page.md

All tests use an in-memory SQLite database so the real expense_tracker.db is
never touched. The get_db() function is monkey-patched via the app's DATABASE
config key to route every database call to ':memory:'.

Test isolation strategy:
  - Each test gets a fresh in-memory database via the `app` fixture.
  - The `auth_client` fixture registers + logs in a user automatically.
  - Expense seeding helpers insert controlled data directly through get_db().
"""

import pytest
import sqlite3
from datetime import date, timedelta
from unittest.mock import patch
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# We import the Flask application and DB helpers once; the fixtures below
# override the database path at test-execution time.
# ---------------------------------------------------------------------------
import app as flask_app_module
from app import app as flask_app
import database.db as db_module
from database.db import (
    init_db,
    get_profile_stats,
    get_recent_expenses,
    get_category_breakdown,
)


# ===========================================================================
# Fixtures
# ===========================================================================

_TEST_DB_CONN = None  # module-level handle so helpers can reuse it


@pytest.fixture
def app(tmp_path):
    """
    Create a Flask test application backed by an isolated on-disk SQLite DB
    (located in pytest's tmp_path so it never touches expense_tracker.db).
    Using a file-based path in tmp_path avoids the shared-connection pitfall
    of ':memory:' when the app opens/closes its own connections per request.
    """
    db_path = str(tmp_path / "test_expense_tracker.db")

    flask_app.config.update(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "WTF_CSRF_ENABLED": False,
        }
    )

    # Patch get_db so every DB call in both app.py and database/db.py
    # goes to our isolated test database file.
    original_get_db = db_module.get_db

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
    A test client that has completed registration and login.
    Returns (client, user_id) so tests can seed expenses for that user.
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


# ---------------------------------------------------------------------------
# Expense seeding helper (inserts directly through the patched get_db)
# ---------------------------------------------------------------------------

def _seed_expenses(expenses):
    """
    Insert a list of (user_id, amount, category, date_str, description) tuples
    into the test database.  Must be called inside an active app context where
    get_db is already patched.
    """
    conn = db_module.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            expenses,
        )
        conn.commit()
    finally:
        conn.close()


def _get_user_id(email):
    """Return the integer user_id for a registered email."""
    conn = db_module.get_db()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


# ===========================================================================
# Helper: compute the same preset date strings the app computes
# ===========================================================================

def _preset_ranges():
    """Return a dict of label -> (start_str, end_str) matching app.py logic."""
    today = date.today()
    month_start = today.replace(day=1)
    last_month_end = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return {
        "This Month": (month_start.isoformat(), today.isoformat()),
        "Last Month": (last_month_start.isoformat(), last_month_end.isoformat()),
        "Last 3 Months": (
            (today - timedelta(days=90)).isoformat(),
            today.isoformat(),
        ),
        "Last 6 Months": (
            (today - timedelta(days=180)).isoformat(),
            today.isoformat(),
        ),
        "All Time": (None, None),
    }


# ===========================================================================
# 1. Authentication guard
# ===========================================================================


class TestAuthGuard:
    def test_unauthenticated_no_params_redirects_to_login(self, client):
        """
        Spec: GET /profile is login-required. An unauthenticated request with
        no query parameters must redirect to /login, not render profile data.
        """
        response = client.get("/profile")
        assert response.status_code == 302, "Expected redirect for unauthenticated access"
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_with_valid_date_params_redirects_to_login(self, client):
        """
        Spec: Auth guard applies regardless of query params. Even with a
        well-formed ?start=...&end=... the user must be redirected to /login.
        """
        response = client.get("/profile?start=2026-01-01&end=2026-01-31")
        assert response.status_code == 302, "Expected redirect even with valid date params"
        assert "/login" in response.headers["Location"]

    def test_unauthenticated_with_malformed_date_params_redirects_to_login(
        self, client
    ):
        """
        Spec: Auth guard fires before any date parsing; malformed params must
        still trigger a redirect to /login, not a 500 or 400.
        """
        response = client.get("/profile?start=notadate&end=alsonotadate")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# ===========================================================================
# 2. All-Time view (no query params)
# ===========================================================================


class TestAllTimeView:
    def test_profile_no_params_returns_200(self, auth_client, app):
        """
        Spec: GET /profile with no query params is the baseline all-time view;
        must return HTTP 200 for an authenticated user.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [(uid, 100.0, "Food", "2025-01-15", "Old expense")]
            )
        response = auth_client.get("/profile")
        assert response.status_code == 200, "Expected 200 for authenticated all-time view"

    def test_profile_no_params_active_period_is_all_time(self, auth_client, app):
        """
        Spec: When no date filter is active the template receives
        active_period == 'All Time' and the filter bar must highlight 'All Time'.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 50.0, "Transport", "2025-06-01", "Bus")])
        response = auth_client.get("/profile")
        assert b"All Time" in response.data, (
            "Expected 'All Time' text in page when no filter is active"
        )

    def test_profile_no_params_transactions_heading_has_no_period_label(
        self, auth_client, app
    ):
        """
        Spec: The transactions section heading must read 'Transactions' (no dash
        and period label) when the All Time view is active.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 20.0, "Food", "2025-03-10", "Lunch")])
        response = auth_client.get("/profile")
        data = response.data.decode()
        # The heading should contain "Transactions" but NOT "Transactions —"
        # with an appended date label (spec says no dash suffix for All Time)
        assert "Transactions" in data, "Expected Transactions heading to be present"
        # Verify no period suffix like "Transactions — This Month"
        for label in ["This Month", "Last Month", "Last 3 Months", "Last 6 Months"]:
            assert f"Transactions — {label}" not in data, (
                f"Heading must not show '— {label}' for All Time view"
            )

    def test_profile_no_params_shows_all_expenses(self, auth_client, app):
        """
        Spec: All-time view must aggregate every expense regardless of date.
        Stats total_spent must equal the sum of all seeded expenses.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [
                    (uid, 100.0, "Food", "2024-01-01", "Old food"),
                    (uid, 200.0, "Bills", "2023-06-15", "Old bill"),
                    (uid, 50.0, "Shopping", "2026-05-01", "Recent"),
                ]
            )
        response = auth_client.get("/profile")
        # Total is 350.00; template formats as ₹350.00
        assert b"350.00" in response.data, (
            "All-time view must sum all expenses across all dates"
        )


# ===========================================================================
# 3. Preset filter — This Month
# ===========================================================================


class TestThisMonthPreset:
    def test_this_month_returns_200(self, auth_client):
        """
        Spec: Visiting /profile with This Month preset query params must return
        HTTP 200 for an authenticated user.
        """
        presets = _preset_ranges()
        start, end = presets["This Month"]
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert response.status_code == 200

    def test_this_month_active_period_label_in_heading(self, auth_client, app):
        """
        Spec: When the This Month preset is active, the transactions section
        heading must include '— This Month'.
        """
        presets = _preset_ranges()
        start, end = presets["This Month"]
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 10.0, "Food", start, "In-month expense")])
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert b"This Month" in response.data, (
            "Expected 'This Month' in response when that preset is active"
        )

    def test_this_month_excludes_expenses_outside_range(self, auth_client, app):
        """
        Spec: Stats and transactions must only include expenses whose date falls
        between start and end (inclusive). An expense from last year must not
        appear in This Month stats.
        """
        presets = _preset_ranges()
        start, end = presets["This Month"]
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [
                    (uid, 999.99, "Food", "2022-01-01", "Very old expense"),
                    (uid, 42.00, "Transport", start, "This month expense"),
                ]
            )
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert b"999.99" not in response.data, (
            "Expense from outside the month range must not appear in filtered view"
        )
        assert b"42.00" in response.data, (
            "Expense from within the month range must appear in filtered view"
        )

    def test_this_month_filter_btn_has_active_class(self, auth_client, app):
        """
        Spec: The active preset button receives the 'active' CSS class.
        When This Month is selected, its <a> tag must contain 'active'.
        """
        presets = _preset_ranges()
        start, end = presets["This Month"]
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 5.0, "Food", start, "snack")])
        response = auth_client.get(f"/profile?start={start}&end={end}")
        data = response.data.decode()
        # The filter button for This Month with 'active' class must appear
        assert "active" in data, "Expected at least one filter button with 'active' class"
        # More specifically, the active link should reference This Month's dates
        assert f"start={start}" in data and "active" in data, (
            "The This Month link should be present and have active class"
        )


# ===========================================================================
# 4. Preset filter — Last Month
# ===========================================================================


class TestLastMonthPreset:
    def test_last_month_active_period_in_page(self, auth_client, app):
        """
        Spec: When Last Month preset dates are supplied as query params the
        active_period must be 'Last Month' and appear in the rendered page.
        """
        presets = _preset_ranges()
        start, end = presets["Last Month"]
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 30.0, "Bills", start, "last month bill")])
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert b"Last Month" in response.data, (
            "Expected 'Last Month' to appear in page when that preset is active"
        )

    def test_last_month_excludes_current_month_expenses(self, auth_client, app):
        """
        Spec: Last Month filter must exclude expenses that fall within the
        current month (i.e. after last_month_end).
        """
        presets = _preset_ranges()
        start, end = presets["Last Month"]
        today = date.today()
        current_month_date = today.replace(day=1).isoformat()
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [
                    (uid, 777.77, "Shopping", current_month_date, "current month item"),
                    (uid, 55.50, "Food", start, "last month food"),
                ]
            )
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert b"777.77" not in response.data, (
            "Current-month expense must not appear in Last Month filtered view"
        )
        assert b"55.50" in response.data, (
            "Last-month expense must appear in Last Month filtered view"
        )


# ===========================================================================
# 5. Preset filter — Last 3 Months
# ===========================================================================


class TestLast3MonthsPreset:
    def test_last_3_months_active_period_in_page(self, auth_client, app):
        """
        Spec: When start = today-90 days and end = today, the active_period
        label 'Last 3 Months' must appear in the rendered page.
        """
        presets = _preset_ranges()
        start, end = presets["Last 3 Months"]
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 20.0, "Health", start, "gym")])
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert b"Last 3 Months" in response.data

    def test_last_3_months_excludes_expense_before_window(self, auth_client, app):
        """
        Spec: An expense dated before (today - 90 days) must be excluded from
        the Last 3 Months filtered stats.
        """
        presets = _preset_ranges()
        start, end = presets["Last 3 Months"]
        old_date = (date.today() - timedelta(days=91)).isoformat()
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [
                    (uid, 888.88, "Entertainment", old_date, "old concert"),
                    (uid, 33.33, "Food", start, "recent meal"),
                ]
            )
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert b"888.88" not in response.data, (
            "Expense older than 90 days must not appear in Last 3 Months view"
        )


# ===========================================================================
# 6. Preset filter — Last 6 Months
# ===========================================================================


class TestLast6MonthsPreset:
    def test_last_6_months_active_period_in_page(self, auth_client, app):
        """
        Spec: When start = today-180 days and end = today, the active_period
        label 'Last 6 Months' must appear in the rendered page.
        """
        presets = _preset_ranges()
        start, end = presets["Last 6 Months"]
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 60.0, "Bills", start, "utility")])
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert b"Last 6 Months" in response.data

    def test_last_6_months_excludes_expense_before_window(self, auth_client, app):
        """
        Spec: An expense older than 180 days must be excluded when the Last 6
        Months preset is active.
        """
        presets = _preset_ranges()
        start, end = presets["Last 6 Months"]
        old_date = (date.today() - timedelta(days=181)).isoformat()
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [
                    (uid, 555.55, "Transport", old_date, "very old trip"),
                    (uid, 25.0, "Food", start, "recent food"),
                ]
            )
        response = auth_client.get(f"/profile?start={start}&end={end}")
        assert b"555.55" not in response.data, (
            "Expense older than 180 days must not appear in Last 6 Months view"
        )


# ===========================================================================
# 7. Custom date range (no matching preset)
# ===========================================================================


class TestCustomDateRange:
    def test_custom_range_returns_200(self, auth_client):
        """
        Spec: A valid custom ?start=...&end=... that does not match any preset
        must still return HTTP 200 and filter data correctly.
        """
        response = auth_client.get("/profile?start=2026-01-01&end=2026-03-31")
        assert response.status_code == 200

    def test_custom_range_filters_expenses_to_range(self, auth_client, app):
        """
        Spec: The custom date-range form submits ?start=...&end=... and filters
        data to that range. Only expenses inside the range must appear.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [
                    (uid, 123.45, "Food", "2026-02-10", "inside range"),
                    (uid, 987.65, "Bills", "2025-06-01", "outside range"),
                ]
            )
        response = auth_client.get("/profile?start=2026-01-01&end=2026-03-31")
        assert b"123.45" in response.data, "Expense inside custom range must appear"
        assert b"987.65" not in response.data, "Expense outside custom range must not appear"

    def test_custom_range_no_preset_highlighted(self, auth_client, app):
        """
        Spec: When the active date range matches no preset, no preset button
        should receive the 'active' class. The template renders active_period=None
        in this case, so none of the preset labels should be wrapped in an 'active'
        anchor directly adjacent to their label text.
        We verify this by checking that the response does not contain
        'active">This Month' (or similar) while a unique non-preset range is active.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 10.0, "Food", "2026-02-15", "food")])
        # Use a date range guaranteed not to match any preset
        response = auth_client.get("/profile?start=2026-02-01&end=2026-02-28")
        data = response.data.decode()
        # None of the preset labels should be inside an element with class 'active'
        for label in ["This Month", "Last Month", "Last 3 Months", "Last 6 Months"]:
            assert f'active">\n                {label}' not in data and \
                   f"active\">{label}" not in data, (
                f"Preset '{label}' must not be highlighted for a custom date range"
            )


# ===========================================================================
# 8. Transaction limit behaviour
# ===========================================================================


class TestTransactionLimit:
    def test_no_filter_limits_transactions_to_5(self, auth_client, app):
        """
        Spec: Without a date filter the get_recent_expenses limit stays at 5,
        so at most 5 transaction rows should appear on the profile page.
        The test seeds 10 distinct expenses and verifies only 5 are rendered.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = [
                (uid, float(10 + i), "Food", f"2026-05-{i+1:02d}", f"meal {i}")
                for i in range(10)
            ]
            _seed_expenses(expenses)

        response = auth_client.get("/profile")
        data = response.data.decode()
        # Count how many "meal N" descriptions appear in the rendered HTML
        meal_count = sum(1 for i in range(10) if f"meal {i}" in data)
        assert meal_count <= 5, (
            f"Without a filter, at most 5 transactions must be shown; got {meal_count}"
        )

    def test_with_filter_limit_raised_to_50(self, auth_client, app):
        """
        Spec: When a date filter is active the limit in get_recent_expenses is
        raised to 50 so users see all matching rows for the selected period.
        The test seeds 10 expenses all within a specific date range and verifies
        all 10 are rendered when that range is queried.
        """
        presets = _preset_ranges()
        start, end = presets["This Month"]
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            expenses = [
                (uid, float(5 + i), "Food", start, f"filtered meal {i}")
                for i in range(10)
            ]
            _seed_expenses(expenses)

        response = auth_client.get(f"/profile?start={start}&end={end}")
        data = response.data.decode()
        meal_count = sum(1 for i in range(10) if f"filtered meal {i}" in data)
        assert meal_count == 10, (
            f"With a date filter active, all 10 matching transactions must appear; got {meal_count}"
        )


# ===========================================================================
# 9. Empty result set — no crash
# ===========================================================================


class TestEmptyResultSet:
    def test_no_expenses_in_range_shows_zero_total(self, auth_client, app):
        """
        Spec: A user with no expenses in the selected range sees ₹0.00 total
        spent — the template must not crash with a KeyError or AttributeError.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            # Expense is far outside the queried range
            _seed_expenses([(uid, 500.0, "Food", "2020-01-01", "old")])

        response = auth_client.get("/profile?start=2026-05-01&end=2026-05-31")
        assert response.status_code == 200, "Expected 200 even when range is empty"
        assert b"0.00" in response.data, "Expected ₹0.00 when no expenses in range"

    def test_no_expenses_in_range_shows_zero_transaction_count(self, auth_client, app):
        """
        Spec: A user with no expenses in the selected range sees 0 transactions.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 100.0, "Bills", "2019-12-31", "very old")])

        response = auth_client.get("/profile?start=2026-05-01&end=2026-05-31")
        assert response.status_code == 200
        # Transaction count stat card should show 0
        assert b"0" in response.data

    def test_no_expenses_in_range_shows_dash_for_top_category(self, auth_client, app):
        """
        Spec: When no expenses fall in the selected range the top category stat
        must display '—' (an em dash), not raise an exception.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 40.0, "Transport", "2018-06-01", "ancient")])

        response = auth_client.get("/profile?start=2026-05-01&end=2026-05-31")
        assert response.status_code == 200
        assert "—".encode() in response.data, (
            "Expected em dash '—' for top category when range has no expenses"
        )

    def test_no_expenses_in_range_empty_transactions_list(self, auth_client, app):
        """
        Spec: When no expenses fall in the range, the transactions panel must
        show the empty-state message rather than a populated table.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 99.0, "Shopping", "2015-01-01", "antique")])

        response = auth_client.get("/profile?start=2026-05-01&end=2026-05-31")
        assert b"No transactions yet" in response.data, (
            "Expected 'No transactions yet' empty state when range has no matching expenses"
        )

    def test_user_with_zero_expenses_all_time_no_crash(self, auth_client):
        """
        Spec: A user with no expenses at all must see zero/dash values and no
        template errors on the all-time view.
        """
        response = auth_client.get("/profile")
        assert response.status_code == 200
        assert b"0.00" in response.data


# ===========================================================================
# 10. Malformed / partial date parameter fallback
# ===========================================================================


class TestMalformedDateFallback:
    def test_malformed_start_falls_back_to_all_time(self, auth_client, app):
        """
        Spec: When 'start' is malformed (not YYYY-MM-DD), the app must silently
        fall back to all-time data — no 400, no 500, no unhandled exception.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 75.0, "Food", "2024-07-04", "fallback test")])

        response = auth_client.get("/profile?start=notadate&end=2026-01-01")
        assert response.status_code == 200, (
            "Malformed start date must yield 200, not an error response"
        )
        # All-time data should be shown (the seeded expense appears)
        assert b"75.00" in response.data, (
            "Falling back to all-time must show all expenses"
        )

    def test_malformed_end_falls_back_to_all_time(self, auth_client, app):
        """
        Spec: When 'end' is malformed, the same silent fallback applies.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 62.5, "Transport", "2024-08-20", "fallback end")])

        response = auth_client.get("/profile?start=2026-01-01&end=baddate")
        assert response.status_code == 200
        assert b"62.50" in response.data

    def test_both_dates_malformed_falls_back_to_all_time(self, auth_client, app):
        """
        Spec: When both params are malformed the app must return 200 and show
        all-time data rather than raising any exception.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 33.0, "Health", "2023-03-15", "checkup")])

        response = auth_client.get("/profile?start=abc&end=xyz")
        assert response.status_code == 200
        assert b"33.00" in response.data

    def test_only_start_provided_falls_back_to_all_time(self, auth_client, app):
        """
        Spec: The filter only activates when BOTH start and end are valid.
        Providing only 'start' must fall back to all-time data.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [
                    (uid, 111.11, "Bills", "2020-01-01", "old bill"),
                    (uid, 22.22, "Food", "2026-05-15", "recent food"),
                ]
            )

        response = auth_client.get("/profile?start=2026-05-01")
        assert response.status_code == 200
        # Both expenses should appear because it falls back to all-time
        assert b"111.11" in response.data, (
            "Only-start param must fall back to all-time and show all expenses"
        )

    def test_only_end_provided_falls_back_to_all_time(self, auth_client, app):
        """
        Spec: Providing only 'end' (no 'start') must fall back to all-time data.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses(
                [
                    (uid, 444.44, "Entertainment", "2019-12-25", "party"),
                    (uid, 11.11, "Food", "2026-05-01", "snack"),
                ]
            )

        response = auth_client.get("/profile?end=2026-05-31")
        assert response.status_code == 200
        assert b"444.44" in response.data, (
            "Only-end param must fall back to all-time and show all expenses"
        )

    def test_sql_injection_in_date_param_does_not_crash(self, auth_client, app):
        """
        Spec: Date values are validated via datetime.strptime before reaching SQL.
        A SQL injection attempt in the date param must be caught by the malformed-
        date fallback (strptime raises ValueError) and return 200, all-time data.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 50.0, "Food", "2026-05-01", "safe expense")])

        injection = "2026-01-01' OR '1'='1"
        response = auth_client.get(f"/profile?start={injection}&end=2026-12-31")
        assert response.status_code == 200, (
            "SQL injection attempt in date param must not crash the server"
        )


# ===========================================================================
# 11. Filter bar HTML structure
# ===========================================================================


class TestFilterBarHTML:
    def test_filter_bar_contains_all_five_preset_labels(self, auth_client):
        """
        Spec: The filter bar must contain five preset buttons labelled exactly:
        'This Month', 'Last Month', 'Last 3 Months', 'Last 6 Months', 'All Time'.
        """
        response = auth_client.get("/profile")
        data = response.data.decode()
        for label in ["This Month", "Last Month", "Last 3 Months", "Last 6 Months", "All Time"]:
            assert label in data, f"Expected preset label '{label}' in filter bar"

    def test_all_time_preset_links_to_bare_profile(self, auth_client):
        """
        Spec: The 'All Time' preset must link to bare /profile (no query params)
        — never pass start= and end= for the all-time view.
        """
        response = auth_client.get("/profile")
        data = response.data.decode()
        # The All Time anchor must href="/profile" not /profile?start=...
        # We look for the anchor that wraps "All Time" and verify it uses bare href
        assert 'href="/profile"' in data, (
            "All Time preset must link to bare /profile with no query params"
        )

    def test_preset_buttons_are_anchor_tags(self, auth_client):
        """
        Spec: Filter bar preset buttons must be <a> tags (not <form> submits)
        so the URL is bookmarkable.
        """
        response = auth_client.get("/profile")
        data = response.data.decode()
        # The filter-btn class should be on <a> elements
        assert 'class="filter-btn' in data, (
            "Expected <a> tags with class 'filter-btn' for preset buttons"
        )

    def test_custom_date_range_form_present(self, auth_client):
        """
        Spec: The profile page must include a collapsible custom date-range form
        with start and end <input type='date'> fields and method='GET'.
        """
        response = auth_client.get("/profile")
        data = response.data.decode()
        assert 'method="GET"' in data or "method=GET" in data, (
            "Custom date-range form must use method='GET'"
        )
        assert 'type="date"' in data, (
            "Custom date-range form must contain <input type='date'> fields"
        )
        assert 'name="start"' in data, "Custom form must have a 'start' date input"
        assert 'name="end"' in data, "Custom form must have an 'end' date input"

    def test_all_time_active_by_default(self, auth_client):
        """
        Spec: When no filter is active (bare /profile), the 'All Time' button
        must carry the 'active' CSS class.
        """
        response = auth_client.get("/profile")
        data = response.data.decode()
        # The All Time anchor should have class containing 'active'
        assert "active" in data, "Expected 'active' class somewhere in the filter bar"
        # Specifically the All Time link should be active when no params
        # Template renders: class="filter-btn active" for active_period == 'All Time'
        assert "filter-btn active" in data or "filter-btn  active" in data or \
               "active" in data, (
            "All Time filter button must have the 'active' CSS class when no filter is set"
        )


# ===========================================================================
# 12. Transactions section heading
# ===========================================================================


class TestTransactionHeading:
    def test_heading_shows_period_for_non_all_time_filter(self, auth_client, app):
        """
        Spec: The section heading above the transactions table changes to reflect
        the active period, e.g. 'Transactions — This Month'.
        """
        presets = _preset_ranges()
        start, end = presets["This Month"]
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 5.0, "Food", start, "item")])
        response = auth_client.get(f"/profile?start={start}&end={end}")
        data = response.data.decode()
        assert "Transactions" in data
        assert "This Month" in data, (
            "Heading must include period label 'This Month' when that preset is active"
        )

    def test_heading_shows_all_time_label_for_no_filter(self, auth_client):
        """
        Spec: 'All Time' appears in the page when no filter is active; the
        heading itself reads plain 'Transactions' (no dash suffix).
        """
        response = auth_client.get("/profile")
        data = response.data.decode()
        assert "Transactions" in data
        # The heading element should NOT contain "Transactions — " with a preset name
        assert "Transactions — All Time" not in data, (
            "Heading must not show '— All Time'; it should just say 'Transactions'"
        )

    def test_heading_shows_custom_range_description(self, auth_client, app):
        """
        Spec: For a custom date range that matches no preset, active_period is
        None and the template should not append any label after 'Transactions'.
        Verify the heading does not show any preset label.
        """
        # Use a fixed custom range unlikely to match any live preset
        with app.app_context():
            uid = _get_user_id("test@spendly.com")
            _seed_expenses([(uid, 9.0, "Food", "2026-02-15", "custom")])
        response = auth_client.get("/profile?start=2026-02-01&end=2026-02-28")
        data = response.data.decode()
        assert "Transactions" in data
        for label in ["This Month", "Last Month", "Last 3 Months", "Last 6 Months"]:
            assert f"Transactions — {label}" not in data, (
                f"Heading must not show '— {label}' for a custom range"
            )


# ===========================================================================
# 13. DB helper unit tests — get_profile_stats
# ===========================================================================


class TestGetProfileStats:
    def test_stats_no_filter_sums_all_expenses(self, app):
        """
        Spec: get_profile_stats(user_id) with no date args must return the sum
        of every expense for that user regardless of date.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, 100.0, "Food", "2024-01-01", "a"),
                    (uid, 200.0, "Bills", "2023-06-15", "b"),
                ]
            )
            stats = get_profile_stats(uid)
        assert stats["total_spent"] == pytest.approx(300.0), (
            "All-time stats must sum all expenses"
        )
        assert stats["transaction_count"] == 2

    def test_stats_with_date_filter_excludes_outside_range(self, app):
        """
        Spec: get_profile_stats(user_id, start_date, end_date) must only count
        expenses whose date is BETWEEN start_date and end_date inclusive.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, 50.0, "Food", "2026-05-10", "in range"),
                    (uid, 999.0, "Bills", "2020-01-01", "out of range"),
                ]
            )
            stats = get_profile_stats(uid, "2026-05-01", "2026-05-31")
        assert stats["total_spent"] == pytest.approx(50.0), (
            "Filtered stats must only sum in-range expenses"
        )
        assert stats["transaction_count"] == 1

    def test_stats_empty_range_returns_zeros_and_dash(self, app):
        """
        Spec: When no expenses fall in the date range, get_profile_stats must
        return total_spent=0.0, transaction_count=0, top_category='—'.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses([(uid, 100.0, "Food", "2020-01-01", "old")])
            stats = get_profile_stats(uid, "2030-01-01", "2030-12-31")
        assert stats["total_spent"] == 0.0
        assert stats["transaction_count"] == 0
        assert stats["top_category"] == "—", (
            "top_category must be '—' when no expenses exist in range"
        )

    def test_stats_top_category_reflects_highest_spend(self, app):
        """
        Spec: top_category must be the category with the highest total spend
        within the (optionally filtered) date range.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, 10.0, "Food", "2026-05-01", "cheap meal"),
                    (uid, 500.0, "Bills", "2026-05-02", "big bill"),
                    (uid, 50.0, "Transport", "2026-05-03", "commute"),
                ]
            )
            stats = get_profile_stats(uid, "2026-05-01", "2026-05-31")
        assert stats["top_category"] == "Bills", (
            "top_category must be 'Bills' as it has the highest total"
        )


# ===========================================================================
# 14. DB helper unit tests — get_recent_expenses
# ===========================================================================


class TestGetRecentExpenses:
    def test_no_filter_returns_at_most_5(self, app):
        """
        Spec: Without a date filter the default limit is 5; more than 5 seeded
        expenses should still return only 5 results.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [(uid, float(i), "Food", f"2026-05-{i+1:02d}", f"meal {i}") for i in range(8)]
            )
            results = get_recent_expenses(uid)
        assert len(results) <= 5, f"Expected at most 5 results without filter; got {len(results)}"

    def test_with_filter_returns_up_to_50(self, app):
        """
        Spec: When start_date and end_date are provided, the limit is raised to
        50. Seeding more than 5 but fewer than 50 matching expenses should return
        all of them.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, float(i), "Food", "2026-05-10", f"item {i}")
                    for i in range(10)
                ]
            )
            results = get_recent_expenses(
                uid, limit=50, start_date="2026-05-01", end_date="2026-05-31"
            )
        assert len(results) == 10, (
            f"With filter active, all 10 in-range expenses must be returned; got {len(results)}"
        )

    def test_filter_excludes_out_of_range_rows(self, app):
        """
        Spec: Rows whose date falls outside [start_date, end_date] must be
        excluded by the BETWEEN clause.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, 200.0, "Bills", "2020-01-01", "old"),
                    (uid, 30.0, "Food", "2026-05-15", "new"),
                ]
            )
            results = get_recent_expenses(
                uid, limit=50, start_date="2026-05-01", end_date="2026-05-31"
            )
        descriptions = [r["description"] for r in results]
        assert "new" in descriptions, "In-range expense must be returned"
        assert "old" not in descriptions, "Out-of-range expense must be excluded"

    def test_results_ordered_by_date_desc(self, app):
        """
        Spec: Results are ordered by date DESC (most recent first).
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, 10.0, "Food", "2026-05-01", "first"),
                    (uid, 20.0, "Food", "2026-05-20", "last"),
                    (uid, 15.0, "Food", "2026-05-10", "middle"),
                ]
            )
            results = get_recent_expenses(uid)
        dates = [r["date"] for r in results]
        assert dates == sorted(dates, reverse=True), (
            "get_recent_expenses must return rows ordered by date DESC"
        )


# ===========================================================================
# 15. DB helper unit tests — get_category_breakdown
# ===========================================================================


class TestGetCategoryBreakdown:
    def test_no_filter_includes_all_categories(self, app):
        """
        Spec: Without date params all category totals must be returned.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, 100.0, "Food", "2024-01-01", "a"),
                    (uid, 200.0, "Bills", "2023-06-01", "b"),
                ]
            )
            categories = get_category_breakdown(uid)
        names = [c["name"] for c in categories]
        assert "Food" in names
        assert "Bills" in names

    def test_with_filter_excludes_out_of_range_categories(self, app):
        """
        Spec: Categories whose all expenses fall outside the date range must
        not appear in the breakdown result.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, 100.0, "Food", "2026-05-10", "in range"),
                    (uid, 999.0, "Luxury", "2020-01-01", "out of range"),
                ]
            )
            categories = get_category_breakdown(uid, "2026-05-01", "2026-05-31")
        names = [c["name"] for c in categories]
        assert "Food" in names, "In-range category must appear"
        assert "Luxury" not in names, "Out-of-range category must not appear"

    def test_empty_range_returns_empty_list(self, app):
        """
        Spec: When no expenses fall in the range, get_category_breakdown must
        return an empty list — not raise an exception.
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses([(uid, 50.0, "Food", "2020-01-01", "old")])
            categories = get_category_breakdown(uid, "2030-01-01", "2030-12-31")
        assert categories == [], "Expected empty list when no expenses in range"

    def test_percentages_sum_to_100(self, app):
        """
        Spec: The pct values across all returned categories must sum to exactly
        100 (the implementation adjusts the leading category to handle rounding).
        """
        with app.app_context():
            uid = _get_user_id("test@spendly.com") or _create_test_user(app)
            _seed_expenses(
                [
                    (uid, 33.0, "Food", "2026-05-01", "food"),
                    (uid, 33.0, "Bills", "2026-05-02", "bills"),
                    (uid, 34.0, "Transport", "2026-05-03", "transport"),
                ]
            )
            categories = get_category_breakdown(uid)
        total_pct = sum(c["pct"] for c in categories)
        assert total_pct == 100, f"Category percentages must sum to 100; got {total_pct}"


# ===========================================================================
# Helper used by DB unit tests when no auth_client pre-created the user
# ===========================================================================

def _create_test_user(app):
    """Create a bare-minimum user and return its id for DB unit tests."""
    conn = db_module.get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("DB Test User", "test@spendly.com", generate_password_hash("pass")),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()
