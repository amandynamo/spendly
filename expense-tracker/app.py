from flask import Flask, render_template, request, redirect, url_for, session, g
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email, get_user_by_id

app = Flask(__name__)
app.secret_key = 'spendly-dev-secret-key'


@app.before_request
def load_user():
    g.user = get_user_by_id(session.get('user_id'))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for('landing'))
    if request.method == "GET":
        return render_template("register.html")

    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip()
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
                               error="An account with that email already exists.",
                               name=name, email=email)

    create_user(name, email, generate_password_hash(password))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for('landing'))
    if request.method == "GET":
        return render_template("login.html")

    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not email or not password:
        return render_template("login.html",
                               error="All fields are required.",
                               email=email)

    user = get_user_by_email(email)
    if not user or not check_password_hash(user['password_hash'], password):
        return render_template("login.html",
                               error="Invalid email or password.",
                               email=email)

    session.clear()
    session['user_id'] = user['id']
    return redirect(url_for('landing'))


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
    return redirect(url_for('landing'))


@app.route("/profile")
@login_required
def profile():
    user = {
        'name': 'Alex Johnson',
        'email': 'alex@example.com',
        'member_since': 'January 2024',
    }
    stats = {
        'total_spent': 1247.50,
        'transaction_count': 23,
        'top_category': 'Food',
    }
    transactions = [
        {'date': '2026-05-08', 'description': 'Gift for friend',   'category': 'Other',         'amount': 22.50},
        {'date': '2026-05-07', 'description': 'Stationery',        'category': 'Other',         'amount': 15.75},
        {'date': '2026-05-06', 'description': 'New clothes',       'category': 'Shopping',      'amount': 67.25},
        {'date': '2026-05-05', 'description': 'Movie tickets',     'category': 'Entertainment', 'amount': 30.00},
        {'date': '2026-05-04', 'description': 'Pharmacy purchase', 'category': 'Health',        'amount': 45.99},
    ]
    categories = [
        {'name': 'Food',          'total': 412.50, 'pct': 33},
        {'name': 'Transport',     'total': 225.00, 'pct': 18},
        {'name': 'Bills',         'total': 285.30, 'pct': 23},
        {'name': 'Health',        'total': 145.99, 'pct': 12},
        {'name': 'Entertainment', 'total':  90.00, 'pct':  7},
        {'name': 'Shopping',      'total':  88.71, 'pct':  7},
    ]
    return render_template('profile.html',
                           user=user, stats=stats,
                           transactions=transactions, categories=categories)


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
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
