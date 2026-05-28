import sqlite3
from werkzeug.security import generate_password_hash

def get_db():
    """Open a connection to the database with foreign keys enabled and row factory set."""
    conn = sqlite3.connect('expense_tracker.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    """Initialize the database by creating tables if they don't exist."""
    conn = get_db()
    try:
        # Create users table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        ''')

        # Create expenses table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        conn.commit()
    finally:
        conn.close()

def seed_db():
    """Seed the database with initial data if it's empty."""
    conn = get_db()
    try:
        # Check if we already have users
        cursor = conn.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]

        if user_count > 0:
            # Data already seeded, return early
            return

        # Insert demo user
        demo_password_hash = generate_password_hash('demo123')
        cursor = conn.execute('''
            INSERT INTO users (name, email, password_hash)
            VALUES (?, ?, ?)
        ''', ('Demo User', 'demo@spendly.com', demo_password_hash))

        user_id = cursor.lastrowid

        # Insert 8 sample expenses across all categories
        expenses_data = [
            # Food
            (user_id, 12.50, 'Food', '2026-05-01', 'Lunch at cafe'),
            # Transport
            (user_id, 25.00, 'Transport', '2026-05-02', 'Gas refill'),
            # Bills
            (user_id, 85.30, 'Bills', '2026-05-03', 'Electricity bill'),
            # Health
            (user_id, 45.99, 'Health', '2026-05-04', 'Pharmacy purchase'),
            # Entertainment
            (user_id, 30.00, 'Entertainment', '2026-05-05', 'Movie tickets'),
            # Shopping
            (user_id, 67.25, 'Shopping', '2026-05-06', 'New clothes'),
            # Other - first
            (user_id, 15.75, 'Other', '2026-05-07', 'Stationery'),
            # Other - second (to make 8 total)
            (user_id, 22.50, 'Other', '2026-05-08', 'Gift for friend'),
        ]

        conn.executemany('''
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
        ''', expenses_data)

        conn.commit()
    finally:
        conn.close()