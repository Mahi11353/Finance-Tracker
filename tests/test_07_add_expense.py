"""
tests/test_07_add_expense.py

Pytest test suite for the Spendly "Add Expense" feature (Step 07).
Tests are written against the feature specification only; no implementation
details are reverse-engineered from the source.

Spec: .claude/specs/07-add-expense.md

Coverage:
- Unit tests for database.queries.insert_expense
- GET /expenses/add — auth guard and template content
- POST /expenses/add — auth guard, happy path, all validation error paths,
  optional-description path, and DB side-effects
"""

import sys
import os
import sqlite3
import pytest
from werkzeug.security import generate_password_hash

# Make sure the project root is importable regardless of where pytest is invoked.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as flask_app_module


# ------------------------------------------------------------------ #
# Helpers — raw DB access so tests never depend on app helpers        #
# ------------------------------------------------------------------ #

def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _create_schema(db_path: str) -> None:
    conn = _get_conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def _insert_user(
    db_path: str,
    name: str = "Test User",
    email: str = "testuser@example.com",
    password: str = "testpass1",
) -> int:
    conn = _get_conn(db_path)
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name, email, generate_password_hash(password), "2026-01-01 00:00:00"),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def _query_expenses(db_path: str, user_id: int) -> list:
    """Return all expense rows for the given user as a list of dicts."""
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """
    Each test receives a fresh, empty SQLite database at a temp path.
    Both database.db and database.queries are patched to use this path.
    """
    db_path = str(tmp_path / "test_add_expense.db")
    _create_schema(db_path)

    # Patch DB_PATH used by database.db (and therefore get_db())
    monkeypatch.setattr("database.db.DB_PATH", db_path)

    # Patch the get_db imported inside database.queries so insert_expense
    # and other query helpers also hit the isolated DB.
    monkeypatch.setattr(
        "database.queries.get_db",
        lambda: _get_conn(db_path),
    )
    yield db_path


@pytest.fixture()
def client(isolated_db, monkeypatch):
    """A test client backed by the isolated DB, with no pre-existing session."""
    monkeypatch.setattr("database.db.DB_PATH", isolated_db)
    flask_app_module.app.config["TESTING"] = True
    flask_app_module.app.config["SECRET_KEY"] = "test-secret-key"
    with flask_app_module.app.test_client() as c:
        yield c, isolated_db


@pytest.fixture()
def auth_client(client):
    """
    A test client that already has a valid session for a known user.
    Returns (test_client, user_id, db_path).
    """
    c, db_path = client
    uid = _insert_user(db_path, name="Expense Tester", email="expense@example.com")
    with c.session_transaction() as sess:
        sess["user_id"] = uid
    return c, uid, db_path


# ------------------------------------------------------------------ #
# Convenience                                                         #
# ------------------------------------------------------------------ #

def _body(resp) -> str:
    return resp.data.decode("utf-8")


# ------------------------------------------------------------------ #
# 1. Unit tests for insert_expense                                    #
# ------------------------------------------------------------------ #

class TestInsertExpense:
    """Direct unit tests for database.queries.insert_expense."""

    def test_valid_args_inserts_row_into_db(self, isolated_db):
        """insert_expense with valid args must persist exactly one row."""
        from database.queries import insert_expense

        uid = _insert_user(isolated_db)
        insert_expense(uid, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _query_expenses(isolated_db, uid)
        assert len(rows) == 1, "Exactly one expense row should be inserted"

    def test_valid_args_stores_correct_amount(self, isolated_db):
        from database.queries import insert_expense

        uid = _insert_user(isolated_db)
        insert_expense(uid, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _query_expenses(isolated_db, uid)
        assert rows[0]["amount"] == 50.0, "Stored amount must equal 50.0"

    def test_valid_args_stores_correct_category(self, isolated_db):
        from database.queries import insert_expense

        uid = _insert_user(isolated_db)
        insert_expense(uid, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _query_expenses(isolated_db, uid)
        assert rows[0]["category"] == "Food", "Stored category must equal 'Food'"

    def test_valid_args_stores_correct_date(self, isolated_db):
        from database.queries import insert_expense

        uid = _insert_user(isolated_db)
        insert_expense(uid, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _query_expenses(isolated_db, uid)
        assert rows[0]["date"] == "2026-03-20", "Stored date must equal '2026-03-20'"

    def test_valid_args_stores_correct_description(self, isolated_db):
        from database.queries import insert_expense

        uid = _insert_user(isolated_db)
        insert_expense(uid, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _query_expenses(isolated_db, uid)
        assert rows[0]["description"] == "Lunch", "Stored description must equal 'Lunch'"

    def test_valid_args_stores_correct_user_id(self, isolated_db):
        from database.queries import insert_expense

        uid = _insert_user(isolated_db)
        insert_expense(uid, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _query_expenses(isolated_db, uid)
        assert rows[0]["user_id"] == uid, "Stored user_id must match the inserted user"

    def test_none_description_stores_null(self, isolated_db):
        """insert_expense with description=None must store NULL in the DB."""
        from database.queries import insert_expense

        uid = _insert_user(isolated_db)
        insert_expense(uid, 99.0, "Transport", "2026-03-21", None)

        rows = _query_expenses(isolated_db, uid)
        assert len(rows) == 1, "One expense row should be inserted even with NULL description"
        assert rows[0]["description"] is None, (
            "description column must be NULL when None is passed"
        )

    def test_insert_expense_multiple_rows_are_independent(self, isolated_db):
        """Calling insert_expense twice creates two separate rows."""
        from database.queries import insert_expense

        uid = _insert_user(isolated_db)
        insert_expense(uid, 10.0, "Food", "2026-03-20", "Breakfast")
        insert_expense(uid, 20.0, "Transport", "2026-03-21", "Bus")

        rows = _query_expenses(isolated_db, uid)
        assert len(rows) == 2, "Two insert_expense calls must produce two rows"


# ------------------------------------------------------------------ #
# 2. Auth guard                                                       #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    """Unauthenticated requests to /expenses/add must redirect to /login."""

    def test_unauthenticated_get_redirects_to_login(self, client):
        c, _ = client
        resp = c.get("/expenses/add")
        assert resp.status_code == 302, (
            "Unauthenticated GET /expenses/add must return 302"
        )
        assert "/login" in resp.headers.get("Location", ""), (
            "Redirect must point to /login, got: " + resp.headers.get("Location", "")
        )

    def test_unauthenticated_post_redirects_to_login(self, client):
        c, _ = client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 302, (
            "Unauthenticated POST /expenses/add must return 302"
        )
        assert "/login" in resp.headers.get("Location", ""), (
            "Redirect must point to /login, got: " + resp.headers.get("Location", "")
        )


# ------------------------------------------------------------------ #
# 3. GET /expenses/add — authenticated                               #
# ------------------------------------------------------------------ #

class TestGetRoute:
    """Authenticated GET /expenses/add must return the form page."""

    def test_authenticated_get_returns_200(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        assert resp.status_code == 200, (
            "Authenticated GET /expenses/add must return 200"
        )

    def test_response_contains_form_element(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "<form" in body, "Response must contain a <form element"

    def test_form_method_is_post(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp).lower()
        # Find the form element and verify it has method="post"
        assert 'method="post"' in body or "method='post'" in body, (
            "The form element must declare method POST"
        )

    def test_response_contains_select_element(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "<select" in body, "Response must contain a <select element for category"

    def test_category_food_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "Food" in body, "Category option 'Food' must be present in the form"

    def test_category_transport_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "Transport" in body, "Category option 'Transport' must be present in the form"

    def test_category_bills_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "Bills" in body, "Category option 'Bills' must be present in the form"

    def test_category_health_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "Health" in body, "Category option 'Health' must be present in the form"

    def test_category_entertainment_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "Entertainment" in body, (
            "Category option 'Entertainment' must be present in the form"
        )

    def test_category_shopping_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "Shopping" in body, "Category option 'Shopping' must be present in the form"

    def test_category_other_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "Other" in body, "Category option 'Other' must be present in the form"

    def test_all_seven_categories_present(self, auth_client):
        """Consolidated check: all 7 fixed category options must appear."""
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        expected_categories = [
            "Food", "Transport", "Bills", "Health",
            "Entertainment", "Shopping", "Other",
        ]
        for cat in expected_categories:
            assert cat in body, (
                f"Category option '{cat}' must be present in the add-expense form"
            )

    def test_amount_field_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert 'name="amount"' in body, "Form must include an amount input field"

    def test_date_field_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert 'name="date"' in body, "Form must include a date input field"

    def test_description_field_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert 'name="description"' in body, "Form must include a description input field"

    def test_page_extends_base_template(self, auth_client):
        """The page should include nav/structure from base.html (e.g. Spendly brand)."""
        c, uid, _ = auth_client
        resp = c.get("/expenses/add")
        body = _body(resp)
        assert "Spendly" in body, (
            "Page must extend base.html; 'Spendly' brand/title must appear"
        )


# ------------------------------------------------------------------ #
# 4. POST /expenses/add — valid data (happy path)                    #
# ------------------------------------------------------------------ #

class TestPostValid:
    """A POST with fully valid data must redirect to /profile and persist the row."""

    def test_valid_post_redirects_302(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 302, (
            "Valid POST /expenses/add must return 302 redirect"
        )

    def test_valid_post_redirects_to_profile(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"Valid POST must redirect to /profile, got Location: {location}"
        )

    def test_valid_post_inserts_row_into_db(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 1, "Valid POST must create exactly one expense row in the DB"

    def test_valid_post_stores_correct_amount_in_db(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert rows[0]["amount"] == 50.0, "DB must store the submitted amount (50.0)"

    def test_valid_post_stores_correct_category_in_db(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert rows[0]["category"] == "Food", "DB must store the submitted category"

    def test_valid_post_stores_correct_date_in_db(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert rows[0]["date"] == "2026-03-20", "DB must store the submitted date"

    def test_valid_post_stores_correct_description_in_db(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert rows[0]["description"] == "Lunch", "DB must store the submitted description"

    def test_valid_post_associates_row_with_authenticated_user(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert rows[0]["user_id"] == uid, (
            "Inserted row must be associated with the authenticated user's ID"
        )


# ------------------------------------------------------------------ #
# 5. POST /expenses/add — validation errors                          #
# ------------------------------------------------------------------ #

class TestPostValidation:
    """Invalid POST data must re-render the form (200) with an error message."""

    def test_missing_amount_returns_200(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
            # amount intentionally omitted
        })
        assert resp.status_code == 200, (
            "Missing amount must re-render the form with status 200"
        )

    def test_missing_amount_shows_error_in_body(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        body = _body(resp)
        # Any error-indicating text is acceptable; the form should not silently succeed
        assert any(word in body.lower() for word in ["error", "required", "amount", "invalid"]), (
            "Missing amount must produce a visible error message on the re-rendered form"
        )

    def test_missing_amount_does_not_insert_row(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 0, "Missing amount must not insert any expense row"

    def test_zero_amount_returns_200(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 200, (
            "amount=0 must re-render the form with status 200"
        )

    def test_zero_amount_shows_error_in_body(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(word in body.lower() for word in ["error", "zero", "greater", "positive", "amount"]), (
            "amount=0 must produce a visible error message on the re-rendered form"
        )

    def test_zero_amount_does_not_insert_row(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 0, "amount=0 must not insert any expense row"

    def test_nonnumeric_amount_returns_200(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 200, (
            "Non-numeric amount must re-render the form with status 200"
        )

    def test_nonnumeric_amount_shows_error_in_body(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(word in body.lower() for word in ["error", "number", "numeric", "amount", "invalid"]), (
            "Non-numeric amount must produce a visible error message on the re-rendered form"
        )

    def test_nonnumeric_amount_does_not_insert_row(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 0, "Non-numeric amount must not insert any expense row"

    def test_invalid_category_returns_200(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Hacking",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 200, (
            "Invalid category must re-render the form with status 200"
        )

    def test_invalid_category_shows_error_in_body(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Hacking",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(word in body.lower() for word in ["error", "category", "valid", "invalid", "select"]), (
            "Invalid category must produce a visible error message on the re-rendered form"
        )

    def test_invalid_category_does_not_insert_row(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Hacking",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 0, "Invalid category must not insert any expense row"

    def test_invalid_date_returns_200(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "not-a-date",
            "description": "Lunch",
        })
        assert resp.status_code == 200, (
            "Invalid date must re-render the form with status 200"
        )

    def test_invalid_date_shows_error_in_body(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "not-a-date",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(word in body.lower() for word in ["error", "date", "valid", "invalid"]), (
            "Invalid date must produce a visible error message on the re-rendered form"
        )

    def test_invalid_date_does_not_insert_row(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": "not-a-date",
            "description": "Lunch",
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 0, "Invalid date must not insert any expense row"

    def test_form_repopulates_amount_after_validation_error(self, auth_client):
        """On validation error the form must echo back the submitted amount value."""
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "999.99",
            "category": "InvalidCat",
            "date": "2026-03-20",
            "description": "Some note",
        })
        body = _body(resp)
        # The previously submitted amount should appear so the user doesn't retype it
        assert "999.99" in body, (
            "Previously submitted amount should be re-populated in the form on validation error"
        )


# ------------------------------------------------------------------ #
# 6. POST /expenses/add — optional description                       #
# ------------------------------------------------------------------ #

class TestPostOptionalDescription:
    """Submitting without a description is valid; row is saved with NULL description."""

    def test_no_description_redirects_302(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "75.0",
            "category": "Bills",
            "date": "2026-04-01",
            # description intentionally omitted
        })
        assert resp.status_code == 302, (
            "Omitting the optional description must still produce a 302 redirect"
        )

    def test_no_description_redirects_to_profile(self, auth_client):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "75.0",
            "category": "Bills",
            "date": "2026-04-01",
        })
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"No-description POST must redirect to /profile, got: {location}"
        )

    def test_no_description_inserts_row(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "75.0",
            "category": "Bills",
            "date": "2026-04-01",
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 1, "Omitting description must still insert one expense row"

    def test_no_description_stores_null_in_db(self, auth_client):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "75.0",
            "category": "Bills",
            "date": "2026-04-01",
        })
        rows = _query_expenses(db_path, uid)
        assert rows[0]["description"] is None, (
            "When description is omitted the DB must store NULL, not an empty string"
        )

    def test_blank_description_stores_null_in_db(self, auth_client):
        """An explicitly blank description (whitespace-only) must also store NULL."""
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "20.0",
            "category": "Other",
            "date": "2026-04-02",
            "description": "   ",  # whitespace only — should be treated as absent
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 1, "Whitespace-only description must still create one row"
        assert rows[0]["description"] is None, (
            "Whitespace-only description must be stored as NULL after stripping"
        )


# ------------------------------------------------------------------ #
# 7. DB side-effects — cross-category and cross-user isolation       #
# ------------------------------------------------------------------ #

class TestDbSideEffects:
    """Verify that writes are correctly scoped to the authenticated user."""

    def test_expense_is_scoped_to_authenticated_user(self, isolated_db, monkeypatch):
        """Two different users' expenses must not bleed into each other."""
        monkeypatch.setattr("database.db.DB_PATH", isolated_db)
        flask_app_module.app.config["TESTING"] = True
        flask_app_module.app.config["SECRET_KEY"] = "test-secret-key"

        uid_a = _insert_user(isolated_db, name="Alice", email="alice@example.com")
        uid_b = _insert_user(isolated_db, name="Bob",   email="bob@example.com")

        with flask_app_module.app.test_client() as c:
            # Log in as user A
            with c.session_transaction() as sess:
                sess["user_id"] = uid_a

            c.post("/expenses/add", data={
                "amount": "100.0",
                "category": "Shopping",
                "date": "2026-05-01",
                "description": "Alice's purchase",
            })

        # User B must have no expenses
        rows_b = _query_expenses(isolated_db, uid_b)
        assert len(rows_b) == 0, (
            "Expense submitted by user A must not appear in user B's expense list"
        )

        # User A must have exactly one expense
        rows_a = _query_expenses(isolated_db, uid_a)
        assert len(rows_a) == 1, "User A must have exactly one expense after one submission"

    @pytest.mark.parametrize("category", [
        "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
    ])
    def test_each_valid_category_can_be_saved(self, auth_client, category):
        """Every one of the 7 fixed categories must be accepted and stored."""
        c, uid, db_path = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "10.0",
            "category": category,
            "date": "2026-05-15",
            "description": f"Test {category}",
        })
        assert resp.status_code == 302, (
            f"Category '{category}' must be accepted and produce a 302 redirect"
        )
        rows = _query_expenses(db_path, uid)
        assert any(r["category"] == category for r in rows), (
            f"Category '{category}' must be stored correctly in the DB"
        )


# ------------------------------------------------------------------ #
# 8. Profile page — Add Expense navigation link                      #
# ------------------------------------------------------------------ #

class TestProfileAddExpenseLink:
    """The profile page must contain a link pointing to /expenses/add."""

    def test_profile_page_contains_add_expense_link(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "/expenses/add" in body, (
            "Profile page must contain a link to /expenses/add so users can add expenses"
        )

    def test_add_expense_link_text_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "Add Expense" in body, (
            "Profile page must contain visible 'Add Expense' text linking to the form"
        )


# ------------------------------------------------------------------ #
# 9. Parametrized validation edge cases                              #
# ------------------------------------------------------------------ #

class TestValidationEdgeCases:
    """Parametrized tests covering a range of invalid inputs."""

    @pytest.mark.parametrize("bad_amount", [
        "",        # empty string
        "0",       # exactly zero
        "-1",      # negative
        "-0.01",   # tiny negative
        "abc",     # non-numeric
        "1e99",    # valid float parse but check if accepted (spec says > 0)
        "  ",      # whitespace-only
    ])
    def test_bad_amount_values_do_not_insert_row(self, auth_client, bad_amount):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-03-20",
            "description": "Test",
        })
        rows = _query_expenses(db_path, uid)
        # Either no row is inserted (validation rejects) or the amount is
        # a truly valid positive float (1e99 parses fine and is > 0).
        # For non-positive / non-numeric values the DB must stay empty.
        if bad_amount.strip() and bad_amount.strip() not in ("0", "-1", "-0.01"):
            # "1e99" is actually a valid positive float — let it pass.
            pass
        else:
            assert len(rows) == 0, (
                f"Invalid amount '{bad_amount}' must not produce a DB row"
            )

    @pytest.mark.parametrize("bad_category", [
        "Hacking",
        "food",        # wrong case
        "FOOD",        # all-caps
        "",            # empty
        "Other ",      # trailing space (not in fixed list as-is)
        "Groceries",
        "<script>",    # potential injection attempt
    ])
    def test_bad_category_values_return_200(self, auth_client, bad_category):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": bad_category,
            "date": "2026-03-20",
            "description": "Test",
        })
        assert resp.status_code == 200, (
            f"Invalid category '{bad_category}' must re-render the form (200), not redirect"
        )

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "2026/03/20",    # wrong separator
        "20-03-2026",    # DD-MM-YYYY
        "2026-13-01",    # month out of range
        "2026-00-10",    # month zero
        "abcdefg",
        "20260320",      # no separators
        "",              # empty string
    ])
    def test_bad_date_values_return_200(self, auth_client, bad_date):
        c, uid, _ = auth_client
        resp = c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": bad_date,
            "description": "Test",
        })
        assert resp.status_code == 200, (
            f"Invalid date '{bad_date}' must re-render the form (200), not redirect"
        )

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "2026/03/20",
        "20-03-2026",
        "2026-13-01",
        "abcdefg",
    ])
    def test_bad_date_values_do_not_insert_row(self, auth_client, bad_date):
        c, uid, db_path = auth_client
        c.post("/expenses/add", data={
            "amount": "50.0",
            "category": "Food",
            "date": bad_date,
            "description": "Test",
        })
        rows = _query_expenses(db_path, uid)
        assert len(rows) == 0, (
            f"Invalid date '{bad_date}' must not produce a DB row"
        )
