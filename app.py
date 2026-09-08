from flask import Flask, Response, g, render_template, request, redirect, url_for, session, jsonify
import csv
import io
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
from pathlib import Path
from datetime import datetime
import os
import re

# --- Configuration ---
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "budget.db"
SECRET_KEY = "change-this-secret-key"

app = Flask(__name__)
app.config.update(SECRET_KEY=SECRET_KEY)


def get_db():
    """Open a sqlite3 connection and initialize schema if needed."""
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(str(DB_PATH))
        db.row_factory = sqlite3.Row
        init_db(db)
    return db


def init_db(db):
    """Create tables for users, profiles, and expenses."""
    cur = db.cursor()
    cur.executescript(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        date TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """
    )

    user_columns = {row[1] for row in cur.execute("PRAGMA table_info(users)")}
    if "password_hash" not in user_columns:
        cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

    profile_columns = {row[1] for row in cur.execute("PRAGMA table_info(profiles)")}
    if profile_columns and "emirate" not in profile_columns:
        cur.execute("ALTER TABLE profiles RENAME TO profiles_legacy")
        profile_columns = set()

    if not profile_columns:
        cur.execute(
            """
            CREATE TABLE profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                emirate TEXT NOT NULL,
                income REAL NOT NULL,
                user_type TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        if cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='profiles_legacy'").fetchone():
            cur.execute(
                """
                INSERT INTO profiles (id, user_id, emirate, income, user_type)
                SELECT id, user_id, 'Dubai', income, user_type FROM profiles_legacy
                """
            )
            cur.execute("DROP TABLE profiles_legacy")

    db.commit()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


EMIRATES = [
    "Dubai",
    "Abu Dhabi",
    "Sharjah",
    "Ajman",
    "Umm Al Quwain",
    "Ras Al Khaimah",
    "Fujairah",
]

# Students and professionals share the same practical living-cost categories.
EXPENSE_CATEGORIES = {
    "student": ["Rent", "Transport", "Groceries", "Electricity", "Water", "Internet/Wi-Fi", "Mobile Recharge/Phone", "Entertainment", "Other"],
    "professional": ["Rent", "Transport", "Groceries", "Electricity", "Water", "Internet/Wi-Fi", "Mobile Recharge/Phone", "Personal Care", "Entertainment", "Other"],
}

# Rough monthly AED estimates for one person, not precise quotes. Keep this table editable.
MONTHLY_BUDGETS_BY_EMIRATE = {
    "Dubai": {
        "student": {"Rent": 2200, "Transport": 350, "Groceries": 450, "Electricity": 250, "Water": 50, "Internet/Wi-Fi": 300, "Mobile Recharge/Phone": 69, "Entertainment": 250, "Other": 250},
        "professional": {"Rent": 3200, "Transport": 500, "Groceries": 650, "Electricity": 350, "Water": 75, "Internet/Wi-Fi": 350, "Mobile Recharge/Phone": 150, "Personal Care": 400, "Entertainment": 400, "Other": 350},
    },
    "Abu Dhabi": {
        "student": {"Rent": 2000, "Transport": 300, "Groceries": 450, "Electricity": 220, "Water": 55, "Internet/Wi-Fi": 300, "Mobile Recharge/Phone": 69, "Entertainment": 200, "Other": 250},
        "professional": {"Rent": 2800, "Transport": 450, "Groceries": 650, "Electricity": 320, "Water": 80, "Internet/Wi-Fi": 350, "Mobile Recharge/Phone": 150, "Personal Care": 400, "Entertainment": 350, "Other": 350},
    },
    "Sharjah": {
        "student": {"Rent": 1500, "Transport": 350, "Groceries": 400, "Electricity": 220, "Water": 45, "Internet/Wi-Fi": 300, "Mobile Recharge/Phone": 69, "Entertainment": 200, "Other": 250},
        "professional": {"Rent": 2200, "Transport": 450, "Groceries": 600, "Electricity": 320, "Water": 70, "Internet/Wi-Fi": 350, "Mobile Recharge/Phone": 150, "Personal Care": 400, "Entertainment": 350, "Other": 350},
    },
    "Ajman": {
        "student": {"Rent": 1200, "Transport": 350, "Groceries": 350, "Electricity": 200, "Water": 43, "Internet/Wi-Fi": 300, "Mobile Recharge/Phone": 69, "Entertainment": 200, "Other": 250},
        "professional": {"Rent": 1800, "Transport": 450, "Groceries": 550, "Electricity": 300, "Water": 65, "Internet/Wi-Fi": 350, "Mobile Recharge/Phone": 150, "Personal Care": 400, "Entertainment": 300, "Other": 350},
    },
    "Umm Al Quwain": {
        "student": {"Rent": 1000, "Transport": 300, "Groceries": 330, "Electricity": 180, "Water": 40, "Internet/Wi-Fi": 300, "Mobile Recharge/Phone": 69, "Entertainment": 180, "Other": 250},
        "professional": {"Rent": 1500, "Transport": 400, "Groceries": 500, "Electricity": 280, "Water": 60, "Internet/Wi-Fi": 350, "Mobile Recharge/Phone": 150, "Personal Care": 400, "Entertainment": 280, "Other": 350},
    },
    "Ras Al Khaimah": {
        "student": {"Rent": 1100, "Transport": 300, "Groceries": 350, "Electricity": 200, "Water": 47, "Internet/Wi-Fi": 300, "Mobile Recharge/Phone": 69, "Entertainment": 180, "Other": 250},
        "professional": {"Rent": 1600, "Transport": 400, "Groceries": 500, "Electricity": 300, "Water": 67, "Internet/Wi-Fi": 350, "Mobile Recharge/Phone": 150, "Personal Care": 400, "Entertainment": 300, "Other": 350},
    },
    "Fujairah": {
        "student": {"Rent": 1000, "Transport": 300, "Groceries": 330, "Electricity": 180, "Water": 42, "Internet/Wi-Fi": 300, "Mobile Recharge/Phone": 69, "Entertainment": 180, "Other": 250},
        "professional": {"Rent": 1500, "Transport": 400, "Groceries": 500, "Electricity": 280, "Water": 62, "Internet/Wi-Fi": 350, "Mobile Recharge/Phone": 150, "Personal Care": 400, "Entertainment": 280, "Other": 350},
    },
}

# Income-based personalization weights. These are internal calculations; the UI shows AED amounts only.
PERSONALIZED_RATIOS_BY_EMIRATE = {
    "Dubai": {
        "student": {"Rent": .45, "Transport": .08, "Groceries": .12, "Electricity": .06, "Water": .015, "Internet/Wi-Fi": .08, "Mobile Recharge/Phone": .02, "Entertainment": .05, "Other": .125},
        "professional": {"Rent": .48, "Transport": .08, "Groceries": .14, "Electricity": .07, "Water": .02, "Internet/Wi-Fi": .06, "Mobile Recharge/Phone": .03, "Personal Care": .05, "Entertainment": .04, "Other": .03},
    },
    "Abu Dhabi": {
        "student": {"Rent": .43, "Transport": .08, "Groceries": .12, "Electricity": .06, "Water": .015, "Internet/Wi-Fi": .08, "Mobile Recharge/Phone": .02, "Entertainment": .05, "Other": .145},
        "professional": {"Rent": .46, "Transport": .08, "Groceries": .14, "Electricity": .07, "Water": .02, "Internet/Wi-Fi": .06, "Mobile Recharge/Phone": .03, "Personal Care": .05, "Entertainment": .04, "Other": .05},
    },
    "Sharjah": {
        "student": {"Rent": .36, "Transport": .09, "Groceries": .13, "Electricity": .06, "Water": .015, "Internet/Wi-Fi": .08, "Mobile Recharge/Phone": .02, "Entertainment": .05, "Other": .195},
        "professional": {"Rent": .40, "Transport": .09, "Groceries": .14, "Electricity": .07, "Water": .02, "Internet/Wi-Fi": .06, "Mobile Recharge/Phone": .03, "Personal Care": .05, "Entertainment": .04, "Other": .10},
    },
    "Ajman": {
        "student": {"Rent": .32, "Transport": .09, "Groceries": .13, "Electricity": .06, "Water": .015, "Internet/Wi-Fi": .08, "Mobile Recharge/Phone": .02, "Entertainment": .05, "Other": .235},
        "professional": {"Rent": .35, "Transport": .09, "Groceries": .14, "Electricity": .07, "Water": .02, "Internet/Wi-Fi": .06, "Mobile Recharge/Phone": .03, "Personal Care": .05, "Entertainment": .04, "Other": .15},
    },
    "Umm Al Quwain": {
        "student": {"Rent": .30, "Transport": .09, "Groceries": .13, "Electricity": .06, "Water": .015, "Internet/Wi-Fi": .08, "Mobile Recharge/Phone": .02, "Entertainment": .05, "Other": .255},
        "professional": {"Rent": .33, "Transport": .09, "Groceries": .14, "Electricity": .07, "Water": .02, "Internet/Wi-Fi": .06, "Mobile Recharge/Phone": .03, "Personal Care": .05, "Entertainment": .04, "Other": .17},
    },
    "Ras Al Khaimah": {
        "student": {"Rent": .31, "Transport": .09, "Groceries": .13, "Electricity": .06, "Water": .015, "Internet/Wi-Fi": .08, "Mobile Recharge/Phone": .02, "Entertainment": .05, "Other": .245},
        "professional": {"Rent": .34, "Transport": .09, "Groceries": .14, "Electricity": .07, "Water": .02, "Internet/Wi-Fi": .06, "Mobile Recharge/Phone": .03, "Personal Care": .05, "Entertainment": .04, "Other": .16},
    },
    "Fujairah": {
        "student": {"Rent": .30, "Transport": .09, "Groceries": .13, "Electricity": .06, "Water": .015, "Internet/Wi-Fi": .08, "Mobile Recharge/Phone": .02, "Entertainment": .05, "Other": .255},
        "professional": {"Rent": .33, "Transport": .09, "Groceries": .14, "Electricity": .07, "Water": .02, "Internet/Wi-Fi": .06, "Mobile Recharge/Phone": .03, "Personal Care": .05, "Entertainment": .04, "Other": .17},
    },
}

ALL_CATEGORIES = list(dict.fromkeys(category for categories in EXPENSE_CATEGORIES.values() for category in categories))


def valid_email(email: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None

@app.context_processor
def inject_now():
    return {"current_year": datetime.utcnow().year}


@app.route("/")
def landing():
    """Public frontend shown before authentication."""
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def capture_email():
    """Sign up or log in with an email and password."""
    if request.method == "POST":
        # A failed login must never leave an older authenticated session active.
        session.pop("user_id", None)
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        mode = request.form.get("mode", "login")
        if not valid_email(email):
            return render_template("email.html", error="Please enter a valid email", email=email, mode=mode)
        if len(password) < 8:
            return render_template(
                "email.html",
                error="Password must be at least 8 characters",
                email=email,
                mode=mode,
            )

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE email = ?", (email,))
        user = cur.fetchone()

        if mode == "signup":
            if user and user["password_hash"]:
                return render_template("email.html", error="That email is already registered. Log in instead.", email=email, mode=mode)
            now = datetime.utcnow().isoformat()
            if user:
                cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), user["id"]))
                user_id = user["id"]
            else:
                cur.execute(
                    "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    (email, generate_password_hash(password), now),
                )
                user_id = cur.lastrowid
            db.commit()
        else:
            if not user or not user["password_hash"]:
                return render_template("email.html", error="No account found. Sign up first.", email=email, mode=mode)
            if not check_password_hash(user["password_hash"], password):
                return render_template("email.html", error="Incorrect email or password", email=email, mode=mode)
            user_id = user["id"]

        session["user_id"] = user_id
        return redirect(url_for("setup"))

    return render_template("email.html", mode=request.args.get("mode", "login"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """Emirate, monthly income, and user type selection."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("capture_email"))

    if request.method == "POST":
        emirate = request.form.get("emirate")
        income = float(request.form.get("income", 0) or 0)
        user_type = request.form.get("user_type")
        if emirate not in EMIRATES:
            emirate = "Dubai"

        db = get_db()
        cur = db.cursor()
        # upsert profile
        cur.execute("SELECT id FROM profiles WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            cur.execute(
                "UPDATE profiles SET emirate=?, income=?, user_type=? WHERE user_id=?",
                (emirate, income, user_type, user_id),
            )
        else:
            cur.execute(
                "INSERT INTO profiles (user_id, emirate, income, user_type) VALUES (?,?,?,?)",
                (user_id, emirate, income, user_type),
            )
        db.commit()
        return redirect(url_for("dashboard"))

    return render_template(
        "setup.html",
        emirates=EMIRATES,
        budgets_by_emirate=MONTHLY_BUDGETS_BY_EMIRATE,
        personalized_ratios_by_emirate=PERSONALIZED_RATIOS_BY_EMIRATE,
    )


@app.route("/logout")
def logout():
    """End the current session and return to the public frontend."""
    session.clear()
    return redirect(url_for("landing"))


@app.route("/dashboard")
def dashboard():
    """Main dashboard showing month-specific spending and comparisons."""
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("capture_email"))

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
    profile = cur.fetchone()
    if not profile:
        return redirect(url_for("setup"))

    # fetch expenses
    cur.execute("SELECT id, category, amount, date, note FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC", (user_id,))
    all_expenses = cur.fetchall()
    available_months = sorted({expense["date"][:7] for expense in all_expenses}, reverse=True)
    current_month = datetime.utcnow().strftime("%Y-%m")
    selected_month = request.args.get("month") or (available_months[0] if available_months else current_month)
    if selected_month not in available_months and selected_month != current_month:
        selected_month = current_month
    expenses = [expense for expense in all_expenses if expense["date"].startswith(selected_month)]

    def month_label(month):
        return datetime.strptime(month, "%Y-%m").strftime("%B %Y")

    # totals per category
    totals = {c: 0.0 for c in ALL_CATEGORIES}
    monthly_totals = {}
    for e in all_expenses:
        cat = e["category"]
        amt = float(e["amount"])
        date = e["date"]
        month = date[:7]
        monthly_totals[month] = monthly_totals.get(month, 0.0) + amt
        if month == selected_month:
            totals[cat] = totals.get(cat, 0.0) + amt

    # Step 1 uses fixed standard costs; Step 2 scales internal weights to income.
    emirate_budgets = MONTHLY_BUDGETS_BY_EMIRATE.get(profile["emirate"], MONTHLY_BUDGETS_BY_EMIRATE["Dubai"])
    standard_budget = emirate_budgets.get(profile["user_type"], emirate_budgets["professional"])
    categories = EXPENSE_CATEGORIES.get(profile["user_type"], EXPENSE_CATEGORIES["professional"])
    emirate_ratios = PERSONALIZED_RATIOS_BY_EMIRATE.get(profile["emirate"], PERSONALIZED_RATIOS_BY_EMIRATE["Dubai"])
    ratios = emirate_ratios.get(profile["user_type"], emirate_ratios["professional"])
    suggested = {category: round(profile["income"] * ratios.get(category, 0), 2) for category in categories}
    month_total = round(sum(totals.get(category, 0) for category in categories), 2)
    suggested_total = round(sum(suggested.values()), 2)
    month_difference = round(suggested_total - month_total, 2)

    # prepare comparison flags
    comparison = []
    for k in categories:
        actual = round(totals.get(k, 0.0), 2)
        suggested_amt = suggested.get(k, 0.0)
        over = actual > suggested_amt if suggested_amt > 0 else False
        comparison.append({"category": k, "actual": actual, "suggested": suggested_amt, "over": over})

    # prepare data for charts
    pie_data = {k: totals[k] for k in totals if totals[k] > 0}
    line_months = sorted(monthly_totals.keys())
    line_labels = [month_label(month) for month in line_months]
    line_values = [monthly_totals[month] for month in line_months]

    return render_template(
        "dashboard.html",
        profile=profile,
        pie_data=pie_data,
        line_labels=line_labels,
        line_values=line_values,
        comparison=comparison,
        expenses=expenses,
        edit_expense=next(
            (expense for expense in expenses if str(expense["id"]) == request.args.get("edit_expense")),
            None,
        ),
        currency="AED",
        emirate=profile["emirate"],
        categories=categories,
        available_months=available_months,
        selected_month=selected_month,
        selected_month_label=month_label(selected_month),
        month_labels={month: month_label(month) for month in available_months},
        month_total=month_total,
        suggested_total=suggested_total,
        month_difference=month_difference,
    )


@app.route("/add_expense", methods=["POST"])
def add_expense():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("capture_email"))

    category = request.form.get("category")
    amount = float(request.form.get("amount", 0) or 0)
    date = request.form.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
    note = request.form.get("note")

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO expenses (user_id, category, amount, date, note) VALUES (?,?,?,?,?)",
        (user_id, category, amount, date, note),
    )
    db.commit()
    return redirect(url_for("dashboard", month=date[:7]))


@app.route("/edit_expense/<int:expense_id>", methods=["POST"])
def edit_expense(expense_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("capture_email"))

    category = request.form.get("category")
    amount = float(request.form.get("amount", 0) or 0)
    date = request.form.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
    note = request.form.get("note")

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        UPDATE expenses
        SET category=?, amount=?, date=?, note=?
        WHERE id=? AND user_id=?
        """,
        (category, amount, date, note, expense_id, user_id),
    )
    db.commit()
    return redirect(url_for("dashboard", month=request.form.get("return_month") or date[:7]))


@app.route("/delete_expense/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("capture_email"))

    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (expense_id, user_id))
    db.commit()
    return redirect(url_for("dashboard", month=request.form.get("return_month") or datetime.utcnow().strftime("%Y-%m")))


@app.route("/export_expenses.csv")
def export_expenses():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("capture_email"))

    current_month = datetime.utcnow().strftime("%Y-%m")
    selected_month = request.args.get("month") or current_month
    if not re.match(r"^\d{4}-\d{2}$", selected_month):
        selected_month = current_month

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT date, category, amount, note FROM expenses WHERE user_id=? AND date LIKE ? ORDER BY date ASC, id ASC",
        (user_id, f"{selected_month}%"),
    )

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["date", "category", "amount", "note"])
    for row in cur.fetchall():
        # Leading apostrophe keeps spreadsheet apps from interpreting the date as a narrow date cell.
        writer.writerow([f"'{row['date']}", row["category"], row["amount"], row["note"]])
    filename = f"budgetly-expenses-{selected_month}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/summary")
def api_summary():
    """Return simple JSON summary for dynamic front-end use (optional)."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({})
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT category, SUM(amount) as total FROM expenses WHERE user_id=? GROUP BY category", (user_id,))
    rows = cur.fetchall()
    return jsonify({r["category"]: r["total"] for r in rows})


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))