# Spec: Date Filter for Profile Page

## Overview
Add a date-range filter to the `/profile` page so users can slice their expense data by
time period. Currently all three data sections — summary stats, recent transactions, and
category breakdown — show all-time totals with no way to narrow the view. This step
introduces a filter bar with preset period shortcuts (This Month, Last Month, Last 3
Months, Last 6 Months, All Time) plus an optional custom date-range picker. The active
filter is passed as query parameters (`?start=YYYY-MM-DD&end=YYYY-MM-DD`), the three
existing DB helper functions gain optional `start_date`/`end_date` parameters, and the
profile template gains a filter UI that highlights the active period and re-renders all
three sections for the selected range.

## Depends on
- Step 01 — Database Setup (`expenses` table with `date TEXT` column must exist)
- Step 02 — Registration (a user with expenses must be creatable)
- Step 03 — Login and Logout (`g.user`, `login_required` must exist)
- Step 04 — Profile Page (`profile.html` layout and variable names must exist)
- Step 05 — Backend Routes for Profile Page (live DB queries and the three helper
  functions must be in place — this step extends them)

## Routes
No new routes. The existing route is extended:
- `GET /profile` — accepts optional `?start=YYYY-MM-DD&end=YYYY-MM-DD` query params;
  returns filtered data when params are present, all-time data when absent — logged-in only

## Database changes
No new tables or columns. The existing `expenses.date` column (stored as `TEXT` in
`YYYY-MM-DD` format) supports SQLite string-comparison range queries directly.

The three existing helper functions in `database/db.py` are extended with optional
parameters:

- `get_profile_stats(user_id, start_date=None, end_date=None)` — adds `WHERE date
  BETWEEN ? AND ?` clause when both params are provided
- `get_recent_expenses(user_id, limit=5, start_date=None, end_date=None)` — adds the
  same date range clause before `ORDER BY`; when a filter is active the `limit` cap is
  raised to 50 so users see all matching rows, not just 5
- `get_category_breakdown(user_id, start_date=None, end_date=None)` — adds the date
  range clause to the aggregation query

## Templates
- **Modify:** `templates/profile.html`
  - Add a filter bar above the stats row containing five preset buttons:
    `This Month`, `Last Month`, `Last 3 Months`, `Last 6 Months`, `All Time`
  - Each preset button is an `<a>` tag whose `href` encodes the corresponding
    `?start=…&end=…` query string (or bare `/profile` for All Time)
  - The active preset button receives an `active` CSS class
  - Add a collapsible custom date-range form with `start` and `end` `<input type="date">`
    fields and a Submit button; the form uses `method="GET"` and `action="/profile"`
  - The section heading above the transactions table changes to reflect the active period
    (e.g. "Transactions — May 2026" or "Transactions — All Time")
  - No structural changes to the stats row, transaction table, or category breakdown —
    they already use template variables that will simply receive filtered data

## Files to change
- `database/db.py` — extend `get_profile_stats()`, `get_recent_expenses()`, and
  `get_category_breakdown()` with optional `start_date`/`end_date` parameters
- `app.py` — read `start` and `end` query params in the `profile()` view; compute preset
  `start`/`end` date strings server-side for the five presets; pass them plus an
  `active_period` label to the template; forward the date args to all three DB helpers
- `templates/profile.html` — add filter bar, preset buttons, custom date-range form,
  and dynamic section heading as described above

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()` only
- Parameterised queries only — never use string formatting in SQL; date values passed
  via `?` placeholders
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Date arithmetic for preset ranges must be computed in `app.py` using Python's
  `datetime` / `date` stdlib — no third-party date libraries
- When `start` or `end` is missing or malformed, fall back to all-time data silently
  (no 400 error); validate format with a `try/except` around `datetime.strptime`
- The `limit` in `get_recent_expenses` must be raised to 50 (not 5) when a date filter
  is active so users see all matching rows for the selected period
- The "All Time" preset must link to bare `/profile` (no query params) — never pass
  `start=` and `end=` for the all-time view
- Active preset detection: compare parsed `start`/`end` to each preset's computed range;
  if no preset matches (custom range), highlight nothing
- Filter bar preset buttons must be `<a>` tags, not `<form>` submits, so the URL is
  bookmarkable

## Definition of done
- [ ] Visiting `/profile` with no query params shows all-time data (same as Step 05)
- [ ] Clicking "This Month" reloads the page with `?start=YYYY-MM-01&end=YYYY-MM-DD`
  and stats/transactions/categories reflect only that month's expenses
- [ ] Clicking "Last Month" shows only the previous calendar month's data
- [ ] Clicking "Last 3 Months" shows the past ~90 days of data
- [ ] Clicking "Last 6 Months" shows the past ~180 days of data
- [ ] Clicking "All Time" removes the query params and shows all-time data
- [ ] The active preset button is visually highlighted (has the `active` CSS class)
- [ ] The custom date-range form submits `?start=…&end=…` and filters data to that range
- [ ] The transactions section heading reflects the active period label
- [ ] A user with no expenses in the selected range sees `₹0.00`, `0 transactions`, `—`
  for top category, and empty lists — no crashes or template errors
- [ ] Passing a malformed date (e.g. `?start=notadate`) falls back to all-time data
  without raising an unhandled exception
- [ ] No raw SQL string formatting in any of the modified DB helper functions
- [ ] No hardcoded hex colour values in `profile.html`
