# Spec: Registration

## Overview
Implement the user registration flow for Spendly. The `/register` route currently renders
the form but discards all POST data. This step wires up the form submission: validates
inputs, rejects duplicate emails, hashes the password, inserts the new user into the
`users` table, and redirects to the login page on success. It also adds the two
`database/db.py` helpers (`create_user` and `get_user_by_email`) that both this step and
the future login step depend on.

## Depends on
- Step 01 — Database Setup (users table must exist; `get_db()` must be working)

## Routes
- `GET /register` — render the empty registration form — public
- `POST /register` — process form submission; on success redirect to `/login`; on error
  re-render the form with an error message and the previously entered name/email — public

## Database changes
No new tables or columns. The `users` table created in Step 01 is sufficient.

Two new helper functions are required in `database/db.py`:

- `get_user_by_email(email)` — returns a `sqlite3.Row` for the matching user, or `None`
- `create_user(name, email, password_hash)` — inserts a row and returns the new `user_id`

## Templates
- **Modify:** `templates/register.html`
  - Pre-fill `name` and `email` inputs with previously submitted values when re-rendering
    after a validation error (prevents the user from retyping everything)
  - No structural changes needed; `{% if error %}` block already present

## Files to change
- `app.py` — add `request`, `redirect`, `url_for` to Flask imports; add `app.secret_key`;
  convert `register()` to accept `GET` and `POST`; add validation and DB logic
- `database/db.py` — add `get_user_by_email()` and `create_user()`
- `templates/register.html` — pre-fill name/email on re-render

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` before being stored;
  the raw password must never be written to the database
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Validate server-side (do not rely solely on HTML `required` attributes):
  - All three fields must be non-empty after stripping whitespace
  - Password must be at least 8 characters
  - Email must not already exist in `users` (checked via `get_user_by_email`)
- On validation failure: re-render `register.html` with `error=<message>` and pass back
  `name` and `email` so inputs stay filled
- On success: `redirect(url_for('login'))` — do not auto-login (that is Step 03)
- `app.secret_key` should be set in `app.py` (required by Flask for session/redirect
  infrastructure; use a hard-coded dev string for now — e.g. `"dev-secret-change-me"`)

## Definition of done
- [ ] Submitting the form with all valid fields creates a new row in `users` and redirects
      to `/login`
- [ ] The stored password is a werkzeug hash, not the plain-text value
- [ ] Submitting with an email that already exists shows an error message on the page
      without losing the entered name/email values
- [ ] Submitting with an empty name, email, or password shows a validation error
- [ ] Submitting with a password shorter than 8 characters shows a validation error
- [ ] The demo user created by `seed_db()` cannot be re-registered (duplicate email check
      works for existing rows too)
- [ ] The `/register` page still loads correctly via GET after the changes
- [ ] No raw SQL string formatting anywhere in the new code
