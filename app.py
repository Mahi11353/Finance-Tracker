import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, make_response
from werkzeug.security import check_password_hash
from datetime import datetime, date as _date
from database.db import get_db, init_db, seed_db, get_user_by_email, get_user_by_id, create_user
from database.queries import (
    get_user_by_id as get_profile_user,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
    insert_expense,
    get_expense_by_id,
    update_expense,
    delete_expense as delete_expense_query,
    set_balance,
    adjust_balance,
    CATEGORIES,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"  # TODO: use env var in production
app.jinja_env.auto_reload = True

with app.app_context():
    init_db()
    seed_db()


@app.before_request
def set_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)


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


def _parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date() if s else None
    except ValueError:
        return None


def _month_offset(today, months):
    """Return the first day of the month `months` before today's month."""
    total = today.year * 12 + (today.month - 1) - months
    return _date(total // 12, total % 12 + 1, 1)


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user_data = get_profile_user(user_id)

    words = user_data["name"].split()
    initials = (words[0][0] + words[-1][0]).upper() if len(words) > 1 else words[0][0].upper()
    user = {**user_data, "initials": initials}

    date_from = _parse_date(request.args.get("date_from"))
    date_to   = _parse_date(request.args.get("date_to"))

    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.")
        date_from = date_to = None

    date_from = date_from.isoformat() if date_from else None
    date_to   = date_to.isoformat()   if date_to   else None

    today = _date.today()
    presets = {
        "this_month": today.replace(day=1).isoformat(),
        "last_3m":    _month_offset(today, 3).isoformat(),
        "last_6m":    _month_offset(today, 6).isoformat(),
        "today":      today.isoformat(),
    }

    stats              = get_summary_stats(user_id, date_from, date_to)
    expenses           = get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    category_breakdown = get_category_breakdown(user_id, date_from, date_to)

    resp = make_response(render_template("profile.html",
                                         user=user,
                                         stats=stats,
                                         expenses=expenses,
                                         category_breakdown=category_breakdown,
                                         date_from=date_from,
                                         date_to=date_to,
                                         presets=presets))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("add_expense.html",
                               categories=CATEGORIES,
                               today=_date.today().isoformat())

    if request.form.get("csrf_token") != session.get("csrf_token"):
        abort(403)

    user_id = session["user_id"]
    raw_amount = request.form.get("amount", "").strip()
    category = request.form.get("category", "")
    raw_date = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip() or None

    error = None
    amount = None
    if not raw_amount:
        error = "Amount is required."
    else:
        try:
            amount = round(float(raw_amount), 2)
            if amount <= 0:
                error = "Amount must be greater than zero."
            elif amount > 1_000_000:
                error = "Amount must be ₹10,00,000 or less."
        except ValueError:
            error = "Amount must be a number."

    if not error and category not in CATEGORIES:
        error = "Please select a valid category."

    if not error and description and len(description) > 200:
        error = "Description must be 200 characters or fewer."

    parsed_date = None
    if not error:
        try:
            parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            error = "Please enter a valid date."

    if error:
        return render_template("add_expense.html",
                               categories=CATEGORIES,
                               today=_date.today().isoformat(),
                               error=error,
                               form=request.form)

    insert_expense(user_id, amount, category, parsed_date.isoformat(), description)
    adjust_balance(user_id, -amount)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "GET":
        return render_template("edit_expense.html",
                               expense=expense,
                               categories=CATEGORIES)

    if request.form.get("csrf_token") != session.get("csrf_token"):
        abort(403)

    raw_amount  = request.form.get("amount", "").strip()
    category    = request.form.get("category", "")
    raw_date    = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip() or None

    error = None
    amount = None
    if not raw_amount:
        error = "Amount is required."
    else:
        try:
            amount = round(float(raw_amount), 2)
            if amount <= 0:
                error = "Amount must be greater than zero."
            elif amount > 1_000_000:
                error = "Amount must be ₹10,00,000 or less."
        except ValueError:
            error = "Amount must be a number."

    if not error and category not in CATEGORIES:
        error = "Please select a valid category."

    if not error and description and len(description) > 200:
        error = "Description must be 200 characters or fewer."

    parsed_date = None
    if not error:
        try:
            parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            error = "Please enter a valid date."

    if error:
        return render_template("edit_expense.html",
                               expense=expense,
                               categories=CATEGORIES,
                               error=error,
                               form=request.form)

    old_amount = expense["amount"]
    update_expense(id, user_id, amount, category, parsed_date.isoformat(), description)
    adjust_balance(user_id, old_amount - amount)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))
    if request.form.get("csrf_token") != session.get("csrf_token"):
        abort(403)
    user_id = session["user_id"]
    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)
    delete_expense_query(id, user_id)
    adjust_balance(user_id, expense["amount"])
    return redirect(url_for("profile"))


@app.route("/balance/update", methods=["POST"])
def update_balance():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    if request.form.get("csrf_token") != session.get("csrf_token"):
        abort(403)

    user_id = session["user_id"]
    raw = request.form.get("balance", "").strip()
    try:
        amount = round(float(raw), 2)
    except ValueError:
        flash("Balance must be a valid number.")
        return redirect(url_for("profile"))

    set_balance(user_id, amount)
    return redirect(url_for("profile"))


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, port=5001)
