from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from database.db import get_db, init_db, seed_db, get_user_by_email, get_user_by_id, create_user

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"  # TODO: use env var in production

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name     = request.form.get("name",     "").strip()
    email    = request.form.get("email",    "").strip()
    password = request.form.get("password", "")

    if not name or not email or not password:
        return render_template("register.html",
                               error="All fields are required.",
                               name=name, email=email)

    if len(password) < 8:
        return render_template("register.html",
                               error="Password must be at least 8 characters.",
                               name=name, email=email)

    if get_user_by_email(email):
        return render_template("register.html",
                               error="Email already in use.",
                               name=name, email=email)

    create_user(name, email, password)
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email    = request.form.get("email",    "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html",
                               error="Invalid email or password.",
                               email=email)

    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name":         "Demo User",
        "email":        "demo@spendly.com",
        "member_since": "Jun 2026",
        "initials":     "DU",
    }

    stats = {
        "total_spent":       "₹319.99",
        "transaction_count": 8,
        "top_category":      "Food",
    }

    expenses = [
        {"date": "Jun 1, 2026",  "description": "Grocery run",            "category": "Food",          "amount": "₹45.50"},
        {"date": "Jun 2, 2026",  "description": "Bus pass top-up",        "category": "Transport",     "amount": "₹12.00"},
        {"date": "Jun 3, 2026",  "description": "Electricity bill",       "category": "Bills",         "amount": "₹120.00"},
        {"date": "Jun 5, 2026",  "description": "Pharmacy",               "category": "Health",        "amount": "₹30.00"},
        {"date": "Jun 7, 2026",  "description": "Streaming subscription", "category": "Entertainment", "amount": "₹18.99"},
        {"date": "Jun 10, 2026", "description": "New shoes",              "category": "Shopping",      "amount": "₹65.00"},
        {"date": "Jun 12, 2026", "description": "Coffee and snacks",      "category": "Food",          "amount": "₹8.50"},
        {"date": "Jun 15, 2026", "description": "Miscellaneous",          "category": "Other",         "amount": "₹20.00"},
    ]

    category_breakdown = [
        {"name": "Bills",         "total": "₹120.00", "pct": 38},
        {"name": "Shopping",      "total": "₹65.00",  "pct": 20},
        {"name": "Food",          "total": "₹54.00",  "pct": 17},
        {"name": "Health",        "total": "₹30.00",  "pct": 9},
        {"name": "Other",         "total": "₹20.00",  "pct": 6},
        {"name": "Entertainment", "total": "₹18.99",  "pct": 6},
        {"name": "Transport",     "total": "₹12.00",  "pct": 4},
    ]

    return render_template("profile.html",
                           user=user,
                           stats=stats,
                           expenses=expenses,
                           category_breakdown=category_breakdown)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
