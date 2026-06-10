"""
tests/test_09-delete-expense.py

Pytest test suite for the Spendora "Delete Expense" feature (Step 09).
Tests are written against the feature specification only; no implementation
details are reverse-engineered from the source.

Spec: .claude/specs/09-delete-expense.md

Coverage:
- Unit tests for database.queries.delete_expense
- POST /expenses/<id>/delete — auth guard, happy path (redirect + DB removal),
  ownership 404, non-existent id 404, GET returns 405
- Profile page — delete form present with correct action and method per row
- DB isolation — deleting one user's expense never touches another user's data
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


def _query_expense(db_path: str, expense_id: int):
    """Return a single expense row as a dict, or None if not found."""
    conn = _get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _count_all_expenses(db_path: str) -> int:
    """Return the total number of expense rows across all users."""
    conn = _get_conn(db_path)
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    conn.close()
    return count


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """
    Each test gets a fresh, empty SQLite database.
    Both database.db and database.queries are patched to use this path.
    """
    db_path = str(tmp_path / "test_delete_expense.db")
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
    uid = _insert_user(db_path, name="Delete Tester", email="delete@example.com")
    eid = _insert_expense(
        db_path, uid,
        amount=99.0,
        category="Transport",
        date="2026-05-10",
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
# 1. Unit tests — delete_expense                                      #
# ------------------------------------------------------------------ #

class TestDeleteExpenseUnit:
    """Direct unit tests for database.queries.delete_expense."""

    def test_valid_id_correct_user_removes_row(self, isolated_db):
        """delete_expense with the correct user_id must remove the row from the DB."""
        from database.queries import delete_expense

        uid = _insert_user(isolated_db)
        eid = _insert_expense(isolated_db, uid, amount=40.0, category="Food",
                              date="2026-04-01", description="Grocery")

        delete_expense(eid, uid)

        row = _query_expense(isolated_db, eid)
        assert row is None, (
            "delete_expense must remove the row when expense_id and user_id match"
        )

    def test_valid_id_correct_user_row_count_decrements(self, isolated_db):
        """After deleting, the total expense count must decrease by 1."""
        from database.queries import delete_expense

        uid = _insert_user(isolated_db)
        _insert_expense(isolated_db, uid, amount=10.0, category="Bills",
                        date="2026-04-01", description="Electric")
        eid = _insert_expense(isolated_db, uid, amount=20.0, category="Food",
                              date="2026-04-02", description="Dinner")

        before = _count_all_expenses(isolated_db)
        delete_expense(eid, uid)
        after = _count_all_expenses(isolated_db)

        assert after == before - 1, (
            "delete_expense must decrement the total expense row count by exactly 1"
        )

    def test_valid_id_wrong_user_row_remains(self, isolated_db):
        """delete_expense with the wrong user_id must not remove the row."""
        from database.queries import delete_expense

        uid_owner = _insert_user(isolated_db, name="Owner", email="owner@example.com")
        uid_other = _insert_user(isolated_db, name="Other", email="other@example.com")
        eid = _insert_expense(isolated_db, uid_owner, amount=55.0, category="Health",
                              date="2026-04-10", description="Doctor")

        delete_expense(eid, uid_other)

        row = _query_expense(isolated_db, eid)
        assert row is not None, (
            "delete_expense with the wrong user_id must leave the row in the DB"
        )

    def test_valid_id_wrong_user_does_not_raise(self, isolated_db):
        """delete_expense with the wrong user_id must not raise any exception."""
        from database.queries import delete_expense

        uid_owner = _insert_user(isolated_db, name="OwnerX", email="ownerx@example.com")
        uid_other = _insert_user(isolated_db, name="OtherX", email="otherx@example.com")
        eid = _insert_expense(isolated_db, uid_owner, amount=30.0, category="Shopping",
                              date="2026-05-01", description="Shoes")

        try:
            delete_expense(eid, uid_other)
        except Exception as exc:
            pytest.fail(
                f"delete_expense raised an unexpected exception with wrong user_id: {exc}"
            )

    def test_nonexistent_id_does_not_raise(self, isolated_db):
        """delete_expense with a non-existent expense_id must not raise any exception."""
        from database.queries import delete_expense

        uid = _insert_user(isolated_db)

        try:
            delete_expense(99999, uid)
        except Exception as exc:
            pytest.fail(
                f"delete_expense raised an unexpected exception for non-existent id: {exc}"
            )

    def test_nonexistent_id_db_unchanged(self, isolated_db):
        """delete_expense with a non-existent id must leave the DB row count unchanged."""
        from database.queries import delete_expense

        uid = _insert_user(isolated_db)
        _insert_expense(isolated_db, uid, amount=15.0, category="Other",
                        date="2026-05-01", description="Misc")

        before = _count_all_expenses(isolated_db)
        delete_expense(99999, uid)
        after = _count_all_expenses(isolated_db)

        assert after == before, (
            "delete_expense with a non-existent id must not change the DB row count"
        )

    def test_delete_does_not_affect_other_expenses_same_user(self, isolated_db):
        """Deleting one expense must not remove a sibling expense owned by the same user."""
        from database.queries import delete_expense

        uid = _insert_user(isolated_db)
        eid_keep = _insert_expense(isolated_db, uid, amount=10.0, category="Food",
                                   date="2026-04-01", description="Breakfast")
        eid_del  = _insert_expense(isolated_db, uid, amount=20.0, category="Transport",
                                   date="2026-04-02", description="Bus")

        delete_expense(eid_del, uid)

        row_keep = _query_expense(isolated_db, eid_keep)
        assert row_keep is not None, (
            "delete_expense must not remove sibling expenses owned by the same user"
        )
        assert row_keep["amount"] == 10.0, (
            "The sibling expense's amount must be unchanged after deleting a different expense"
        )

    def test_delete_does_not_affect_other_users_expense(self, isolated_db):
        """Deleting an expense must not remove another user's expense even if amounts match."""
        from database.queries import delete_expense

        uid_a = _insert_user(isolated_db, name="Alice", email="alice@example.com")
        uid_b = _insert_user(isolated_db, name="Bob",   email="bob@example.com")
        eid_a = _insert_expense(isolated_db, uid_a, amount=50.0, category="Bills",
                                date="2026-05-01", description="Alice's bill")
        eid_b = _insert_expense(isolated_db, uid_b, amount=50.0, category="Bills",
                                date="2026-05-01", description="Bob's bill")

        delete_expense(eid_a, uid_a)

        row_b = _query_expense(isolated_db, eid_b)
        assert row_b is not None, (
            "delete_expense must not delete another user's expense"
        )


# ------------------------------------------------------------------ #
# 2. Auth guard — unauthenticated POST                                #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    """Unauthenticated POST to /expenses/<id>/delete must redirect to /login."""

    def test_unauthenticated_post_returns_302(self, client):
        c, db_path = client
        uid = _insert_user(db_path, name="Guard User", email="guard@example.com")
        eid = _insert_expense(db_path, uid)
        resp = c.post(f"/expenses/{eid}/delete")
        assert resp.status_code == 302, (
            "Unauthenticated POST /expenses/<id>/delete must return 302"
        )

    def test_unauthenticated_post_redirects_to_login(self, client):
        c, db_path = client
        uid = _insert_user(db_path, name="Guard User2", email="guard2@example.com")
        eid = _insert_expense(db_path, uid)
        resp = c.post(f"/expenses/{eid}/delete")
        location = resp.headers.get("Location", "")
        assert "/login" in location, (
            f"Unauthenticated POST must redirect to /login, got Location: {location}"
        )

    def test_unauthenticated_post_does_not_delete_row(self, client):
        """An unauthenticated POST must not remove any expense from the DB."""
        c, db_path = client
        uid = _insert_user(db_path, name="Guard User3", email="guard3@example.com")
        eid = _insert_expense(db_path, uid)

        c.post(f"/expenses/{eid}/delete")

        row = _query_expense(db_path, eid)
        assert row is not None, (
            "An unauthenticated POST must not delete the expense row from the DB"
        )


# ------------------------------------------------------------------ #
# 3. POST — authenticated, own expense (happy path)                  #
# ------------------------------------------------------------------ #

class TestPostOwnExpense:
    """Authenticated POST on an owned expense must redirect and remove the row."""

    def test_own_expense_returns_302(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/delete")
        assert resp.status_code == 302, (
            "Authenticated POST /expenses/<id>/delete (own expense) must return 302"
        )

    def test_own_expense_redirects_to_profile(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.post(f"/expenses/{eid}/delete")
        location = resp.headers.get("Location", "")
        assert "/profile" in location, (
            f"Successful delete must redirect to /profile, got Location: {location}"
        )

    def test_own_expense_row_removed_from_db(self, auth_client):
        c, uid, eid, db_path = auth_client
        c.post(f"/expenses/{eid}/delete")
        row = _query_expense(db_path, eid)
        assert row is None, (
            "After a successful DELETE POST the expense row must no longer exist in the DB"
        )

    def test_own_expense_total_count_decrements(self, auth_client):
        """The total row count must drop by 1 after a successful delete."""
        c, uid, eid, db_path = auth_client
        before = _count_all_expenses(db_path)
        c.post(f"/expenses/{eid}/delete")
        after = _count_all_expenses(db_path)
        assert after == before - 1, (
            "Successful delete must decrement the total expense row count by exactly 1"
        )

    def test_own_expense_delete_does_not_affect_other_users(self, client):
        """Deleting user A's expense via the route must not delete user B's expense."""
        c, db_path = client
        uid_a = _insert_user(db_path, name="Alice", email="alice_route@example.com")
        uid_b = _insert_user(db_path, name="Bob",   email="bob_route@example.com")
        eid_a = _insert_expense(db_path, uid_a, amount=100.0, category="Food",
                                date="2026-04-01", description="Alice's lunch")
        eid_b = _insert_expense(db_path, uid_b, amount=200.0, category="Bills",
                                date="2026-04-02", description="Bob's bill")

        with c.session_transaction() as sess:
            sess["user_id"] = uid_a

        c.post(f"/expenses/{eid_a}/delete")

        row_b = _query_expense(db_path, eid_b)
        assert row_b is not None, (
            "Deleting user A's expense must not remove user B's expense from the DB"
        )
        assert row_b["amount"] == 200.0, (
            "User B's expense amount must be unchanged after user A's delete"
        )


# ------------------------------------------------------------------ #
# 4. POST — authenticated, other user's expense → 404                #
# ------------------------------------------------------------------ #

class TestPostOtherUsersExpense:
    """POST to another user's expense must return 404 and leave DB unchanged."""

    def test_other_users_expense_returns_404(self, client):
        c, db_path = client
        uid_owner = _insert_user(db_path, name="Owner", email="owner_del@example.com")
        uid_other = _insert_user(db_path, name="Other", email="other_del@example.com")
        eid = _insert_expense(db_path, uid_owner, amount=60.0, category="Health",
                              date="2026-05-05", description="Checkup")

        with c.session_transaction() as sess:
            sess["user_id"] = uid_other

        resp = c.post(f"/expenses/{eid}/delete")
        assert resp.status_code == 404, (
            "POST to another user's expense must return 404"
        )

    def test_other_users_expense_row_still_exists(self, client):
        """After a cross-user POST attempt the target row must still be in the DB."""
        c, db_path = client
        uid_owner = _insert_user(db_path, name="Owner2", email="owner2_del@example.com")
        uid_other = _insert_user(db_path, name="Other2", email="other2_del@example.com")
        eid = _insert_expense(db_path, uid_owner, amount=60.0, category="Health",
                              date="2026-05-05", description="Checkup")

        with c.session_transaction() as sess:
            sess["user_id"] = uid_other

        c.post(f"/expenses/{eid}/delete")

        row = _query_expense(db_path, eid)
        assert row is not None, (
            "The target expense row must still exist after a cross-user delete attempt"
        )

    def test_other_users_expense_row_amount_unchanged(self, client):
        """The amount on the target row must remain intact after a cross-user attempt."""
        c, db_path = client
        uid_owner = _insert_user(db_path, name="Owner3", email="owner3_del@example.com")
        uid_other = _insert_user(db_path, name="Other3", email="other3_del@example.com")
        eid = _insert_expense(db_path, uid_owner, amount=77.0, category="Shopping",
                              date="2026-05-06", description="Clothes")

        with c.session_transaction() as sess:
            sess["user_id"] = uid_other

        c.post(f"/expenses/{eid}/delete")

        row = _query_expense(db_path, eid)
        assert row is not None and row["amount"] == 77.0, (
            "Expense amount must be unchanged after a cross-user delete attempt"
        )


# ------------------------------------------------------------------ #
# 5. POST — authenticated, non-existent expense id → 404             #
# ------------------------------------------------------------------ #

class TestPostNonexistentExpense:
    """POST to a non-existent expense id must return 404."""

    def test_nonexistent_id_returns_404(self, client):
        c, db_path = client
        uid = _insert_user(db_path, name="Lonely User", email="lonely@example.com")
        with c.session_transaction() as sess:
            sess["user_id"] = uid

        resp = c.post("/expenses/99999/delete")
        assert resp.status_code == 404, (
            "POST /expenses/<non-existent-id>/delete must return 404"
        )

    def test_nonexistent_id_db_row_count_unchanged(self, client):
        """A 404 response must not alter the total expense row count."""
        c, db_path = client
        uid = _insert_user(db_path, name="Lonely User2", email="lonely2@example.com")
        _insert_expense(db_path, uid, amount=30.0, category="Other",
                        date="2026-06-01", description="Misc")

        with c.session_transaction() as sess:
            sess["user_id"] = uid

        before = _count_all_expenses(db_path)
        c.post("/expenses/99999/delete")
        after = _count_all_expenses(db_path)

        assert after == before, (
            "A 404 on a non-existent id must not change the DB row count"
        )


# ------------------------------------------------------------------ #
# 6. GET /expenses/<id>/delete → 405 Method Not Allowed              #
# ------------------------------------------------------------------ #

class TestGetMethodNotAllowed:
    """A GET request to the delete URL must return 405 regardless of auth state."""

    def test_unauthenticated_get_returns_405(self, client):
        c, db_path = client
        uid = _insert_user(db_path, name="Method User", email="method@example.com")
        eid = _insert_expense(db_path, uid)
        resp = c.get(f"/expenses/{eid}/delete")
        assert resp.status_code == 405, (
            "GET /expenses/<id>/delete must return 405 Method Not Allowed"
        )

    def test_authenticated_get_returns_405(self, auth_client):
        c, uid, eid, _ = auth_client
        resp = c.get(f"/expenses/{eid}/delete")
        assert resp.status_code == 405, (
            "Authenticated GET /expenses/<id>/delete must return 405 Method Not Allowed"
        )

    def test_get_does_not_delete_row(self, auth_client):
        """A GET request must not remove the expense row from the DB."""
        c, uid, eid, db_path = auth_client
        c.get(f"/expenses/{eid}/delete")
        row = _query_expense(db_path, eid)
        assert row is not None, (
            "A GET request to the delete URL must not remove the expense from the DB"
        )


# ------------------------------------------------------------------ #
# 7. Profile page — delete form present per expense row              #
# ------------------------------------------------------------------ #

class TestProfileDeleteButton:
    """The profile page must render a delete form for each expense row."""

    def test_profile_contains_delete_form_action(self, auth_client):
        """Profile page must include a form whose action points to the delete URL."""
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert f"/expenses/{eid}/delete" in body, (
            f"Profile page must contain a form action pointing to "
            f"/expenses/{eid}/delete for the seeded expense"
        )

    def test_profile_delete_form_method_is_post(self, auth_client):
        """The delete form on the profile page must declare method POST."""
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp).lower()
        # The form that targets the delete URL should use POST
        assert 'method="post"' in body or "method='post'" in body, (
            "The delete form on the profile page must declare method POST"
        )

    def test_profile_contains_delete_button_text(self, auth_client):
        """A visible 'Delete' label must appear in the profile transaction table."""
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "Delete" in body, (
            "Profile page transaction table must include a 'Delete' button or label"
        )

    def test_profile_delete_links_for_multiple_expenses(self, client):
        """Each expense row must have its own correctly-formed delete form action."""
        c, db_path = client
        uid  = _insert_user(db_path, name="Multi Del", email="multidel@example.com")
        eid1 = _insert_expense(db_path, uid, amount=10.0, category="Food",
                               date="2026-05-01", description="Exp one")
        eid2 = _insert_expense(db_path, uid, amount=20.0, category="Transport",
                               date="2026-05-02", description="Exp two")

        with c.session_transaction() as sess:
            sess["user_id"] = uid

        resp = c.get("/profile")
        body = _body(resp)
        assert f"/expenses/{eid1}/delete" in body, (
            f"Profile page must have a delete form action for expense {eid1}"
        )
        assert f"/expenses/{eid2}/delete" in body, (
            f"Profile page must have a delete form action for expense {eid2}"
        )

    def test_profile_page_also_has_edit_links(self, auth_client):
        """The Actions column must still include edit links alongside the new delete forms."""
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert f"/expenses/{eid}/edit" in body, (
            "Profile page must retain edit links alongside the new delete forms"
        )

    def test_profile_actions_column_header_present(self, auth_client):
        """The transactions table must still carry an 'Actions' column header."""
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "Actions" in body, (
            "Profile transaction table must include an 'Actions' column header"
        )

    def test_profile_page_extends_base_template(self, auth_client):
        """Profile page must extend base.html — verified by the Spendora brand appearing."""
        c, uid, eid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "Spendora" in body, (
            "Profile page must extend base.html; 'Spendora' brand/title must appear"
        )


# ------------------------------------------------------------------ #
# 8. DB isolation — cross-user safety after route-level delete        #
# ------------------------------------------------------------------ #

class TestDbIsolation:
    """Deleting one user's expense via the route must never affect another user."""

    def test_delete_route_scoped_to_authenticated_user(self, client):
        """
        User A deletes their own expense via POST.
        User B's expenses must remain intact.
        """
        c, db_path = client
        uid_a = _insert_user(db_path, name="Alice", email="alice_iso@example.com")
        uid_b = _insert_user(db_path, name="Bob",   email="bob_iso@example.com")
        eid_a = _insert_expense(db_path, uid_a, amount=100.0, category="Food",
                                date="2026-04-01", description="Alice food")
        eid_b = _insert_expense(db_path, uid_b, amount=200.0, category="Bills",
                                date="2026-04-02", description="Bob bill")

        with c.session_transaction() as sess:
            sess["user_id"] = uid_a

        resp = c.post(f"/expenses/{eid_a}/delete")
        assert resp.status_code == 302, "Alice's own delete must succeed (302)"

        # Alice's row is gone
        assert _query_expense(db_path, eid_a) is None, (
            "Alice's expense must be removed after a successful delete"
        )
        # Bob's row is untouched
        row_b = _query_expense(db_path, eid_b)
        assert row_b is not None, (
            "Bob's expense must not be affected by Alice's delete"
        )
        assert row_b["amount"] == 200.0, (
            "Bob's expense amount must be unchanged after Alice's delete"
        )

    def test_delete_not_applied_when_session_belongs_to_non_owner(self, client):
        """
        When a logged-in user attempts to delete another user's expense via POST,
        the route returns 404 and the owner's expense remains in the DB.
        """
        c, db_path = client
        uid_owner = _insert_user(db_path, name="RealOwner", email="realowner@example.com")
        uid_attacker = _insert_user(db_path, name="Attacker", email="attacker@example.com")
        eid = _insert_expense(db_path, uid_owner, amount=500.0, category="Shopping",
                              date="2026-06-01", description="Expensive purchase")

        with c.session_transaction() as sess:
            sess["user_id"] = uid_attacker

        resp = c.post(f"/expenses/{eid}/delete")
        assert resp.status_code == 404, (
            "Attempting to delete another user's expense must return 404"
        )

        row = _query_expense(db_path, eid)
        assert row is not None, (
            "The owner's expense must still exist after an attacker's delete attempt"
        )
        assert row["amount"] == 500.0, (
            "The expense amount must be unchanged after the failed delete attempt"
        )
