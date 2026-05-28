import sys
import sqlite3
sys.path.append('.')
from database.db import get_db
from werkzeug.security import check_password_hash

def check_database():
    conn = get_db()

    print("=== Database Schema ===")
    # Check tables
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"Tables: {[table['name'] for table in tables]}")

    print("\n=== Users Table ===")
    users = conn.execute("SELECT * FROM users").fetchall()
    print(f"Number of users: {len(users)}")
    for user in users:
        print(f"  ID: {user['id']}")
        print(f"  Name: {user['name']}")
        print(f"  Email: {user['email']}")
        print(f"  Password hash starts with: {user['password_hash'][:20]}...")
        print(f"  Created at: {user['created_at']}")

    print("\n=== Expenses Table ===")
    expenses = conn.execute("SELECT * FROM expenses").fetchall()
    print(f"Number of expenses: {len(expenses)}")
    for expense in expenses:
        print(f"  ID: {expense['id']}")
        print(f"  User ID: {expense['user_id']}")
        print(f"  Amount: {expense['amount']}")
        print(f"  Category: {expense['category']}")
        print(f"  Date: {expense['date']}")
        print(f"  Description: {expense['description']}")
        print(f"  Created at: {expense['created_at']}")
        print()

    # Check foreign key constraint
    print("=== Foreign Key Check ===")
    try:
        # Try to insert an expense with invalid user_id
        conn.execute("INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
                    (999, 10.0, 'Food', '2026-05-01', 'Test'))
        conn.commit()
        print("ERROR: Foreign key constraint not enforced!")
    except sqlite3.IntegrityError as e:
        print(f"SUCCESS: Foreign key constraint working - {e}")

    # Check unique constraint
    print("\n=== Unique Constraint Check ===")
    try:
        # Try to insert a duplicate email
        conn.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    ('Duplicate User', 'demo@spendly.com', 'hash'))
        conn.commit()
        print("ERROR: Unique constraint not enforced!")
    except sqlite3.IntegrityError as e:
        print(f"SUCCESS: Unique constraint working - {e}")

    conn.close()

if __name__ == "__main__":
    check_database()