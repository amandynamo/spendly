from flask import Flask, render_template, request, redirect, url_for, session, g
from functools import wraps
from datetime import datetime, date, timedelta
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
    return redirect(url_for('profile'))


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

    # Parse and validate date filter query params
    raw_start = request.args.get('start', '')
    raw_end   = request.args.get('end', '')
    filter_start = filter_end = None
    try:
        if raw_start and raw_end:
            parsed_start = datetime.strptime(raw_start, '%Y-%m-%d')
            parsed_end   = datetime.strptime(raw_end,   '%Y-%m-%d')
            if parsed_start <= parsed_end:
                filter_start, filter_end = raw_start, raw_end
    except ValueError:
        pass

    # Compute preset date ranges
    today            = date.today()
    month_start      = today.replace(day=1)
    last_month_end   = month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    presets = [
        {'label': 'This Month',    'start': month_start.isoformat(),                    'end': today.isoformat()},
        {'label': 'Last Month',    'start': last_month_start.isoformat(),               'end': last_month_end.isoformat()},
        {'label': 'Last 3 Months', 'start': (today - timedelta(days=90)).isoformat(),   'end': today.isoformat()},
        {'label': 'Last 6 Months', 'start': (today - timedelta(days=180)).isoformat(),  'end': today.isoformat()},
        {'label': 'All Time',      'start': None,                                        'end': None},
    ]

    active_period = 'All Time' if not filter_start else None
    for p in presets:
        if p['start'] == filter_start and p['end'] == filter_end:
            active_period = p['label']
            break

    expense_limit = 50 if filter_start else 5
    stats        = get_profile_stats(user_id, filter_start, filter_end)
    transactions = get_recent_expenses(user_id, limit=expense_limit,
                                       start_date=filter_start, end_date=filter_end)
    for t in transactions:
        try:
            t['date_display'] = datetime.strptime(t['date'], '%Y-%m-%d').strftime('%d %b %Y')
        except ValueError:
            t['date_display'] = t['date']
    categories = get_category_breakdown(user_id, filter_start, filter_end)

    return render_template('profile.html',
                           user=user, stats=stats,
                           transactions=transactions, categories=categories,
                           presets=presets,
                           filter_start=filter_start, filter_end=filter_end,
                           active_period=active_period)


@app.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


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
