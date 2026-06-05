from database.db import get_db
from datetime import datetime

CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def _date_filter(date_from, date_to):
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", [date_from, date_to]
    return "", []


def _format_balance(amount):
    if amount < 0:
        return f"-₹{abs(amount):,.2f}"
    return f"₹{amount:,.2f}"


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return None
    dt = datetime.strptime(row["created_at"][:10], "%Y-%m-%d")
    balance = row["balance"]
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": dt.strftime("%B %Y"),
        "balance": balance,
        "balance_display": _format_balance(balance),
        "balance_negative": balance < 0,
    }


def set_balance(user_id, amount):
    conn = get_db()
    conn.execute("UPDATE users SET balance = ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()


def adjust_balance(user_id, delta):
    conn = get_db()
    conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (delta, user_id))
    conn.commit()
    conn.close()


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    date_clause, extra = _date_filter(date_from, date_to)
    sql = (
        "SELECT id, date, description, category, amount FROM expenses"
        " WHERE user_id = ?"
        + date_clause
        + " ORDER BY date DESC, id DESC LIMIT ?"
    )
    conn = get_db()
    rows = conn.execute(sql, [user_id] + extra + [limit]).fetchall()
    conn.close()
    result = []
    for row in rows:
        dt = datetime.strptime(row["date"], "%Y-%m-%d")
        result.append({
            "id": row["id"],
            "date": f"{dt.strftime('%b')} {dt.day}, {dt.year}",
            "description": row["description"],
            "category": row["category"],
            "amount": f"₹{row['amount']:.2f}",
        })
    return result


def get_summary_stats(user_id, date_from=None, date_to=None):
    date_clause, extra = _date_filter(date_from, date_to)
    sql = (
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt"
        " FROM expenses WHERE user_id = ?"
        + date_clause
    )
    conn = get_db()
    row = conn.execute(sql, [user_id] + extra).fetchone()
    cnt = row["cnt"]
    conn.close()
    if cnt == 0:
        return {"total_spent": "₹0.00", "transaction_count": 0, "top_category": "—"}
    top_sql = (
        "SELECT category FROM expenses WHERE user_id = ?"
        + date_clause
        + " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1"
    )
    conn = get_db()
    top = conn.execute(top_sql, [user_id] + extra).fetchone()
    conn.close()
    return {
        "total_spent": f"₹{row['total']:.2f}",
        "transaction_count": cnt,
        "top_category": top["category"],
    }


def get_category_breakdown(user_id, date_from=None, date_to=None):
    date_clause, extra = _date_filter(date_from, date_to)
    sql = (
        "SELECT category, SUM(amount) AS total FROM expenses"
        " WHERE user_id = ?"
        + date_clause
        + " GROUP BY category ORDER BY total DESC"
    )
    conn = get_db()
    rows = conn.execute(sql, [user_id] + extra).fetchall()
    conn.close()
    if not rows:
        return []
    grand_total = sum(r["total"] for r in rows)
    result = []
    pct_assigned = 0
    for i, row in enumerate(rows):
        if i < len(rows) - 1:
            pct = round(row["total"] / grand_total * 100)
            pct_assigned += pct
        else:
            pct = 100 - pct_assigned
        result.append({
            "name": row["category"],
            "total": f"₹{row['total']:.2f}",
            "pct": pct,
        })
    return result


def get_expense_by_id(expense_id, user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    ).fetchone()
    conn.close()
    return row


def update_expense(expense_id, user_id, amount, category, date, description):
    conn = get_db()
    conn.execute(
        "UPDATE expenses SET amount=?, category=?, date=?, description=?"
        " WHERE id=? AND user_id=?",
        (amount, category, date, description, expense_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id, user_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    )
    conn.commit()
    conn.close()


def insert_expense(user_id, amount, category, date, description):
    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    conn.commit()
    conn.close()
