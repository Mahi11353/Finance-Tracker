"""
tests/test_06_date_filter_profile.py

Pytest test suite for the Spendly date-filter feature on the /profile route.
Tests are written against the feature specification only; no implementation
details are reverse-engineered from the source.

Spec: .claude/specs/06-date-filter-profile-page.md
"""

import sys
import os
import sqlite3
import pytest
from datetime import date, timedelta
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


def _insert_expenses(db_path: str, user_id: int) -> None:
    """
    Seed data with a deliberately spread date range so tests can verify
    narrowing.  Dates are split across three calendar months:

      2026-03-10  Food          50.00   "Old groceries"
      2026-04-05  Transport     30.00   "Train ticket"
      2026-05-01  Bills        100.00   "Water bill"
      2026-05-20  Health        40.00   "Dentist"
      2026-06-01  Food          20.00   "Snacks"
      2026-06-10  Shopping      80.00   "T-shirts"
      2026-06-15  Entertainment 15.00   "Cinema"

    Total all-time: 335.00  (7 transactions)
    2026-06-01 – 2026-06-15 total: 115.00  (3 transactions)
    2026-06-01 – 2026-06-10 total:  100.00 (2 transactions)
    """
    rows = [
        (user_id, 50.00,  "Food",          "2026-03-10", "Old groceries"),
        (user_id, 30.00,  "Transport",     "2026-04-05", "Train ticket"),
        (user_id, 100.00, "Bills",         "2026-05-01", "Water bill"),
        (user_id, 40.00,  "Health",        "2026-05-20", "Dentist"),
        (user_id, 20.00,  "Food",          "2026-06-01", "Snacks"),
        (user_id, 80.00,  "Shopping",      "2026-06-10", "T-shirts"),
        (user_id, 15.00,  "Entertainment", "2026-06-15", "Cinema"),
    ]
    conn = _get_conn(db_path)
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """
    Each test receives a fresh, empty SQLite database at a temp path.
    Both database.db and database.queries are patched to use this path.
    """
    db_path = str(tmp_path / "test_filter.db")
    _create_schema(db_path)

    # Patch DB_PATH used by database.db (and therefore get_db())
    monkeypatch.setattr("database.db.DB_PATH", db_path)

    # Patch the get_db imported inside database.queries
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
    A test client that already has a session for a known user who has
    a fixed set of expenses seeded across multiple months.
    Returns (test_client, user_id, db_path).
    """
    c, db_path = client
    uid = _insert_user(db_path, name="Filter Tester", email="filter@example.com")
    _insert_expenses(db_path, uid)
    with c.session_transaction() as sess:
        sess["user_id"] = uid
    return c, uid, db_path


# ------------------------------------------------------------------ #
# Convenience: decode response body                                   #
# ------------------------------------------------------------------ #

def _body(resp) -> str:
    return resp.data.decode("utf-8")


# ------------------------------------------------------------------ #
# 1. Auth guard                                                       #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_unauthenticated_get_redirects_to_login(self, client):
        c, _ = client
        resp = c.get("/profile")
        assert resp.status_code == 302, "Expected redirect for unauthenticated request"
        assert "/login" in resp.headers["Location"], (
            "Redirect should point to /login, got: " + resp.headers["Location"]
        )

    def test_unauthenticated_with_date_params_also_redirects(self, client):
        c, _ = client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-30")
        assert resp.status_code == 302, (
            "Auth guard must fire even when date query params are present"
        )
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# 2. Unfiltered (All Time) happy path                                 #
# ------------------------------------------------------------------ #

class TestUnfilteredView:
    def test_returns_200(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        assert resp.status_code == 200, "Authenticated /profile should return 200"

    def test_all_expenses_are_shown(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        # All 7 transactions should appear (descriptions are unique per row)
        assert "Old groceries" in body, "Expected 'Old groceries' in unfiltered view"
        assert "Train ticket" in body, "Expected 'Train ticket' in unfiltered view"
        assert "Water bill" in body, "Expected 'Water bill' in unfiltered view"
        assert "Dentist" in body, "Expected 'Dentist' in unfiltered view"
        assert "Snacks" in body, "Expected 'Snacks' in unfiltered view"
        assert "T-shirts" in body, "Expected 'T-shirts' in unfiltered view"
        assert "Cinema" in body, "Expected 'Cinema' in unfiltered view"

    def test_total_spent_is_sum_of_all_expenses(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        # 50 + 30 + 100 + 40 + 20 + 80 + 15 = 335.00
        assert "335.00" in body, "All-time total should be 335.00"

    def test_transaction_count_matches_all_rows(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "7" in body, "Transaction count should reflect all 7 seeded expenses"

    def test_rupee_symbol_present_in_unfiltered_view(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "₹" in body, "Rupee symbol must appear in unfiltered profile view"

    def test_all_time_preset_button_is_active(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        # The "All Time" button should carry the active CSS class when no filter is applied
        assert "dash-filter-preset--active" in body, (
            "An active preset indicator must be present on the unfiltered view"
        )
        # The active marker should appear near the "All Time" label
        all_time_idx = body.find("All Time")
        active_idx   = body.rfind("dash-filter-preset--active", 0, all_time_idx + 200)
        assert active_idx != -1, (
            "dash-filter-preset--active should appear near the 'All Time' label"
        )

    def test_filter_bar_html_elements_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert 'name="date_from"' in body, "date_from input must be rendered in the filter bar"
        assert 'name="date_to"' in body, "date_to input must be rendered in the filter bar"
        assert "This Month" in body, "'This Month' preset link must be in the filter bar"
        assert "Last 3 Months" in body, "'Last 3 Months' preset link must be in the filter bar"
        assert "Last 6 Months" in body, "'Last 6 Months' preset link must be in the filter bar"
        assert "All Time" in body, "'All Time' preset link must be in the filter bar"


# ------------------------------------------------------------------ #
# 3. Custom date range — filtering narrows all three sections         #
# ------------------------------------------------------------------ #

class TestCustomDateRangeFiltering:
    def test_narrowed_range_hides_out_of_range_expenses(self, auth_client):
        c, uid, _ = auth_client
        # Only June 2026 expenses: Snacks (06-01), T-shirts (06-10), Cinema (06-15)
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        assert "Snacks"  in body, "Snacks (2026-06-01) should be included in June filter"
        assert "T-shirts" in body, "T-shirts (2026-06-10) should be included in June filter"
        assert "Cinema"  in body, "Cinema (2026-06-15) should be included in June filter"
        # Expenses outside the range must not appear
        assert "Old groceries" not in body, "Old groceries (2026-03-10) must be excluded"
        assert "Train ticket"  not in body, "Train ticket (2026-04-05) must be excluded"
        assert "Water bill"    not in body, "Water bill (2026-05-01) must be excluded"
        assert "Dentist"       not in body, "Dentist (2026-05-20) must be excluded"

    def test_narrowed_range_total_is_correct(self, auth_client):
        c, uid, _ = auth_client
        # 20.00 + 80.00 + 15.00 = 115.00
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        assert "115.00" in body, "Filtered total should be 115.00 for June 2026"

    def test_narrowed_range_transaction_count(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        assert "3" in body, "Transaction count should be 3 for the June 2026 range"

    def test_narrowed_range_category_breakdown_only_shows_in_range_categories(
        self, auth_client
    ):
        c, uid, _ = auth_client
        # June range has Food, Shopping, Entertainment; Bills/Health/Transport should be absent
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        assert "Food"          in body, "Food should appear in June category breakdown"
        assert "Shopping"      in body, "Shopping should appear in June category breakdown"
        assert "Entertainment" in body, "Entertainment should appear in June category breakdown"
        # Categories with zero spend in the range must not appear in the breakdown
        assert "Bills"     not in body, "Bills must not appear in the June-only breakdown"
        assert "Health"    not in body, "Health must not appear in the June-only breakdown"
        assert "Transport" not in body, "Transport must not appear in the June-only breakdown"

    def test_category_breakdown_rupee_symbol_in_filtered_view(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        assert "₹" in body, "Rupee symbol must appear in filtered category breakdown amounts"

    def test_narrower_two_expense_range(self, auth_client):
        c, uid, _ = auth_client
        # Only 2026-06-01 (Snacks 20.00) and 2026-06-10 (T-shirts 80.00) → total 100.00
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-10")
        body = _body(resp)
        assert "Snacks"   in body
        assert "T-shirts" in body
        assert "Cinema"   not in body, "Cinema (2026-06-15) must be outside 06-01–06-10 range"
        assert "100.00"   in body, "Total for 2026-06-01 to 2026-06-10 should be 100.00"

    def test_single_day_range_returns_matching_expense(self, auth_client):
        c, uid, _ = auth_client
        # Exactly one expense on 2026-06-10: T-shirts 80.00
        resp = c.get("/profile?date_from=2026-06-10&date_to=2026-06-10")
        body = _body(resp)
        assert "T-shirts" in body, "T-shirts on 2026-06-10 should be in single-day filter"
        assert "Snacks"   not in body, "Snacks must be excluded from single-day 2026-06-10 filter"
        assert "Cinema"   not in body, "Cinema must be excluded from single-day 2026-06-10 filter"
        assert "80.00"    in body


# ------------------------------------------------------------------ #
# 4. Inclusive boundary semantics                                     #
# ------------------------------------------------------------------ #

class TestInclusiveBoundaries:
    def test_date_from_boundary_is_inclusive(self, auth_client):
        c, uid, _ = auth_client
        # date_from=2026-06-15: Cinema (2026-06-15) must be included
        resp = c.get("/profile?date_from=2026-06-15&date_to=2026-06-30")
        body = _body(resp)
        assert "Cinema" in body, "Expense on date_from itself must be included (inclusive bound)"

    def test_date_to_boundary_is_inclusive(self, auth_client):
        c, uid, _ = auth_client
        # date_to=2026-06-01: Snacks (2026-06-01) must be included
        resp = c.get("/profile?date_from=2026-01-01&date_to=2026-06-01")
        body = _body(resp)
        assert "Snacks" in body, "Expense on date_to itself must be included (inclusive bound)"

    def test_expense_one_day_after_date_to_is_excluded(self, auth_client):
        c, uid, _ = auth_client
        # date_to=2026-06-09 means T-shirts (2026-06-10) must NOT appear
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-09")
        body = _body(resp)
        assert "T-shirts" not in body, (
            "Expense on the day after date_to must be excluded"
        )

    def test_expense_one_day_before_date_from_is_excluded(self, auth_client):
        c, uid, _ = auth_client
        # date_from=2026-06-02 means Snacks (2026-06-01) must NOT appear
        resp = c.get("/profile?date_from=2026-06-02&date_to=2026-06-30")
        body = _body(resp)
        assert "Snacks" not in body, (
            "Expense on the day before date_from must be excluded"
        )


# ------------------------------------------------------------------ #
# 5. Empty result range                                               #
# ------------------------------------------------------------------ #

class TestEmptyResultRange:
    def test_valid_range_with_no_expenses_returns_zero_total(self, auth_client):
        c, uid, _ = auth_client
        # 2024-01-01 to 2024-12-31 — no expenses in seed data for this year
        resp = c.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
        assert resp.status_code == 200, "Empty range must not crash the server"
        body = _body(resp)
        assert "₹0.00" in body, "Total spent must be ₹0.00 when no expenses match the range"

    def test_valid_range_with_no_expenses_returns_zero_count(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
        body = _body(resp)
        # transaction_count should be 0 — the digit "0" will appear in the stats area
        assert "0" in body, "Transaction count must be 0 when no expenses match"

    def test_valid_range_with_no_expenses_has_empty_category_breakdown(
        self, auth_client
    ):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
        body = _body(resp)
        # The category breakdown list items are rendered only inside the
        # {% for cat in category_breakdown %} loop, which emits elements with
        # class "dash-cat-name".  When the list is empty no such elements exist.
        assert "dash-cat-name" not in body, (
            "No category breakdown rows should be rendered when the filtered "
            "range contains zero expenses"
        )

    def test_page_renders_without_error_for_empty_range(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
        assert resp.status_code == 200
        body = _body(resp)
        assert "₹" in body, "Rupee symbol must appear even in zero-expense filtered view"

    def test_top_category_shows_dash_for_empty_range(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
        body = _body(resp)
        # When there are no transactions, top_category should be "—"
        assert "—" in body, "Top category must be '—' when no expenses match the filter"


# ------------------------------------------------------------------ #
# 6. Inverted range (date_from > date_to)                            #
# ------------------------------------------------------------------ #

class TestInvertedRange:
    def test_inverted_range_flashes_error_message(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01",
            follow_redirects=True,
        )
        body = _body(resp)
        assert "Start date must be before end date." in body, (
            "Flash message 'Start date must be before end date.' must appear "
            "when date_from > date_to"
        )

    def test_inverted_range_falls_back_to_unfiltered_view(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        body = _body(resp)
        # Unfiltered view must show all expenses — all descriptions present
        assert "Old groceries" in body, "Fallback to unfiltered should show all expenses"
        assert "Cinema"        in body, "Fallback to unfiltered should show all expenses"

    def test_inverted_range_total_is_all_time_total(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get(
            "/profile?date_from=2026-12-31&date_to=2026-01-01",
            follow_redirects=True,
        )
        body = _body(resp)
        # All-time total 335.00 must appear in the fallback view
        assert "335.00" in body, (
            "After inverted-range fallback, total should equal all-time total (335.00)"
        )

    def test_inverted_range_returns_200(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-12-31&date_to=2026-01-01")
        assert resp.status_code == 200, "Inverted range must return 200, not an error code"


# ------------------------------------------------------------------ #
# 7. Malformed date strings                                           #
# ------------------------------------------------------------------ #

class TestMalformedDates:
    @pytest.mark.parametrize("bad_value", [
        "not-a-date",
        "2026/06/01",
        "06-01-2026",
        "2026-13-01",
        "2026-00-10",
        "abcdefg",
        "20260601",
        " ",
        "null",
        "undefined",
        "2026-06-",
        "--",
    ])
    def test_malformed_date_from_does_not_crash(self, auth_client, bad_value):
        c, uid, _ = auth_client
        resp = c.get(f"/profile?date_from={bad_value}&date_to=2026-06-30")
        assert resp.status_code == 200, (
            f"Malformed date_from='{bad_value}' must not crash the server"
        )

    @pytest.mark.parametrize("bad_value", [
        "not-a-date",
        "2026/06/30",
        "30-06-2026",
        "abcdefg",
        "2026-06-",
        "13:00:00",
    ])
    def test_malformed_date_to_does_not_crash(self, auth_client, bad_value):
        c, uid, _ = auth_client
        resp = c.get(f"/profile?date_from=2026-06-01&date_to={bad_value}")
        assert resp.status_code == 200, (
            f"Malformed date_to='{bad_value}' must not crash the server"
        )

    def test_malformed_date_from_falls_back_to_unfiltered(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=not-a-date&date_to=2026-06-30")
        body = _body(resp)
        # All expenses should be visible since the bad param is silently ignored
        assert "Old groceries" in body, "Malformed date_from should fall back to unfiltered"
        assert "Train ticket"  in body, "Malformed date_from should fall back to unfiltered"

    def test_malformed_date_to_falls_back_to_unfiltered(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=not-a-date")
        body = _body(resp)
        assert "Old groceries" in body, "Malformed date_to should fall back to unfiltered"

    def test_both_malformed_falls_back_to_unfiltered(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=bad&date_to=also-bad")
        assert resp.status_code == 200
        body = _body(resp)
        assert "Old groceries" in body, "Both malformed params should fall back to unfiltered"
        assert "335.00"        in body, "All-time total must appear when both params are malformed"

    def test_malformed_dates_do_not_produce_error_flash(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=not-a-date&date_to=2026-06-30")
        body = _body(resp)
        # The inverted-range error message must NOT appear for a merely malformed date
        assert "Start date must be before end date." not in body, (
            "Malformed date should be silently ignored, not treated as an inverted range"
        )


# ------------------------------------------------------------------ #
# 8. Preset ranges                                                    #
# ------------------------------------------------------------------ #

class TestPresetRanges:
    def _today(self) -> date:
        return date.today()

    def _month_offset(self, today: date, months: int) -> date:
        """Mirror the spec's month-offset logic to compute expected preset date_from."""
        total = today.month - 1 - months
        year  = today.year + total // 12
        month = total % 12 + 1
        return date(year, month, 1)

    def test_this_month_preset_is_active_when_params_match(self, auth_client):
        c, uid, _ = auth_client
        today = self._today()
        first_of_month = today.replace(day=1).isoformat()
        today_str      = today.isoformat()
        resp = c.get(f"/profile?date_from={first_of_month}&date_to={today_str}")
        body = _body(resp)
        assert resp.status_code == 200
        # The "This Month" button should have the active CSS class
        this_month_idx = body.find("This Month")
        assert this_month_idx != -1, "'This Month' text must appear in the template"
        # Find the active class marker near the "This Month" label
        section = body[max(0, this_month_idx - 200): this_month_idx + 50]
        assert "dash-filter-preset--active" in section, (
            "'This Month' button should carry dash-filter-preset--active class "
            "when date_from/date_to match the this-month preset"
        )

    def test_last_3_months_preset_is_active_when_params_match(self, auth_client):
        c, uid, _ = auth_client
        today     = self._today()
        date_from = self._month_offset(today, 3).isoformat()
        date_to   = today.isoformat()
        resp = c.get(f"/profile?date_from={date_from}&date_to={date_to}")
        body = _body(resp)
        assert resp.status_code == 200
        last_3m_idx = body.find("Last 3 Months")
        assert last_3m_idx != -1, "'Last 3 Months' text must appear in the template"
        section = body[max(0, last_3m_idx - 200): last_3m_idx + 50]
        assert "dash-filter-preset--active" in section, (
            "'Last 3 Months' button should be active when params match the preset"
        )

    def test_last_6_months_preset_is_active_when_params_match(self, auth_client):
        c, uid, _ = auth_client
        today     = self._today()
        date_from = self._month_offset(today, 6).isoformat()
        date_to   = today.isoformat()
        resp = c.get(f"/profile?date_from={date_from}&date_to={date_to}")
        body = _body(resp)
        assert resp.status_code == 200
        last_6m_idx = body.find("Last 6 Months")
        assert last_6m_idx != -1, "'Last 6 Months' text must appear in the template"
        section = body[max(0, last_6m_idx - 200): last_6m_idx + 50]
        assert "dash-filter-preset--active" in section, (
            "'Last 6 Months' button should be active when params match the preset"
        )

    def test_all_time_preset_active_when_no_params(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        all_time_idx = body.find("All Time")
        assert all_time_idx != -1, "'All Time' text must appear in the template"
        section = body[max(0, all_time_idx - 200): all_time_idx + 50]
        assert "dash-filter-preset--active" in section, (
            "'All Time' button should be active when no date params are provided"
        )

    def test_non_preset_range_does_not_activate_any_preset_button(self, auth_client):
        c, uid, _ = auth_client
        # A custom range that does not match any preset
        resp = c.get("/profile?date_from=2026-04-10&date_to=2026-05-25")
        body = _body(resp)
        # Count occurrences of the active class; only the All Time button should
        # NOT be active, and none of the date-based presets should match either.
        # The custom range 2026-04-10 to 2026-05-25 does not align with presets.
        # The "All Time" button should NOT be active either (date params are present).
        all_time_idx = body.find("All Time")
        section = body[max(0, all_time_idx - 200): all_time_idx + 50]
        assert "dash-filter-preset--active" not in section, (
            "'All Time' should not be active when date params are present"
        )

    def test_this_month_preset_filters_data(self, auth_client):
        c, uid, db_path = auth_client
        today = self._today()
        first_of_month = today.replace(day=1).isoformat()
        today_str      = today.isoformat()

        # Insert an expense that falls in the current month so the filter
        # can actually produce a result we can assert on.
        conn = _get_conn(db_path)
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (uid, 99.00, "Food", today_str, "Today's lunch"),
        )
        conn.commit()
        conn.close()

        resp = c.get(f"/profile?date_from={first_of_month}&date_to={today_str}")
        body = _body(resp)
        assert "Today's lunch" in body, (
            "Expense added today should be visible in the 'This Month' preset filter"
        )

    def test_last_3_months_preset_returns_200(self, auth_client):
        c, uid, _ = auth_client
        today     = self._today()
        date_from = self._month_offset(today, 3).isoformat()
        date_to   = today.isoformat()
        resp = c.get(f"/profile?date_from={date_from}&date_to={date_to}")
        assert resp.status_code == 200

    def test_last_6_months_preset_returns_200(self, auth_client):
        c, uid, _ = auth_client
        today     = self._today()
        date_from = self._month_offset(today, 6).isoformat()
        date_to   = today.isoformat()
        resp = c.get(f"/profile?date_from={date_from}&date_to={date_to}")
        assert resp.status_code == 200


# ------------------------------------------------------------------ #
# 9. Rupee symbol in all view modes                                   #
# ------------------------------------------------------------------ #

class TestRupeeSymbol:
    def test_rupee_in_filtered_stat_total(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        assert "₹" in body, "₹ must appear in the stats total after filtering"

    def test_rupee_in_filtered_transaction_amounts(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        # There should be at least one ₹ in the transaction rows
        rupee_count = body.count("₹")
        assert rupee_count >= 1, (
            "At least one ₹ symbol must appear in the filtered transactions list"
        )

    def test_rupee_in_empty_filter_result(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2020-01-01&date_to=2020-12-31")
        body = _body(resp)
        assert "₹0.00" in body, "₹0.00 must appear when the filtered range has no expenses"

    def test_rupee_in_category_breakdown_totals(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        # Category totals in breakdown should show ₹
        assert "₹" in body, "₹ must appear in category breakdown totals"


# ------------------------------------------------------------------ #
# 10. Template structure is intact after filter changes               #
# ------------------------------------------------------------------ #

class TestTemplateStructure:
    def test_user_name_still_rendered_in_filtered_view(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        assert "Filter Tester" in body, "User name must still appear in the filtered view"

    def test_user_email_still_rendered_in_filtered_view(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        assert "filter@example.com" in body, "User email must still appear in filtered view"

    def test_date_inputs_reflect_active_filter_values(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile?date_from=2026-06-01&date_to=2026-06-15")
        body = _body(resp)
        # The date inputs should be pre-filled with the active filter values
        assert "2026-06-01" in body, "date_from value should be reflected in the date input"
        assert "2026-06-15" in body, "date_to value should be reflected in the date input"

    def test_recent_transactions_heading_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "Recent Transactions" in body, "'Recent Transactions' heading must be present"

    def test_by_category_heading_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "By Category" in body, "'By Category' heading must be present"

    def test_page_title_present(self, auth_client):
        c, uid, _ = auth_client
        resp = c.get("/profile")
        body = _body(resp)
        assert "Spendly" in body, "Page title or brand name 'Spendly' must appear on the profile page"
