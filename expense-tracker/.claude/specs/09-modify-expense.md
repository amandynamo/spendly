# Spec: Modify Expense

## Overview
Allow logged-in users to edit an existing expense they own. From the profile page,
each expense row gains an "Edit" link that navigates to a pre-filled form. On submit,
the server validates the input, verifies ownership, updates the database row, and
redirects back to the profile with a success flash. This completes the full CRUD
lifecycle for expenses (Create in Step 07, Delete in Step 08, Update here) and
replaces the placeholder stub at `GET /expenses/<id>/edit`.

## Depends on
- Step 01 — Database Setup (`expenses` table must exist)
- Step 03 — Login and Logout (`g.user`, `login_required` decorator must exist)
- Step 05 — Backend Routes for Profile Page (profile page and transactions list must exist)
- Step 07 — Add Expense (`insert_expense`, `VALID_CATEGORIES`, and the add-expense form must exist)
- Step 08 — Delete Existing Expense (expense `id` is already exposed in `get_recent_expenses`)

## Routes
- `GET /expenses/<int:id>/edit` — render the pre-filled edit form for expense `id` — logged-in only
- `POST /expenses/<int:id>/edit` — validate and apply the update, redirect to `/profile` — logged-in only

The existing placeholder `GET /expenses/<int:id>/edit` stub in `app.py` must be
**replaced** with a full two-method handler.

## Database changes
No new tables or columns.

One new helper in `database/db.py`:

1. **`get_expense_by_id(expense_id, user_id)`** — fetch the single expense row where
   `id = ?` AND `user_id = ?`. Returns a `dict` or `None` if not found / wrong owner.

2. **`update_expense(expense_id, user_id, amount, category, date, description)`** —
   updates `amount`, `category`, `date`, `description` for the row where `id = ?` AND
   `user_id = ?`. Returns the number of rows updated (0 or 1). The `user_id` check is
   the ownership guard.

## Templates
- **Create:** `templates/edit_expense.html`
  - Extends `base.html`
  - Form with `method="POST"` and `action="/expenses/{{ expense.id }}/edit"`
  - Pre-filled fields: `amount`, `category` (select with `VALID_CATEGORIES`), `date`, `description`
  - Inline error display (same pattern as `add_expense.html`)
  - Cancel link back to `/profile`
  - Styling must use CSS variables only — no hardcoded hex values

- **Modify:** `templates/profile.html`
  - Add an "Edit" link to each expense row alongside the existing delete button:
    ```html
    <a href="/expenses/{{ t.id }}/edit">Edit</a>
    ```

## Files to change
- `app.py`
  - Replace the placeholder `edit_expense` route with a full GET/POST handler:
    - `GET`: call `get_expense_by_id(id, g.user['id'])`; if `None`, flash an error and
      redirect to `/profile`; otherwise render `edit_expense.html` with the expense data
      and `VALID_CATEGORIES`
    - `POST`: validate `amount` (float > 0), `category` (in `VALID_CATEGORIES`), `date`
      (parseable as `%Y-%m-%d`); on failure re-render the form with errors; on success
      call `update_expense(...)`, flash `'Expense updated successfully!'` with category
      `'success'`, and redirect to `/profile`
    - Add `methods=["GET", "POST"]` and `@login_required` to the route decorator
  - Update the import from `database.db` to include `get_expense_by_id` and
    `update_expense`

- `database/db.py`
  - Add `get_expense_by_id(expense_id, user_id)` helper
  - Add `update_expense(expense_id, user_id, amount, category, date, description)` helper

- `templates/profile.html`
  - Add per-row edit link in the transactions list

## Files to create
- `templates/edit_expense.html` — the edit form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()` only
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Both `get_expense_by_id` and `update_expense` **must** filter by both `id` AND
  `user_id` — omitting `user_id` from the WHERE clause would allow cross-user access
- The `GET` route must return a 404-equivalent redirect (not a blank form) if the
  expense does not exist or belongs to another user
- Re-use `VALID_CATEGORIES` from `app.py` — do not duplicate the list
- Description field must be trimmed and capped at 200 characters (same as add)
- Amount must be rounded to 2 decimal places before storing

## Definition of done
- [ ] An "Edit" link appears on each expense row in the profile transactions list
- [ ] Clicking the edit link opens a form pre-filled with the expense's current values
- [ ] Submitting valid changes updates the expense in the database and redirects to `/profile`
- [ ] The updated values are immediately visible in the profile transactions list
- [ ] Invalid amount (non-numeric, zero, negative) shows an inline error without losing other field values
- [ ] Invalid category shows an inline error
- [ ] Invalid date shows an inline error
- [ ] Attempting to edit an expense belonging to another user redirects to `/profile` with an error flash (no data leaked)
- [ ] Unauthenticated users hitting `GET` or `POST /expenses/<id>/edit` are redirected to `/login`
- [ ] No raw SQL string formatting in any new DB helpers
- [ ] No hardcoded hex colour values in `edit_expense.html` or `profile.html`
- [ ] Flash message confirms the update on the profile page
