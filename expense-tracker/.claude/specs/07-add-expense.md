# Spec: Add Expense

## Overview
Implement the Add Expense feature so logged-in users can record a new spending entry
via a form at `/expenses/add`. The route currently returns a placeholder string — this
step replaces it with a full GET/POST handler. On GET, the form is rendered; on POST,
the submitted data is validated and inserted into the existing `expenses` table, then
the user is redirected to `/profile`. This is the first write-path feature in Spendly
and completes the core expense-entry loop started by the database setup in Step 01.

## Depends on
- Step 01 — Database Setup (`expenses` table with all columns must exist)
- Step 03 — Login and Logout (`g.user`, `login_required` decorator must exist)
- Step 05 — Backend Routes for Profile Page (profile page exists to redirect to after save)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert the new expense; redirect to `/profile` on
  success, re-render the form with an error message on failure — logged-in only

## Database changes
No new tables or columns. The existing `expenses` table already has all required
columns: `id`, `user_id`, `amount`, `category`, `date`, `description`, `created_at`.

One new DB helper function is added to `database/db.py`:
- `add_expense(user_id, amount, category, date, description)` — inserts a row into
  the `expenses` table using parameterised queries; returns the new row's `id`.

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`
  - Contains a form with `method="POST"` and `action="/expenses/add"`
  - Fields:
    - `amount` — number input, step="0.01", min="0.01", required
    - `category` — select with fixed options: Food, Transport, Bills, Health,
      Entertainment, Shopping, Other; required
    - `date` — date input, defaults to today's date, required
    - `description` — text input, optional, max 200 characters
  - A submit button labelled "Add Expense"
  - Displays an `error` variable when present (inline above the form)
  - Re-populates field values on validation failure (sticky form)

## Files to change
- `app.py` — replace the placeholder `add_expense` route with a full GET/POST handler:
  - Add `login_required` decorator
  - GET: render `add_expense.html` with today's date pre-filled
  - POST: read and validate form fields, call `add_expense()` DB helper on success,
    redirect to `/profile`; re-render form with error on failure
- `database/db.py` — add `add_expense(user_id, amount, category, date, description)`
  helper function
- `app.py` imports — add `add_expense` to the import from `database.db`

## Files to create
- `templates/add_expense.html` — the add-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()` only
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- The route must be protected with `login_required`
- `amount` must be cast to `float` and validated to be greater than 0; reject
  non-numeric input with a user-friendly error message
- `category` must be validated against the fixed allowed list — reject any value
  not in `['Food', 'Transport', 'Bills', 'Health', 'Entertainment', 'Shopping', 'Other']`
- `date` must be validated as a real `YYYY-MM-DD` date using `datetime.strptime`;
  reject malformed dates with an error message
- `description` is optional — store empty string as `None` (or omit); never crash
  on a missing description field
- On POST validation failure, re-render the form with the error and re-populate all
  previously submitted values so the user does not lose their input
- On success, redirect to `/profile` using `redirect(url_for('profile'))`
- The `date` input on GET should default to today's date (`date.today().isoformat()`)

## Definition of done
- [ ] `GET /expenses/add` renders the form for a logged-in user
- [ ] `GET /expenses/add` redirects unauthenticated users to `/login`
- [ ] The date field is pre-filled with today's date on GET
- [ ] Submitting valid data inserts a row into the `expenses` table and redirects to
  `/profile`
- [ ] The new expense appears in the transactions list on `/profile` after submission
- [ ] Submitting with a missing or zero amount shows an error and re-renders the form
- [ ] Submitting with a non-numeric amount shows an error and re-renders the form
- [ ] Submitting with an invalid category shows an error and re-renders the form
- [ ] Submitting with a malformed date shows an error and re-renders the form
- [ ] All valid field values are re-populated in the form after a validation failure
- [ ] No raw SQL string formatting in `add_expense()` DB helper
- [ ] No hardcoded hex colour values in `add_expense.html`
