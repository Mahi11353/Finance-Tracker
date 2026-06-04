import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.db import get_db, init_db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)
from werkzeug.security import generate_password_hash
import app as flask_app


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets a fresh in-memory-equivalent DB via a temp file."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("database.db.DB_PATH", db_path)
    monkeypatch.setattr("database.queries.get_db", lambda: _get_test_db(db_path))

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
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
    yield db_path


def _get_test_db(path):
    import sqlite3
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _insert_user(db_path, name="Test User", email="test@example.com"):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name, email, generate_password_hash("pass1234"), "2026-01-15 10:00:00"),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def _insert_expenses(db_path, user_id):
    import sqlite3
    conn = sqlite3.connect(db_path)
    sample = [
        (user_id, 45.50,  "Food",          "2026-06-01", "Grocery run"),
        (user_id, 12.00,  "Transport",     "2026-06-02", "Bus pass top-up"),
        (user_id, 120.00, "Bills",         "2026-06-03", "Electricity bill"),
        (user_id, 30.00,  "Health",        "2026-06-05", "Pharmacy"),
        (user_id, 18.99,  "Entertainment", "2026-06-07", "Streaming subscription"),
        (user_id, 65.00,  "Shopping",      "2026-06-10", "New shoes"),
        (user_id, 8.50,   "Food",          "2026-06-12", "Coffee and snacks"),
        (user_id, 20.00,  "Other",         "2026-06-15", "Miscellaneous"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        sample,
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Unit tests — get_user_by_id                                         #
# ------------------------------------------------------------------ #

def test_get_user_by_id_valid(isolated_db):
    uid = _insert_user(isolated_db, name="Jane Doe", email="jane@example.com")
    result = get_user_by_id(uid)
    assert result is not None
    assert result["name"] == "Jane Doe"
    assert result["email"] == "jane@example.com"
    assert result["member_since"] == "January 2026"


def test_get_user_by_id_not_found(isolated_db):
    assert get_user_by_id(9999) is None


# ------------------------------------------------------------------ #
# Unit tests — get_summary_stats                                      #
# ------------------------------------------------------------------ #

def test_get_summary_stats_with_expenses(isolated_db):
    uid = _insert_user(isolated_db)
    _insert_expenses(isolated_db, uid)
    stats = get_summary_stats(uid)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"
    assert stats["total_spent"].startswith("₹")
    total_val = float(stats["total_spent"].replace("₹", ""))
    assert abs(total_val - 319.99) < 0.01


def test_get_summary_stats_no_expenses(isolated_db):
    uid = _insert_user(isolated_db)
    stats = get_summary_stats(uid)
    assert stats == {"total_spent": "₹0.00", "transaction_count": 0, "top_category": "—"}


# ------------------------------------------------------------------ #
# Unit tests — get_recent_transactions                                #
# ------------------------------------------------------------------ #

def test_get_recent_transactions_with_expenses(isolated_db):
    uid = _insert_user(isolated_db)
    _insert_expenses(isolated_db, uid)
    txns = get_recent_transactions(uid)
    assert len(txns) == 8
    for t in txns:
        assert "date" in t and "description" in t and "category" in t and "amount" in t
        assert t["amount"].startswith("₹")
    # newest-first: Jun 15 should be first
    assert "Jun 15" in txns[0]["date"]


def test_get_recent_transactions_no_expenses(isolated_db):
    uid = _insert_user(isolated_db)
    assert get_recent_transactions(uid) == []


# ------------------------------------------------------------------ #
# Unit tests — get_category_breakdown                                 #
# ------------------------------------------------------------------ #

def test_get_category_breakdown_with_expenses(isolated_db):
    uid = _insert_user(isolated_db)
    _insert_expenses(isolated_db, uid)
    breakdown = get_category_breakdown(uid)
    assert len(breakdown) == 7
    names = [c["name"] for c in breakdown]
    assert "Bills" in names
    pct_sum = sum(c["pct"] for c in breakdown)
    assert pct_sum == 100
    for c in breakdown:
        assert isinstance(c["pct"], int)
        assert c["total"].startswith("₹")
    # Bills should be first (highest total)
    assert breakdown[0]["name"] == "Bills"


def test_get_category_breakdown_no_expenses(isolated_db):
    uid = _insert_user(isolated_db)
    assert get_category_breakdown(uid) == []


# ------------------------------------------------------------------ #
# Route tests                                                         #
# ------------------------------------------------------------------ #

@pytest.fixture
def client(isolated_db, monkeypatch):
    monkeypatch.setattr("database.db.DB_PATH", isolated_db)
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"
    with flask_app.app.test_client() as c:
        yield c, isolated_db


def test_profile_unauthenticated_redirects(client):
    c, _ = client
    resp = c.get("/profile")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_profile_authenticated_returns_200(client):
    c, db_path = client
    uid = _insert_user(db_path, name="Demo User", email="demo@spendly.com")
    _insert_expenses(db_path, uid)
    with c.session_transaction() as sess:
        sess["user_id"] = uid
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹" in body
    assert "Bills" in body
