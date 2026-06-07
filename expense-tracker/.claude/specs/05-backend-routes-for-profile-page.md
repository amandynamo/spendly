# Spec: Backend Routes for Profile Page

## Overview
Replace all hardcoded data in the `/profile` route with real database queries. Step 04
built the complete profile UI using static Python dicts as stand-ins. This step wires
that UI to live data: the logged-in user's name, email, and join date come from the
`users` table; the summary stats (total spent, transaction count, top category) and the
recent transaction list are aggregated from the `expenses` table; and the category
breakdown is computed per-category for the current user. Three new helper functions are
added to `database/db.py` to keep all SQL out of `app.py`. The `$` currency symbol in
`profile.html` is corrected to `₹` as part of this step.

## Depends on
- Step 01 — Database Setup (`users` and `expenses` tables must exist; `get_db()` must work)
- Step 02 — Registration (users must be creatable)
- Step 03 — Login and Logout (`g.user`, `session['user_id']`, and `login_required` must exist)
- Step 04 — Profile Page (the `profile.html` template and its variable names must already exist)

## Routes
No new routes. The existing `GET /profile` route is modified in place:
- `GET /profile` — render the profile page with live DB data — logged-in only

## Database changes
No new tables or columns. The existing `users` and `expenses` tables are sufficient.

Three new helper functions are required in `database/db.py`:

- `get_profile_stats(user_id)` — returns a dict with keys:
  - `total_spent` (REAL): `SUM(amount)` for the user; `0.0` if no expenses
  - `transaction_count` (INTEGER): `COUNT(*)` for the user; `0` if no expenses
  - `top_category` (TEXT): the category with the highest `SUM(amount)`; `'—'` if no expenses

- `get_recent_expenses(user_id, limit=5)` — returns a list of dicts (most recent first), each with:
  - `date`, `description`, `category`, `amount`
  - ordered by `date DESC`, then `id DESC` (stable tie-break)

- `get_category_breakdown(user_id)` — returns a list of dicts ordered by `total DESC`, each with:
  - `name` (category name), `total` (SUM of amount), `pct` (integer percentage of grand total)
  - only categories that have at least one expense for this user are included
  - `pct` values must sum to 100 (apply rounding correction to the largest category if needed)

## Templates
- **Modify:** `templates/profile.html`
  - Replace all `$` currency symbols with `₹`
  - No structural changes required; all Jinja variable names remain the same as Step 04

## Files to change
- `database/db.py` — add `get_profile_stats()`, `get_recent_expenses()`, `get_category_breakdown()`
- `app.py` — import the three new helpers; replace the hardcoded dicts in `profile()` with real DB calls; derive `member_since` from `g.user['created_at']` (format as `"Month YYYY"`, e.g. `"January 2024"`)
- `templates/profile.html` — replace `$` with `₹` throughout

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
- `get_profile_stats()`, `get_recent_expenses()`, and `get_category_breakdown()` must each open and close their own DB connection (use try/finally with `conn.close()`)
- Return safe defaults (`0`, `0.0`, `[]`, `'—'`) when the user has no expenses — never let a missing row cause a `TypeError` in the template
- `member_since` must be derived from `g.user['created_at']` in `app.py`, not hardcoded; use `datetime.strptime` / `strftime` to format it
- The `pct` field in `get_category_breakdown()` must be an integer (not float) so the template can render it directly in a `style="width: {{ cat.pct }}%"` or similar attribute

## Definition of done
- [ ] Visiting `/profile` while logged in shows the real user's name and email (not "Alex Johnson")
- [ ] The "Member since" field reflects the actual `created_at` value from the `users` table
- [ ] "Total Spent" stat matches the actual `SUM(amount)` for that user's expenses
- [ ] "Transactions" count matches the actual `COUNT(*)` for that user's expenses
- [ ] "Top Category" shows the category with the highest total spend for that user
- [ ] The recent transactions table shows real rows from the `expenses` table (most recent first)
- [ ] The category breakdown lists only categories the user has actually spent in
- [ ] A brand-new user with zero expenses sees `₹0.00`, `0 transactions`, `—` for top category, and empty lists — no crashes or template errors
- [ ] All currency values display `₹` not `$`
- [ ] No hardcoded user data remains in `app.py`'s `profile()` function
- [ ] No raw SQL string formatting in any of the new DB helper functions
