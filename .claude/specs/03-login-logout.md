# Spec: Login and Logout

## Overview
Implement session-based authentication for Spendora. This step converts the existing `/login` stub into a working POST handler that validates credentials against the database using `check_password_hash`, stores the authenticated user's ID in Flask's `session`, and redirects on success. It also implements the `/logout` stub to clear the session and redirect to the landing page. After this step, the app can distinguish between anonymous and authenticated visitors — a prerequisite for all protected routes in later steps.

## Depends on
- Step 01 — Database Setup (`get_db()`, `users` table, and `get_user_by_email()` must exist)
- Step 02 — Registration (a user must be creatable so login can be tested end-to-end)

## Routes
- `GET /login` — render the login form; if the user is already logged in redirect to `/profile` — public
- `POST /login` — validate email and password, set `session['user_id']` on success, redirect to `/profile`; re-render form with error on failure — public
- `GET /logout` — clear the session, redirect to `/` — logged-in

## Database changes
No schema changes. Add one helper function to `database/db.py`:
- `get_user_by_id(user_id)` — returns a `sqlite3.Row` or `None`; needed to load the current user from the session in future routes

## Templates
- **Modify:** `templates/login.html` — ensure the `<form>` has `method="POST"` and `action="/login"`; add `email` and `password` input fields; add an `{% if error %}` block to display validation errors; preserve the `email` value on re-render so the user does not have to retype it (do not repopulate `password`)
- **Modify:** `templates/base.html` — update the navigation to show a **Logout** link when `session.user_id` is set, and **Login** / **Register** links when it is not

## Files to change
- `app.py` — import `session` and `check_password_hash`; convert `login()` to handle GET and POST; implement `logout()` with `session.clear()`; add an already-logged-in redirect guard to the GET branch
- `database/db.py` — add `get_user_by_id(user_id)`
- `templates/login.html` — add POST form, error display, and email repopulation
- `templates/base.html` — add session-aware navigation links

## Files to create
None.

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` is already installed via Werkzeug.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with `werkzeug.security`; use `check_password_hash` to verify
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Store only `session['user_id']` (the integer PK) — never store the password or password hash in the session
- On failed login, pass a generic error ("Invalid email or password") — do not reveal which field was wrong
- On failed login, re-render `login.html` passing `error=<message>` and `email=<submitted_email>`
- Use `session.clear()` in logout — do not rely on `session.pop()` for individual keys
- The `secret_key` is already set in `app.py`; do not change it in this step

## Definition of done
- [ ] Visiting `GET /login` renders a form with `email` and `password` fields
- [ ] Submitting the form with an email that does not exist re-renders the form with an error message
- [ ] Submitting with a correct email but wrong password re-renders the form with an error message
- [ ] Submitting with valid credentials sets `session['user_id']` and redirects to `/profile`
- [ ] After login, visiting `GET /login` redirects to `/profile` instead of showing the form
- [ ] Visiting `GET /logout` clears the session and redirects to `/`
- [ ] After logout, `session['user_id']` is no longer present
- [ ] The navigation in `base.html` shows **Logout** when logged in and **Login** / **Register** when logged out
- [ ] The demo user (`demo@spendora.com` / `demo123`) can log in successfully
- [ ] No plain-text passwords are stored or logged anywhere
