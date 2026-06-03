# Spec: Login and Logout

## Overview
Implement the login and logout flows for Spendly. The `/login` route currently only handles
GET requests and renders the form without processing credentials. This step wires up the
POST handler: validates the submitted email and password against the database using
`check_password_hash`, stores the authenticated user's ID in Flask's server-side session,
and redirects to the dashboard on success. The `/logout` route is converted from its
placeholder to a real handler that clears the session and redirects to the landing page.
A `login_required` decorator is introduced so future steps can protect routes with a single
line. A `get_user_by_id()` helper is added to `database/db.py` so the session user can be
resolved to a full user record inside `before_request`.

## Depends on
- Step 01 — Database Setup (`users` table and `get_db()` must exist)
- Step 02 — Registration (`get_user_by_email()` and `create_user()` must exist; `app.secret_key` must be set)

## Routes
- `GET  /login`  — render the empty login form — public
- `POST /login`  — validate credentials; on success set session and redirect to `/`; on error re-render form with error message and pre-filled email — public
- `GET  /logout` — clear session, redirect to `/` — logged-in (redirect silently if already logged out)

## Database changes
No new tables or columns.

One new helper function required in `database/db.py`:

- `get_user_by_id(user_id)` — returns a `sqlite3.Row` for the matching user, or `None`

## Templates
- **Modify:** `templates/login.html`
  - The form `action` must POST to `/login`
  - Pre-fill the `email` input with the previously submitted value on re-render after error
  - Show an `{% if error %}` block with the error message (same pattern as `register.html`)

- **Modify:** `templates/base.html`
  - Show a "Logout" link in the nav when `g.user` is set
  - Show "Login" and "Register" links in the nav when `g.user` is not set

## Files to change
- `app.py`
  - Add `session, g` to the Flask import
  - Add `check_password_hash` to the werkzeug import
  - Add `get_user_by_id` to the `database.db` import
  - Add a `before_request` hook that loads `g.user` from `session['user_id']` (or sets it to `None`)
  - Add a `login_required` decorator that redirects to `/login` if `g.user` is `None`
  - Convert `login()` to accept `GET` and `POST`; on POST validate email/password and set `session['user_id']`
  - Convert `logout()` from placeholder to a real handler that calls `session.clear()` and redirects to `/`

- `database/db.py`
  - Add `get_user_by_id(user_id)` helper

- `templates/login.html`
  - Pre-fill email on re-render; add error display block; ensure form posts to `/login`

- `templates/base.html`
  - Conditional nav links based on `g.user`

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plain text
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- The session must only store `session['user_id']` (the integer primary key) — never store the full user dict or the password hash in the session
- `g.user` is populated in `before_request` via `get_user_by_id(session.get('user_id'))`; it is `None` when no user is logged in
- Login error message must be generic: "Invalid email or password." — do not reveal which field was wrong
- On login success: `redirect(url_for('landing'))` (the `/` route) — redirect target can be expanded to a real dashboard in a later step
- `login_required` must redirect to `/login` and must not expose the protected route's URL in the query string at this stage

## Definition of done
- [ ] Submitting valid credentials sets a session and redirects to `/`
- [ ] The nav shows "Logout" after a successful login
- [ ] Submitting an email that does not exist shows "Invalid email or password."
- [ ] Submitting a correct email but wrong password shows "Invalid email or password."
- [ ] Submitting with a blank email or blank password shows a validation error
- [ ] Previously entered email is pre-filled when the login form re-renders after an error
- [ ] Visiting `/logout` clears the session and redirects to `/`
- [ ] The nav shows "Login" and "Register" after logout
- [ ] Visiting `/logout` when already logged out redirects silently without error
- [ ] `g.user` is accessible in all templates via `before_request`
- [ ] No raw SQL string formatting anywhere in the new code
