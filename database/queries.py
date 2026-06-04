from database.db import get_db
from datetime import datetime


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return None
    dt = datetime.strptime(row["created_at"][:10], "%Y-%m-%d")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": dt.strftime("%B %Y"),
    }


def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT date, description, category, amount FROM expenses"
        " WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        dt = datetime.strptime(row["date"], "%Y-%m-%d")
        result.append({
            "date": f"{dt.strftime('%b')} {dt.day}, {dt.year}",
            "description": row["description"],
            "category": row["category"],
            "amount": f"₹{row['amount']:.2f}",
        })
    return result


def get_summary_stats(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt"
        " FROM expenses WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    cnt = row["cnt"]
    conn.close()
    if cnt == 0:
        return {"total_spent": "₹0.00", "transaction_count": 0, "top_category": "—"}
    conn = get_db()
    top = conn.execute(
        "SELECT category FROM expenses WHERE user_id = ?"
        " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    conn.close()
    return {
        "total_spent": f"₹{row['total']:.2f}",
        "transaction_count": cnt,
        "top_category": top["category"],
    }


def get_category_breakdown(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT category, SUM(amount) AS total FROM expenses"
        " WHERE user_id = ? GROUP BY category ORDER BY total DESC",
        (user_id,),
    ).fetchall()
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
