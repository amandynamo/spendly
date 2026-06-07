from flask import Flask, render_template, request, redirect, url_for, session, g
from functools import wraps
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from database.db import get_db, init_db, seed_db, create_user, get_user_by_email, get_user_by_id, get_profile_stats, get_recent_expenses, get_category_breakdown

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
    user_id = g.user['id']
    member_since = datetime.strptime(g.user['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%B %Y')
    user = {
        'name': g.user['name'],
        'email': g.user['email'],
        'member_since': member_since,
    }
    stats = get_profile_stats(user_id)
    transactions = get_recent_expenses(user_id)
    categories = get_category_breakdown(user_id)
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
