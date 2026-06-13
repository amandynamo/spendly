# Spec: Delete Existing Expense

## Overview
Allow logged-in users to delete one of their own expenses directly from the profile
page. Each expense row in the transactions list gains a delete button that submits a
small POST form; the server verifies ownership, removes the row from the database, and
redirects back to the profile with a confirmation flash message. This completes the
basic CRUD lifecycle for expenses started in Step 07 and is a prerequisite for any
future edit/update flow.

## Depends on
- Step 01 — Database Setup (`expenses` table must exist)
- Step 03 — Login and Logout (`g.user`, `login_required` decorator must exist)
- Step 05 — Backend Routes for Profile Page (profile page and transactions list must exist)
- Step 07 — Add Expense (`insert_expense` and the expense data flow must be in place)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense with the given id if it belongs
  to the logged-in user; redirect to `/profile` — logged-in only

The existing `GET /expenses/<int:id>/delete` stub must be **replaced** with a POST-only
route. Using GET for a destructive action is unsafe (bookmarks, prefetch, link-preview
crawlers can trigger it unintentionally).

## Database changes
No new tables or columns.

Two changes to `database/db.py`:

1. **New helper** `delete_expense(expense_id, user_id)` — deletes the row from
   `expenses` where `id = ?` AND `user_id = ?` using parameterised queries. The
   `user_id` check is the ownership guard; it means a user can never delete another
   user's record even if they guess the id. Returns the number of rows deleted (0 or 1).

2. **Modify `get_recent_expenses`** — the current SELECT omits `id`; add it so the
   profile template can render per-row delete forms. Change:
   ```sql
   SELECT date, description, category, amount
   ```
   to:
   ```sql
   SELECT id, date, description, category, amount
   ```

## Templates
- **Modify:** `templates/profile.html`
  - In the transactions table/list, add a delete form to each row:
    ```html
    <form method="POST" action="/expenses/{{ t.id }}/delete">
      <button type="submit">Delete</button>
    </form>
    ```
  - The button styling must use CSS variables only — no hardcoded hex values.
  - No new templates needed.

## Files to change
- `app.py`
  - Replace the placeholder `delete_expense` route with a proper `POST`-only handler:
    - Add `methods=["POST"]` to the route decorator
    - Add `@login_required` decorator
    - Call `delete_expense(id, g.user['id'])` from `database.db`
    - On success (1 row deleted): flash `'Expense deleted.'` with category `'success'`
      and redirect to `/profile`
    - On failure (0 rows deleted — id not found or wrong owner): flash
      `'Expense not found.'` with category `'error'` and redirect to `/profile`
  - Update the import from `database.db` to include `delete_expense`

- `database/db.py`
  - Add `delete_expense(expense_id, user_id)` helper
  - Update `get_recent_expenses` SELECT to include `id`

- `templates/profile.html`
  - Add per-row delete form buttons in the transactions list

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()` only
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- The route **must** use `POST`, not `GET` — destructive actions must never be triggered
  by a GET request
- The `delete_expense` DB helper **must** filter by both `id` AND `user_id` — this is
  the only ownership check; omitting `user_id` from the WHERE clause would be a
  security vulnerability
- Do not redirect to a confirmation page — delete immediately on POST and flash a
  message on the profile page

## Definition of done
- [ ] A delete button is visible on each expense row in the profile transactions list
- [ ] Clicking delete submits a POST form (not a GET link)
- [ ] A deleted expense no longer appears in the transactions list after the redirect
- [ ] The profile stats (total spent, transaction count) update correctly after deletion
- [ ] Attempting to delete an expense that belongs to another user returns no error to
  the attacker and does not delete the row (ownership check enforced)
- [ ] Attempting to delete a non-existent id redirects to `/profile` with an error flash
- [ ] Unauthenticated users hitting `POST /expenses/<id>/delete` are redirected to `/login`
- [ ] No raw SQL string formatting in `delete_expense()` DB helper
- [ ] No hardcoded hex colour values added to `profile.html`
- [ ] Flash message confirms the deletion on the profile page
