# Spec: Registration

## Overview
Implement the user registration flow for Spendly. This step wires up the existing `register.html` template to a working `POST /register` handler that validates input, checks for duplicate emails, hashes the password, and inserts the new user into the database. After a successful registration the user is redirected to the login page. This is the first step that writes user data and establishes the `secret_key` needed for session management in later steps.

## Depends on
- Step 01 — Database Setup (users table and `get_db()` must exist)

## Routes
- `GET /register` — render the registration form — public (already exists, no change needed)
- `POST /register` — validate form fields, create user, redirect to `/login` on success or re-render form with error on failure — public

## Database changes
No schema changes. The `users` table already has all required columns (`id`, `name`, `email`, `password_hash`, `created_at`).

Add two helper functions to `database/db.py`:
- `create_user(name, email, password)` — hashes password, inserts row, returns new user id
- `get_user_by_email(email)` — returns a `sqlite3.Row` or `None`

## Templates
- **Modify:** `templates/register.html` — already renders `{% if error %}` block; no structural changes required. Ensure the `value` attribute on `name` and `email` inputs is repopulated on validation failure (pass them back via `render_template`).

## Files to change
- `app.py` — add `SECRET_KEY`, import `request` / `redirect` / `url_for` from Flask, convert `register()` to handle both GET and POST, add validation logic
- `database/db.py` — add `create_user()` and `get_user_by_email()`

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `SECRET_KEY` must be set on the Flask app before any session usage (use a hard-coded dev string for now; a comment should note it must be replaced in production)
- Validation order: (1) all fields present, (2) password ≥ 8 characters, (3) email not already registered
- On any validation failure, re-render `register.html` passing `error=<message>`, `name=<submitted_name>`, and `email=<submitted_email>` so the user does not have to retype

## Definition of done
- [ ] Submitting the form with all valid fields creates a new row in the `users` table with a hashed password
- [ ] Submitting with a missing field (name, email, or password) re-renders the form with a descriptive error message
- [ ] Submitting with a password shorter than 8 characters re-renders the form with an error
- [ ] Submitting with an email that is already registered re-renders the form with an error ("Email already in use")
- [ ] After successful registration the browser is redirected to `/login`
- [ ] The `name` and `email` inputs are repopulated when the form is re-rendered after a validation error
- [ ] The app starts without errors and `SECRET_KEY` is configured
- [ ] No plain-text passwords are stored in the database
