"""
tests/test_08_edit_expense.py

Pytest test suite for the Spendora "Edit Expense" feature (Step 08).
Tests are written against the feature specification only; no implementation
details are reverse-engineered from the source.

Spec: .claude/specs/08-edit-expense.md

Coverage:
- Unit tests for database.queries.get_expense_by_id
- Unit tests for database.queries.update_expense
- GET /expenses/<id>/edit — auth guard, 200 happy path, pre-population, 404 paths
- POST /expenses/<id>/edit — auth guard, happy path, ownership 404, all
  validation error paths, optional-description path, DB side-effects,
  form re-population after errors
- Profile page edit links
"""

import sys
import os
import sqlite3
import pytest
from werkzeug.security import generate_password_hash

# Ensure project root is importable regardless of pytest invocation directory.
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


def _insert_expense(
    db_path: str,
    user_id: int,
    amount: float = 50.0,
    category: str = "Food",
    date: str = "2026-03-20",
    description: str = "Lunch",
) -> int:
    """Insert a single expense and return its id."""
    conn = _get_conn(db_path)
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return eid


def _query_expense(db_path: str, expense_id: int) -> dict | None:
    """Return a single expense row as a dict, or None if not found."""
    conn = _get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """
    Each test gets a fresh, empty SQLite database.
    Both database.db and database.queries are patched to use this path.
    """
    db_path = str(tmp_path / "test_edit_expense.db")
    _create_schema(db_path)

    monkeypatch.setattr("database.db.DB_PATH", db_path)
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
    A test client that already has a valid session for a known user who
    owns one pre-seeded expense.
    Returns (test_client, user_id, expense_id, db_path).
    """
    c, db_path = client
    uid = _insert_user(db_path, name="Edit Tester", email="edit@example.com")
    eid = _insert_expense(
        db_path, uid,
        amount=75.50,
        category="Transport",
        date="2026-04-15",
        description="Train ticket",
    )
    with c.session_transaction() as sess:
        sess["user_id"] = uid
    return c, uid, eid, db_path


# ------------------------------------------------------------------ #
# Convenience                                                         #
# ------------------------------------------------------------------ #

def _body(resp) -> str:
    return resp.data.decode("utf-8")


# ------------------------------------------------------------------ #
# 1. Unit tests — get_expense_by_id                                   #
# ------------------------------------------------------------------ #

class TestGetExpenseById:
    """Direct unit tests for database.queries.get_expense_by_id."""

    def test_correct_user_id_returns_row(self, isolated_db):
        """get_expense_by_id with matching user_id must return a non-None row."""
        from database.queries import get_expense_by_id

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=42.0, category="Food",
                              date="2026-05-01", description="Groceries")

        result = get_expense_by_id(eid, uid)
        assert result is not None, (
            "get_expense_by_id must return a row when expense_id and user_id match"
        )

    def test_correct_user_id_returns_correct_amount(self, isolated_db):
        from database.queries import get_expense_by_id

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=42.0, category="Food",
                              date="2026-05-01", description="Groceries")

        result = get_expense_by_id(eid, uid)
        assert result["amount"] == 42.0, "Returned row must have the correct amount"

    def test_correct_user_id_returns_correct_category(self, isolated_db):
        from database.queries import get_expense_by_id

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=42.0, category="Food",
                              date="2026-05-01", description="Groceries")

        result = get_expense_by_id(eid, uid)
        assert result["category"] == "Food", "Returned row must have the correct category"

    def test_correct_user_id_returns_correct_date(self, isolated_db):
        from database.queries import get_expense_by_id

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=42.0, category="Food",
                              date="2026-05-01", description="Groceries")

        result = get_expense_by_id(eid, uid)
        assert result["date"] == "2026-05-01", "Returned row must have the correct date"

    def test_correct_user_id_returns_correct_description(self, isolated_db):
        from database.queries import get_expense_by_id

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=42.0, category="Food",
                              date="2026-05-01", description="Groceries")

        result = get_expense_by_id(eid, uid)
        assert result["description"] == "Groceries", (
            "Returned row must have the correct description"
        )

    def test_correct_user_id_returns_correct_id(self, isolated_db):
        from database.queries import get_expense_by_id

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=42.0, category="Food",
                              date="2026-05-01", description="Groceries")

        result = get_expense_by_id(eid, uid)
        assert result["id"] == eid, "Returned row must carry the correct expense id"

    def test_wrong_user_id_returns_none(self, isolated_db):
        """get_expense_by_id must return None when user_id does not own the expense."""
        from database.queries import get_expense_by_id

        uid_owner = _insert_user(isolated_db, name="Owner", email="owner@example.com")
        uid_other = _insert_user(isolated_db, name="Other", email="other@example.com")
        eid = _insert_expense(isolated_db, uid_owner, amount=10.0, category="Bills",
                              date="2026-05-10", description="Bill")

        result = get_expense_by_id(eid, uid_other)
        assert result is None, (
            "get_expense_by_id must return None when the expense belongs to a different user"
        )

    def test_nonexistent_expense_id_returns_none(self, isolated_db):
        """get_expense_by_id must return None for an id that has no row."""
        from database.queries import get_expense_by_id

        uid = _insert_user(isolated_db)
        result = get_expense_by_id(99999, uid)
        assert result is None, (
            "get_expense_by_id must return None when no expense with that id exists"
        )

    def test_returns_none_after_only_other_users_expenses_exist(self, isolated_db):
        """When another user owns expenses, querying with wrong user must still return None."""
        from database.queries import get_expense_by_id

        uid_a = _insert_user(isolated_db, name="A", email="a@example.com")
        uid_b = _insert_user(isolated_db, name="B", email="b@example.com")
        eid = _insert_expense(isolated_db, uid_a, amount=25.0, category="Health",
                              date="2026-05-05", description="Doctor")

        # uid_b attempts to access uid_a's expense
        assert get_expense_by_id(eid, uid_b) is None, (
            "Ownership scoping must prevent user B from seeing user A's expense"
        )


# ------------------------------------------------------------------ #
# 2. Unit tests — update_expense                                      #
# ------------------------------------------------------------------ #

class TestUpdateExpense:
    """Direct unit tests for database.queries.update_expense."""

    def test_correct_user_id_updates_amount(self, isolated_db):
        """update_expense with the correct user_id must persist the new amount."""
        from database.queries import update_expense

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=50.0, category="Food",
                              date="2026-04-01", description="Dinner")

        update_expense(eid, uid, 99.0, "Food", "2026-04-01", "Dinner")

        row = _query_expense(isolated_db, eid)
        assert row["amount"] == 99.0, (
            "update_expense must write the new amount to the DB when user_id matches"
        )

    def test_correct_user_id_updates_category(self, isolated_db):
        from database.queries import update_expense

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=50.0, category="Food",
                              date="2026-04-01", description="Dinner")

        update_expense(eid, uid, 50.0, "Health", "2026-04-01", "Dinner")

        row = _query_expense(isolated_db, eid)
        assert row["category"] == "Health", "update_expense must write the new category"

    def test_correct_user_id_updates_date(self, isolated_db):
        from database.queries import update_expense

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=50.0, category="Food",
                              date="2026-04-01", description="Dinner")

        update_expense(eid, uid, 50.0, "Food", "2026-06-15", "Dinner")

        row = _query_expense(isolated_db, eid)
        assert row["date"] == "2026-06-15", "update_expense must write the new date"

    def test_correct_user_id_updates_description(self, isolated_db):
        from database.queries import update_expense

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=50.0, category="Food",
                              date="2026-04-01", description="Dinner")

        update_expense(eid, uid, 50.0, "Food", "2026-04-01", "Updated note")

        row = _query_expense(isolated_db, eid)
        assert row["description"] == "Updated note", (
            "update_expense must write the new description"
        )

    def test_correct_user_id_sets_description_null(self, isolated_db):
        """update_expense with description=None must store NULL in the DB."""
        from database.queries import update_expense

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=50.0, category="Food",
                              date="2026-04-01", description="Dinner")

        update_expense(eid, uid, 50.0, "Food", "2026-04-01", None)

        row = _query_expense(isolated_db, eid)
        assert row["description"] is None, (
            "update_expense with description=None must store NULL in the DB"
        )

    def test_wrong_user_id_leaves_row_unchanged(self, isolated_db):
        """update_expense with the wrong user_id must not modify any row."""
        from database.queries import update_expense

        uid_owner = _insert_user(isolated_db, name="Owner", email="owner@example.com")
        uid_other = _insert_user(isolated_db, name="Other", email="other@example.com")
        eid = _insert_expense(isolated_db, uid_owner, amount=50.0, category="Food",
                              date="2026-04-01", description="Original")

        # Attempt to update with wrong user — must be a no-op, not raise
        update_expense(eid, uid_other, 999.0, "Shopping", "2026-12-31", "Hacked")

        row = _query_expense(isolated_db, eid)
        assert row["amount"] == 50.0, (
            "Amount must be unchanged when update_expense is called with the wrong user_id"
        )
        assert row["category"] == "Food", (
            "Category must be unchanged when update_expense is called with the wrong user_id"
        )
        assert row["description"] == "Original", (
            "Description must be unchanged when update_expense is called with the wrong user_id"
        )

    def test_wrong_user_id_does_not_raise(self, isolated_db):
        """update_expense with the wrong user_id must not raise any exception."""
        from database.queries import update_expense

        uid_owner = _insert_user(isolated_db, name="Owner2", email="owner2@example.com")
        uid_other = _insert_user(isolated_db, name="Other2", email="other2@example.com")
        eid = _insert_expense(isolated_db, uid_owner, amount=10.0, category="Other",
                              date="2026-01-01", description="Test")

        # Should not raise
        try:
            update_expense(eid, uid_other, 500.0, "Shopping", "2026-06-01", "Attack")
        except Exception as exc:
            pytest.fail(
                f"update_expense raised an exception with a wrong user_id: {exc}"
            )

    def test_update_does_not_affect_other_expenses(self, isolated_db):
        """Updating one expense must not change any other expense row."""
        from database.queries import update_expense

        uid = _insert_user(isolated_db)
        eid1 = _insert_expense(isolated_db, uid, amount=10.0, category="Food",
                               date="2026-01-01", description="Breakfast")
        eid2 = _insert_expense(isolated_db, uid, amount=20.0, category="Transport",
                               date="2026-01-02", description="Bus")

        update_expense(eid1, uid, 15.0, "Food", "2026-01-01", "Updated breakfast")

        row2 = _query_expense(isolated_db, eid2)
        assert row2["amount"] == 20.0, (
            "update_expense must not modify expenses other than the targeted one"
        )


# ------------------------------------------------------------------ #
# 3. Auth guard                                                        #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    """Unauthenticated requests to /expenses/<id>/edit must redirect to /login."""

    def test_unauthenticated_get_redirects_302(self, client):
        c, db_path = client
        # Insert a user and expense so the id actually exists.
        uid = _insert_user(db_path, name="Guard User", email="guard@example.com")
        eid = _insert_expense(db_path, uid)
        resp = c.get(f"/expenses/{eid}/edit")
        assert resp.status_code == 302, (
            "Unauthenticated GET /expenses/<id>/edit must return 302"
        )

    def test_unauthenticated_get_redirects_to_login(self, client):
        c, db_path = client
        uid = _insert_user(db_path, name="Guard User2", email="guard2@example.com")
        eid = _insert_expense(db_path, uid)
        resp = c.get(f"/expenses/{eid}/edit")
        location = resp.headers.get("Location", "")
        assert "/login" in location, (
            f"Unauthenticated GET must redirect to /login, got: {location}"
        )

    def test_unauthenticated_post_redirects_302(self, client):
        c, db_path = client
        uid = _insert_user(db_path, name="Guard User3", email="guard3@example.com")
        eid = _insert_expense(db_path, uid)
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-05-01",
            "description": "Tamper",
        })
        assert resp.status_code == 302, (
            "Unauthenticated POST /expenses/<id>/edit must return 302"
        )

    def test_unauthenticated_post_redirects_to_login(self, client):
        c, db_path = client
        uid = _insert_user(db_path, name="Guard User4", email="guard4@example.com")
        eid = _insert_expense(db_path, uid)
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Food",
            "date": "2026-05-01",
            "description": "Tamper",
        })
        location = resp.headers.get("Location", "")
        assert "/login" in location, (
            f"Unauthenticated POST must redirect to /login, got: {location}"
        )


# ------------------------------------------------------------------ #
# 4. GET /expenses/<id>/edit — authenticated, own expense            #
# ------------------------------------------------------------------ #

class TestGetRouteOwnExpense:
    """Authenticated GET on an owned expense must return 200 with pre-filled form."""

    def test_returns_200(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.get(f"/expenses/{eid}/edit")
        assert resp.status_code == 200, (
            "Authenticated GET /expenses/<id>/edit (own expense) must return 200"
        )

    def test_response_contains_form_element(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.get(f"/expenses/{eid}/edit")
        assert "<form" in _body(resp), "Response must contain a <form element"

    def test_form_method_is_post(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit")).lower()
        assert 'method="post"' in body or "method='post'" in body, (
            "The edit form must declare method POST"
        )

    def test_form_action_contains_expense_id(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert f"/expenses/{eid}/edit" in body, (
            f"Form action must reference /expenses/{eid}/edit"
        )

    def test_prefills_amount(self, auth_client):
        c, uid, eid, db_path = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        # The seeded expense has amount 75.5; the form value may render as 75.5 or 75.50
        assert "75.5" in body, (
            "Edit form must pre-fill the current amount value (75.5)"
        )

    def test_prefills_date(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert "2026-04-15" in body, (
            "Edit form must pre-fill the current date value (2026-04-15)"
        )

    def test_prefills_description(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert "Train ticket" in body, (
            "Edit form must pre-fill the current description value"
        )

    def test_category_select_present(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert "<select" in body, "Response must contain a <select for category"

    def test_all_seven_categories_present(self, auth_client):
        """All 7 fixed category options must appear in the select."""
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        for cat in ["Food", "Transport", "Bills", "Health",
                    "Entertainment", "Shopping", "Other"]:
            assert cat in body, (
                f"Category option '{cat}' must be present in the edit form"
            )

    def test_current_category_is_preselected(self, auth_client):
        """The seeded expense has category 'Transport'; that option must be selected."""
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        # The HTML must mark Transport as selected — look for selected near Transport
        # Acceptable patterns: 'selected' appears on the same <option> line as Transport
        assert "selected" in body, "A category option must be marked as selected"
        # Find the region around 'Transport' and confirm 'selected' appears nearby
        idx = body.find("Transport")
        assert idx != -1, "Transport category must appear in the page"
        surrounding = body[max(0, idx - 50): idx + 100]
        assert "selected" in surrounding, (
            "The current expense category 'Transport' must be marked as selected in the <select>"
        )

    def test_amount_input_present(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert 'name="amount"' in body, "Form must include an amount input"

    def test_date_input_present(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert 'name="date"' in body, "Form must include a date input"

    def test_description_input_present(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert 'name="description"' in body, "Form must include a description input"

    def test_save_changes_button_present(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert "Save Changes" in body, "Submit button must be labelled 'Save Changes'"

    def test_cancel_link_to_profile_present(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert "/profile" in body, (
            "A cancel link back to /profile must appear on the edit form page"
        )

    def test_page_extends_base_template(self, auth_client):
        c, uid, eid, _ = auth_client
        body = _body(c.get(f"/expenses/{eid}/edit"))
        assert "Spendora" in body, (
            "Page must extend base.html; 'Spendora' brand/title must appear"
        )


# ------------------------------------------------------------------ #
# 5. GET /expenses/<id>/edit — 404 paths                             #
# ------------------------------------------------------------------ #

class TestGetRoute404:
    """Requests that do not match owned expenses must return 404."""

    def test_other_users_expense_returns_404(self, client):
        c, db_path = client
        uid_owner = _insert_user(db_path, name="Owner", email="owner404@example.com")
        uid_other = _insert_user(db_path, name="Other", email="other404@example.com")
        eid = _insert_expense(db_path, uid_owner, amount=30.0, category="Bills",
                              date="2026-05-01", description="Electric")

        # Log in as uid_other
        with c.session_transaction() as sess:
            sess["user_id"] = uid_other

        resp = c.get(f"/expenses/{eid}/edit")
        assert resp.status_code == 404, (
            "GET on another user's expense must return 404"
        )

    def test_nonexistent_expense_returns_404(self, client):
        c, db_path = client
        uid = _insert_user(db_path, name="NoExp", email="noexp@example.com")

        with c.session_transaction() as sess:
            sess["user_id"] = uid

        resp = c.get("/expenses/99999/edit")
        assert resp.status_code == 404, (
            "GET on a non-existent expense id must return 404"
        )


# ------------------------------------------------------------------ #
# 6. POST /expenses/<id>/edit — valid data (happy path)              #
# ------------------------------------------------------------------ #

class TestPostValid:
    """A POST with fully valid data must redirect to /profile and update the DB."""

    def test_valid_post_returns_302(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "120.0",
            "category": "Bills",
            "date": "2026-05-10",
            "description": "Updated bill",
        })
        assert resp.status_code == 302, (
            "Valid POST /expenses/<id>/edit must return 302 redirect"
        )

    def test_valid_post_redirects_to_profile(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "120.0",
            "category": "Bills",
            "date": "2026-05-10",
            "description": "Updated bill",
        })
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"Valid POST must redirect to /profile, got Location: {location}"
        )

    def test_valid_post_updates_amount_in_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "120.0",
            "category": "Bills",
            "date": "2026-05-10",
            "description": "Updated bill",
        })
        row = _query_expense(db_path, eid)
        assert row["amount"] == 120.0, (
            "DB must reflect the new amount after a valid POST"
        )

    def test_valid_post_updates_category_in_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "120.0",
            "category": "Bills",
            "date": "2026-05-10",
            "description": "Updated bill",
        })
        row = _query_expense(db_path, eid)
        assert row["category"] == "Bills", (
            "DB must reflect the new category after a valid POST"
        )

    def test_valid_post_updates_date_in_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "120.0",
            "category": "Bills",
            "date": "2026-05-10",
            "description": "Updated bill",
        })
        row = _query_expense(db_path, eid)
        assert row["date"] == "2026-05-10", (
            "DB must reflect the new date after a valid POST"
        )

    def test_valid_post_updates_description_in_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "120.0",
            "category": "Bills",
            "date": "2026-05-10",
            "description": "Updated bill",
        })
        row = _query_expense(db_path, eid)
        assert row["description"] == "Updated bill", (
            "DB must reflect the new description after a valid POST"
        )

    def test_valid_post_does_not_change_user_id(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "120.0",
            "category": "Bills",
            "date": "2026-05-10",
            "description": "Updated bill",
        })
        row = _query_expense(db_path, eid)
        assert row["user_id"] == uid, (
            "user_id in the DB must remain unchanged after an edit"
        )


# ------------------------------------------------------------------ #
# 7. POST /expenses/<id>/edit — ownership 404                        #
# ------------------------------------------------------------------ #

class TestPostOwnership:
    """POST to another user's expense must return 404 and not modify the DB."""

    def test_other_users_expense_returns_404(self, client):
        c, db_path = client
        uid_owner = _insert_user(db_path, name="Owner", email="powner@example.com")
        uid_other = _insert_user(db_path, name="Other", email="pother@example.com")
        eid = _insert_expense(db_path, uid_owner, amount=30.0, category="Bills",
                              date="2026-05-01", description="Electric")

        with c.session_transaction() as sess:
            sess["user_id"] = uid_other

        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "999.0",
            "category": "Shopping",
            "date": "2026-12-31",
            "description": "Hacked",
        })
        assert resp.status_code == 404, (
            "POST to another user's expense must return 404"
        )

    def test_other_users_expense_post_does_not_modify_db(self, client):
        c, db_path = client
        uid_owner = _insert_user(db_path, name="Owner2", email="powner2@example.com")
        uid_other = _insert_user(db_path, name="Other2", email="pother2@example.com")
        eid = _insert_expense(db_path, uid_owner, amount=30.0, category="Bills",
                              date="2026-05-01", description="Original")

        with c.session_transaction() as sess:
            sess["user_id"] = uid_other

        c.post(f"/expenses/{eid}/edit", data={
            "amount": "999.0",
            "category": "Shopping",
            "date": "2026-12-31",
            "description": "Hacked",
        })
        row = _query_expense(db_path, eid)
        assert row["amount"] == 30.0, (
            "DB row must be unchanged after a cross-user POST attempt"
        )


# ------------------------------------------------------------------ #
# 8. POST /expenses/<id>/edit — validation errors                    #
# ------------------------------------------------------------------ #

class TestPostValidation:
    """Invalid POST data must re-render the form (200) with an error message."""

    # -- missing amount ------------------------------------------------

    def test_missing_amount_returns_200(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
            # amount omitted
        })
        assert resp.status_code == 200, (
            "Missing amount must re-render the form with status 200"
        )

    def test_missing_amount_shows_error(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(w in body.lower() for w in ["error", "required", "amount", "invalid"]), (
            "Missing amount must show an error message on the re-rendered form"
        )

    def test_missing_amount_does_not_update_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        row = _query_expense(db_path, eid)
        assert row["amount"] == 75.50, (
            "Missing amount must not update the DB row"
        )

    # -- amount = 0 ----------------------------------------------------

    def test_zero_amount_returns_200(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 200, "amount=0 must re-render the form with status 200"

    def test_zero_amount_shows_error(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(w in body.lower() for w in
                   ["error", "zero", "greater", "positive", "amount"]), (
            "amount=0 must produce an error message on the re-rendered form"
        )

    def test_zero_amount_does_not_update_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "0",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        row = _query_expense(db_path, eid)
        assert row["amount"] == 75.50, "amount=0 must not update the DB row"

    # -- non-numeric amount --------------------------------------------

    def test_nonnumeric_amount_returns_200(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 200, (
            "Non-numeric amount must re-render the form with status 200"
        )

    def test_nonnumeric_amount_shows_error(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(w in body.lower() for w in
                   ["error", "number", "numeric", "amount", "invalid"]), (
            "Non-numeric amount must produce an error message"
        )

    def test_nonnumeric_amount_does_not_update_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        row = _query_expense(db_path, eid)
        assert row["amount"] == 75.50, "Non-numeric amount must not update the DB row"

    # -- invalid category ----------------------------------------------

    def test_invalid_category_returns_200(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Hacking",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        assert resp.status_code == 200, (
            "Invalid category must re-render the form with status 200"
        )

    def test_invalid_category_shows_error(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Hacking",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(w in body.lower() for w in
                   ["error", "category", "valid", "invalid", "select"]), (
            "Invalid category must produce an error message"
        )

    def test_invalid_category_does_not_update_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Hacking",
            "date": "2026-03-20",
            "description": "Lunch",
        })
        row = _query_expense(db_path, eid)
        assert row["category"] == "Transport", (
            "Invalid category must not update the DB row"
        )

    # -- invalid date --------------------------------------------------

    def test_invalid_date_returns_200(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Food",
            "date": "not-a-date",
            "description": "Lunch",
        })
        assert resp.status_code == 200, (
            "Invalid date must re-render the form with status 200"
        )

    def test_invalid_date_shows_error(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Food",
            "date": "not-a-date",
            "description": "Lunch",
        })
        body = _body(resp)
        assert any(w in body.lower() for w in ["error", "date", "valid", "invalid"]), (
            "Invalid date must produce an error message"
        )

    def test_invalid_date_does_not_update_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Food",
            "date": "not-a-date",
            "description": "Lunch",
        })
        row = _query_expense(db_path, eid)
        assert row["date"] == "2026-04-15", (
            "Invalid date must not update the DB row"
        )


# ------------------------------------------------------------------ #
# 9. POST /expenses/<id>/edit — parametrized validation edge cases   #
# ------------------------------------------------------------------ #

class TestPostValidationParametrized:
    """Parametrized variants covering the spec's stated invalid inputs."""

    @pytest.mark.parametrize("bad_amount", [
        "",        # empty string
        "0",       # exactly zero
        "-1",      # negative
        "-0.01",   # tiny negative
        "abc",     # non-numeric string
        "  ",      # whitespace only
    ])
    def test_bad_amount_returns_200_and_does_not_update_db(
        self, auth_client, bad_amount
    ):
        c, uid, eid, db_path = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": bad_amount,
            "category": "Food",
            "date": "2026-03-20",
            "description": "Test",
        })
        assert resp.status_code == 200, (
            f"Invalid amount '{bad_amount}' must re-render the form (200)"
        )
        row = _query_expense(db_path, eid)
        assert row["amount"] == 75.50, (
            f"Invalid amount '{bad_amount}' must not change the DB row"
        )

    @pytest.mark.parametrize("bad_category", [
        "Hacking",
        "food",           # wrong case
        "FOOD",           # all-caps
        "",               # empty string
        "Other ",         # trailing space
        "Groceries",      # not in the list
        "<script>alert(1)</script>",  # injection attempt
    ])
    def test_bad_category_returns_200(self, auth_client, bad_category):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": bad_category,
            "date": "2026-03-20",
            "description": "Test",
        })
        assert resp.status_code == 200, (
            f"Invalid category '{bad_category}' must re-render the form (200)"
        )

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "2026/03/20",     # wrong separator
        "20-03-2026",     # DD-MM-YYYY
        "2026-13-01",     # month out of range
        "2026-00-10",     # month zero
        "abcdefg",
        "20260320",       # no separators
        "",               # empty string
    ])
    def test_bad_date_returns_200_and_does_not_update_db(
        self, auth_client, bad_date
    ):
        c, uid, eid, db_path = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Food",
            "date": bad_date,
            "description": "Test",
        })
        assert resp.status_code == 200, (
            f"Invalid date '{bad_date}' must re-render the form (200)"
        )
        row = _query_expense(db_path, eid)
        assert row["date"] == "2026-04-15", (
            f"Invalid date '{bad_date}' must not change the DB row"
        )


# ------------------------------------------------------------------ #
# 10. POST — optional description                                     #
# ------------------------------------------------------------------ #

class TestPostOptionalDescription:
    """Omitting or blanking description is valid; row updated with NULL description."""

    def test_no_description_redirects_302(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "80.0",
            "category": "Shopping",
            "date": "2026-06-01",
            # description omitted
        })
        assert resp.status_code == 302, (
            "Omitting description must still produce a 302 redirect"
        )

    def test_no_description_redirects_to_profile(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "80.0",
            "category": "Shopping",
            "date": "2026-06-01",
        })
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"No-description POST must redirect to /profile, got: {location}"
        )

    def test_no_description_stores_null_in_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "80.0",
            "category": "Shopping",
            "date": "2026-06-01",
        })
        row = _query_expense(db_path, eid)
        assert row["description"] is None, (
            "When description is omitted the DB must store NULL"
        )

    def test_blank_description_stores_null_in_db(self, auth_client):
        """Whitespace-only description must be treated as absent (NULL)."""
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/edit", data={
            "amount": "80.0",
            "category": "Shopping",
            "date": "2026-06-01",
            "description": "   ",
        })
        row = _query_expense(db_path, eid)
        assert row["description"] is None, (
            "Whitespace-only description must be stripped and stored as NULL"
        )

    def test_blank_description_still_redirects(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "80.0",
            "category": "Shopping",
            "date": "2026-06-01",
            "description": "   ",
        })
        assert resp.status_code == 302, (
            "Whitespace-only description must not be a validation error — must redirect"
        )


# ------------------------------------------------------------------ #
# 11. Form re-population on validation error                          #
# ------------------------------------------------------------------ #

class TestFormRepopulationOnError:
    """After a failed POST the form must echo the *submitted* (not original) values."""

    def test_submitted_amount_appears_after_invalid_category(self, auth_client):
        """The user-submitted amount should be retained on the re-rendered form."""
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "999.99",
            "category": "InvalidCat",
            "date": "2026-03-20",
            "description": "Some note",
        })
        body = _body(resp)
        assert "999.99" in body, (
            "The submitted amount (999.99) must be re-populated in the form after a "
            "category validation error"
        )

    def test_submitted_description_appears_after_invalid_date(self, auth_client):
        """The user-submitted description should be retained on the re-rendered form."""
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "50.0",
            "category": "Food",
            "date": "bad-date",
            "description": "My unique note 12345",
        })
        body = _body(resp)
        assert "My unique note 12345" in body, (
            "The submitted description must be re-populated in the form after a date "
            "validation error"
        )

    def test_submitted_date_appears_after_invalid_amount(self, auth_client):
        """The user-submitted date should be retained on the re-rendered form."""
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "abc",
            "category": "Food",
            "date": "2026-07-04",
            "description": "Independence",
        })
        body = _body(resp)
        assert "2026-07-04" in body, (
            "The submitted date must be re-populated in the form after an amount "
            "validation error"
        )


# ------------------------------------------------------------------ #
# 12. Profile page — Edit links                                        #
# ------------------------------------------------------------------ #

class TestProfileEditLinks:
    """The profile page transactions table must include an Edit link per row."""

    def test_profile_contains_edit_link_for_expense(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert f"/expenses/{eid}/edit" in body, (
            f"Profile page must contain an Edit link pointing to "
            f"/expenses/{eid}/edit for the seeded expense"
        )

    def test_profile_contains_edit_text(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "Edit" in body, (
            "Profile transaction table must include 'Edit' link text"
        )

    def test_profile_edit_links_for_multiple_expenses(self, client):
        """Each seeded expense row must have its own correctly-formed edit link."""
        c, db_path = client
        uid = _insert_user(db_path, name="Multi Link", email="multilink@example.com")
        eid1 = _insert_expense(db_path, uid, amount=10.0, category="Food",
                               date="2026-05-01", description="Exp one")
        eid2 = _insert_expense(db_path, uid, amount=20.0, category="Transport",
                               date="2026-05-02", description="Exp two")

        with c.session_transaction() as sess:
            sess["user_id"] = uid

        resp = c.get("/profile")
        body = _body(resp)
        assert f"/expenses/{eid1}/edit" in body, (
            f"Profile page must have an edit link for expense {eid1}"
        )
        assert f"/expenses/{eid2}/edit" in body, (
            f"Profile page must have an edit link for expense {eid2}"
        )

    def test_profile_actions_column_header_present(self, auth_client):
        """The transactions table must have an 'Actions' column header."""
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "Actions" in body, (
            "Profile transaction table must include an 'Actions' column header"
        )

    def test_get_recent_transactions_returns_id_field(self, isolated_db):
        """get_recent_transactions must include 'id' in each returned dict."""
        from database.queries import get_recent_transactions

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=55.0, category="Health",
                              date="2026-06-10", description="Checkup")

        transactions = get_recent_transactions(uid)
        assert len(transactions) == 1, "Expected exactly one transaction"
        assert "id" in transactions[0], (
            "get_recent_transactions must include 'id' in each row so templates "
            "can build edit links"
        )
        assert transactions[0]["id"] == eid, (
            "The 'id' field in the returned transaction must match the inserted expense id"
        )


# ------------------------------------------------------------------ #
# 13. DB side-effects — cross-user isolation                          #
# ------------------------------------------------------------------ #

class TestDbIsolation:
    """Editing one user's expense must never affect another user's data."""

    def test_edit_does_not_affect_other_users_expenses(self, client):
        c, db_path = client
        uid_a = _insert_user(db_path, name="Alice", email="alice_iso@example.com")
        uid_b = _insert_user(db_path, name="Bob",   email="bob_iso@example.com")
        eid_a = _insert_expense(db_path, uid_a, amount=100.0, category="Food",
                                date="2026-04-01", description="Alice's food")
        eid_b = _insert_expense(db_path, uid_b, amount=200.0, category="Bills",
                                date="2026-04-02", description="Bob's bill")

        # Log in as Alice and edit her own expense
        with c.session_transaction() as sess:
            sess["user_id"] = uid_a

        c.post(f"/expenses/{eid_a}/edit", data={
            "amount": "150.0",
            "category": "Shopping",
            "date": "2026-04-01",
            "description": "Alice updated",
        })

        # Bob's expense must be untouched
        row_b = _query_expense(db_path, eid_b)
        assert row_b["amount"] == 200.0, (
            "Bob's expense must not be affected by Alice's edit"
        )
        assert row_b["description"] == "Bob's bill", (
            "Bob's description must remain unchanged after Alice's edit"
        )

    @pytest.mark.parametrize("category", [
        "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
    ])
    def test_each_valid_category_can_be_saved_via_edit(self, auth_client, category):
        """Every one of the 7 fixed categories must be accepted and stored via edit."""
        c, uid, eid, db_path = auth_client
        resp = c.post(f"/expenses/{eid}/edit", data={
            "amount": "10.0",
            "category": category,
            "date": "2026-05-15",
            "description": f"Test {category}",
        })
        assert resp.status_code == 302, (
            f"Category '{category}' must be accepted and produce a 302 redirect"
        )
        row = _query_expense(db_path, eid)
        assert row["category"] == category, (
            f"Category '{category}' must be stored correctly in the DB after edit"
        )
