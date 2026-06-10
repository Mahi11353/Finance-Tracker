# ◈ Spendly — Personal Expense Tracker

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.1.3-black?style=flat-square&logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite)
![Werkzeug](https://img.shields.io/badge/Werkzeug-3.1.6-red?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)

> **Track every rupee. Own your finances.**

Spendly is a full-stack personal finance web application built with Flask and SQLite. It lets users register, log in, add and manage expenses across categories, track their account balance, and analyse spending patterns through a clean dashboard — all without touching a spreadsheet.

This project was built incrementally using a spec-driven, AI-assisted workflow with Claude Code, following feature-branch development practices throughout.

---

## 📸 Screenshots

| Landing Page | Dashboard |
|---|---|
| *(screenshot placeholder — `docs/screenshots/landing.png`)* | *(screenshot placeholder — `docs/screenshots/dashboard.png`)* |

| Add Expense Form | Category Breakdown |
|---|---|
| *(screenshot placeholder — `docs/screenshots/add-expense.png`)* | *(screenshot placeholder — `docs/screenshots/categories.png`)* |

---

## ✨ Features

- **User registration and login** — email + password accounts with secure Werkzeug hashing
- **Session-based authentication** — server-side sessions that protect every route
- **CSRF protection** — token injected per session, validated on every state-changing form
- **Expense management** — add, edit, and delete expenses with full validation
- **7 fixed categories** — Food, Transport, Bills, Health, Entertainment, Shopping, Other
- **Account balance tracking** — set a starting balance; it auto-adjusts on every expense add, edit, or delete
- **Analytics dashboard** — total spent, transaction count, and top spending category at a glance
- **Category breakdown** — visual progress-bar breakdown of spending by category
- **Date range filtering** — preset shortcuts (This Month, Last 3 Months, Last 6 Months) plus a custom date-range picker
- **Recent transactions table** — formatted, ordered transaction list with inline edit and delete
- **Responsive UI** — mobile-friendly layout using custom CSS with CSS variables
- **Demo seed data** — auto-seeded demo user and sample expenses on first run
- **Landing page** — marketing-style hero section with feature cards and a demo modal
- **Legal pages** — Terms & Conditions and Privacy Policy routes

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11+, Flask 3.1.3 |
| **Database** | SQLite 3 (via Python `sqlite3` standard library) |
| **Authentication** | Flask sessions, Werkzeug `generate_password_hash` / `check_password_hash` |
| **Templating** | Jinja2 (via Flask) |
| **Frontend** | Vanilla HTML5, CSS3 (custom), vanilla JavaScript |
| **Typography** | Google Fonts — DM Serif Display + DM Sans |
| **WSGI Server** | Gunicorn 26.0.0 (production) |
| **Testing** | pytest 8.3.5, pytest-flask 1.3.0, Playwright 1.60.0 |
| **Dev Tooling** | Claude Code, custom slash commands, spec-driven workflow |

---

## 🗂️ Project Architecture

```
expense-tracker/
│
├── app.py                   # Flask app factory, all route handlers
├── requirements.txt         # Pinned Python dependencies
├── spendly.db               # SQLite database (auto-created on first run)
│
├── database/
│   ├── __init__.py
│   ├── db.py                # Connection helper, schema init, seed data, user CRUD
│   └── queries.py           # Expense CRUD + analytics queries (stats, breakdown)
│
├── templates/
│   ├── base.html            # Shared layout: navbar, footer, flash messages
│   ├── landing.html         # Public marketing / hero page
│   ├── register.html        # Registration form
│   ├── login.html           # Login form
│   ├── profile.html         # User dashboard (stats, transactions, categories)
│   ├── add_expense.html     # Add-expense form
│   ├── edit_expense.html    # Edit-expense form
│   ├── terms.html           # Terms & Conditions
│   └── privacy.html         # Privacy Policy
│
├── static/
│   ├── css/
│   │   ├── style.css        # Global styles, design tokens, navbar, landing
│   │   └── profile.css      # Dashboard-specific styles
│   └── js/
│       └── main.js          # Client-side interactions (modals, etc.)
│
└── .claude/
    ├── specs/               # 9 Claude-generated markdown feature specs
    ├── commands/            # Custom slash commands (seed-user, seed-expense, etc.)
    ├── agents/              # Specialized sub-agents (test-writer, reviewer, etc.)
    └── settings.json        # Claude Code project configuration
```

### How the layers interact

```
Browser Request
      │
      ▼
 app.py (Flask routes)
      │  reads session, validates input
      ▼
 database/db.py          ←→   spendly.db (SQLite file)
      │  get_db(), get_user_by_email(), create_user()
      ▼
 database/queries.py
      │  get_summary_stats(), get_recent_transactions(),
      │  get_category_breakdown(), insert/update/delete_expense()
      ▼
 Jinja2 Templates (templates/*.html)
      │  extends base.html, renders data passed by the route
      ▼
 Browser Response (HTML + static CSS/JS)
```

- `database/db.py` owns connection management and user-level operations.
- `database/queries.py` owns all expense-level reads and writes, plus the analytics aggregations shown on the dashboard.
- `app.py` is the sole entry point for all HTTP routes — it orchestrates auth checks, calls database helpers, and passes data to templates.
- Templates inherit from `base.html` which provides the navbar (auth-aware), footer, and flash message display.

---

## ⚙️ Installation Guide

### Prerequisites

- Python **3.11 or higher**
- `pip` (comes with Python)
- `git`

### 1 — Clone the repository

```bash
git clone https://github.com/<your-username>/expense-tracker.git
cd expense-tracker
```

### 2 — Create a virtual environment

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### 4 — Run the development server

```bash
python app.py
```

Open your browser at **http://127.0.0.1:5001**

> The database is created and seeded automatically on the first run. A demo account (`demo@spendly.com` / `demo123`) is available immediately.

---

## 🌱 Environment Setup

| Variable | Default | Purpose |
|---|---|---|
| `FLASK_DEBUG` | `false` | Set to `true` to enable debug mode and auto-reload |
| `SECRET_KEY` | hardcoded dev value | **Must be overridden in production** — used to sign sessions |

Example `.env` for production:

```bash
FLASK_DEBUG=false
SECRET_KEY=your-random-64-char-secret-here
```

> **Note:** The current `app.secret_key` in `app.py` is a development placeholder. Replace it with `os.environ.get("SECRET_KEY")` before deploying.

### Python version

```bash
python --version   # should be 3.11 or higher
```

### Verify the installation

```bash
pip list | grep Flask   # should show Flask 3.1.3
```

---

## 🗄️ Database Setup

Spendly uses **SQLite** — a file-based, serverless database. No external database server is needed.

### How it works

On every app startup, `app.py` calls:

```python
with app.app_context():
    init_db()   # Creates tables if they don't exist
    seed_db()   # Inserts demo data only if the users table is empty
```

### Schema

**`users` table**

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key, autoincrement |
| `name` | TEXT | Full name, not null |
| `email` | TEXT | Unique, not null |
| `password_hash` | TEXT | Werkzeug PBKDF2 hash |
| `balance` | REAL | Default 0, auto-adjusted by expenses |
| `created_at` | TEXT | UTC datetime string |

**`expenses` table**

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key, autoincrement |
| `user_id` | INTEGER | Foreign key → `users.id` |
| `amount` | REAL | Positive float, max ₹10,00,000 |
| `category` | TEXT | One of 7 fixed categories |
| `date` | TEXT | YYYY-MM-DD format |
| `description` | TEXT | Optional, max 200 chars |
| `created_at` | TEXT | UTC datetime string |

### Database file location

```
expense-tracker/
└── spendly.db    ← auto-created here on first run
```

To reset the database completely:

```bash
# Delete the file and restart the server — it will be recreated and re-seeded
rm spendly.db
python app.py
```

---

## 🔐 Authentication Flow

### Registration (`POST /register`)

1. User submits name, email, and password.
2. Server validates all fields are present and password is ≥ 8 characters.
3. Email uniqueness is checked against the `users` table.
4. Password is hashed with Werkzeug's `generate_password_hash` (PBKDF2-SHA256).
5. New user row is inserted; user is redirected to login.

### Login (`POST /login`)

1. User submits email and password.
2. Server fetches the user row by email.
3. `check_password_hash(stored_hash, submitted_password)` validates credentials.
4. On success, `session["user_id"] = user["id"]` is set.
5. User is redirected to `/profile`.

### Session protection

Every protected route checks `session.get("user_id")` at the top:

```python
@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    ...
```

### Logout (`GET /logout`)

```python
session.clear()
return redirect(url_for("landing"))
```

### Password storage

Werkzeug uses **PBKDF2-HMAC-SHA256** with a random salt by default. Plaintext passwords are never stored or logged.

---

## 🔒 Security Practices

| Practice | Implementation |
|---|---|
| **Password hashing** | Werkzeug `generate_password_hash` / `check_password_hash` — PBKDF2-SHA256 |
| **Parameterised SQL** | All queries use `?` placeholders — zero string formatting in SQL |
| **CSRF protection** | `secrets.token_hex(32)` stored in session, validated on every POST |
| **SQL injection prevention** | `sqlite3` parameterised queries throughout `database/db.py` and `queries.py` |
| **Foreign key enforcement** | `PRAGMA foreign_keys = ON` set on every connection in `get_db()` |
| **Auth guards** | Every protected route redirects unauthenticated users to `/login` |
| **Ownership checks** | Expense queries always filter by both `id` AND `user_id` — users cannot access other users' data |
| **Cache-Control** | Dashboard response sets `Cache-Control: no-store` to prevent browser caching of sensitive data |
| **No debug in prod** | `debug` flag reads from `FLASK_DEBUG` env variable, defaults to `false` |

---

## 🔀 Git Workflow

This project follows a **feature-branch workflow**:

```
main
 └── feature/database-setup       ← spec 01
 └── feature/registration         ← spec 02
 └── feature/login-logout         ← spec 03
 └── feature/profile-page         ← spec 04 / 05 / 06
 └── feature/add-expense          ← spec 07
 └── feature/edit-expense         ← spec 08
 └── feature/delete-expense       ← spec 09
```

Each feature branch corresponds to one spec file in `.claude/specs/`. The branch is merged into `main` via a pull request once the feature is implemented, tested, and code-reviewed.

---

## 🤖 Claude AI Workflow

Spendly was built using **Claude Code** as the primary development assistant, following a spec-driven, agentic workflow.

### How it worked

```
1. /create-spec  →  Claude writes a detailed markdown spec in .claude/specs/
2. Claude implements the feature from the spec (routes, DB helpers, templates)
3. /test-feature →  spendly-test-writer agent generates pytest tests
                    spendly-test-runner agent executes and analyses results
4. /code-review-feature → spendly-quality-reviewer + spendly-security-reviewer
                           run in parallel and report findings
5. Merge to main
```

### Custom slash commands

| Command | Purpose |
|---|---|
| `/create-spec` | Scaffold a new markdown feature spec |
| `/test-feature <step>` | Write and run tests for a given spec |
| `/code-review-feature <step>` | Parallel quality + security review of changed code |
| `/seed-user` | Insert a dummy user into the database |
| `/seed-expense` | Seed realistic dummy expenses for a user |

### Specialised agents

| Agent | Role |
|---|---|
| `spendly-test-writer` | Generates pytest tests from spec requirements |
| `spendly-test-runner` | Executes tests and analyses failures |
| `spendly-quality-reviewer` | Reviews code quality, clean-code patterns |
| `spendly-security-reviewer` | Reviews for OWASP-style security issues |

All agent definitions live in `.claude/agents/`.

---

## 🚀 Deployment Guide

### Render / Railway (recommended for beginners)

1. Push your repository to GitHub.
2. Create a new **Web Service** on [Render](https://render.com) or [Railway](https://railway.app).
3. Set the **Start Command** to:
   ```
   gunicorn app:app
   ```
4. Set environment variables in the dashboard:
   ```
   SECRET_KEY=<random-64-char-string>
   FLASK_DEBUG=false
   ```
5. Deploy. The database file (`spendly.db`) will be created on first boot.

> **Important:** SQLite is a file-based database. On platforms with ephemeral filesystems (Render free tier, Heroku), the database resets on each deploy. For persistent production data, migrate to PostgreSQL (see Future Improvements).

### Gunicorn basics

```bash
# Run with 2 worker processes
gunicorn -w 2 app:app

# Run on a specific port
gunicorn -w 2 -b 0.0.0.0:8000 app:app
```

### Environment variables checklist

- [ ] `SECRET_KEY` — long, random, never committed to git
- [ ] `FLASK_DEBUG=false` — always false in production

---

## 🧪 Running Tests

```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/test_add_expense.py

# Run with verbose output
pytest -v
```

Tests use `pytest-flask` for route testing and a dedicated in-memory test client. Playwright is available for end-to-end browser tests.

---

## 🔮 Future Improvements

| Area | Improvement |
|---|---|
| **Database** | Migrate from SQLite to PostgreSQL for production-grade persistence and concurrency |
| **API** | Expose a REST API (JSON responses) so the frontend can be decoupled |
| **Auth** | Add OAuth (Google / GitHub sign-in) via Flask-OAuthlib |
| **Containers** | Add `Dockerfile` and `docker-compose.yml` for consistent local and cloud environments |
| **Cloud** | Full deployment guide for AWS / GCP / Azure with persistent volume for SQLite or managed Postgres |
| **Analytics** | Monthly trend charts using Chart.js or D3.js |
| **Budget limits** | Per-category monthly budget caps with visual warnings when approaching limits |
| **Export** | Export expenses to CSV / PDF via `reportlab` (already installed) |
| **Recurring expenses** | Support for marking expenses as recurring (subscriptions, rent) |
| **Multi-currency** | Support for currencies beyond INR |
| **Dark mode** | CSS variable-based theme toggle |
| **2FA** | TOTP-based two-factor authentication |

---

## 📚 Learning Outcomes

Building Spendly from scratch provided hands-on experience with:

- **Flask fundamentals** — routing, templates, sessions, flash messages, request handling
- **Database design** — relational schema design, foreign keys, parameterised queries, SQLite pragmas
- **Authentication security** — password hashing, session management, CSRF protection, ownership-based access control
- **Jinja2 templating** — template inheritance, conditional rendering, filters, context variables
- **Spec-driven development** — writing and implementing from detailed markdown specifications
- **Agentic AI workflows** — using Claude Code with specialised sub-agents for testing, code review, and seeding
- **Feature-branch Git workflow** — one branch per feature, PR-based merges, clean commit history
- **Production readiness** — Gunicorn WSGI, environment variable management, deployment configuration
- **Frontend without a framework** — CSS custom properties, responsive layout, vanilla JS DOM interaction

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome.

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Commit your changes: `git commit -m "add: brief description"`
4. Push to your branch: `git push origin feature/your-feature-name`
5. Open a Pull Request against `main`

Please ensure:
- All new routes have authentication guards where applicable
- All SQL queries use parameterised placeholders (no string formatting)
- New features include corresponding tests in `tests/`
- Code follows the existing style (no ORMs, no external auth libraries)

---

## 📄 License

This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2026 Mahi Gupta

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 👤 Author

**Mahi Gupta**

- GitHub: [@Mahi11353](https://github.com/Mahi11353)
- Email: gupta.mahi1409@gmail.com

---

<div align="center">
  <strong>◈ Spendly</strong> — Built with Flask, SQLite, and Claude Code
  <br>
  <em>Track every rupee. Own your finances.</em>
</div>
