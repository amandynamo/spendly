#!/usr/bin/env python3
"""
Seed realistic dummy expenses for a specific user
Usage: python seed_expenses.py <user_id> <count> <months>
Example: python seed_expenses.py 1 50 6
"""

import sqlite3
import sys
import random
from datetime import datetime, timedelta

def get_db():
    """Open a connection to the database with foreign keys enabled and row factory set."""
    conn = sqlite3.connect('expense_tracker.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def user_exists(conn, user_id):
    """Check if a user exists in the users table."""
    cursor = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,))
    return cursor.fetchone() is not None

def generate_random_date(start_date, end_date):
    """Generate a random date between start_date and end_date (inclusive)."""
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    random_number_of_days = random.randrange(days_between_dates)
    return start_date + timedelta(days=random_number_of_days)

def generate_expense_data(user_id, months):
    """Generate a single expense record with random data."""

    # Define categories with their amount ranges and weights
    # Food most common, Health and Entertainment least
    categories = [
        ('Food', 50, 800, 0.30),           # 30% weight
        ('Transport', 20, 500, 0.15),      # 15% weight
        ('Bills', 200, 3000, 0.15),        # 15% weight
        ('Health', 100, 2000, 0.10),       # 10% weight
        ('Entertainment', 100, 1500, 0.10), # 10% weight
        ('Shopping', 200, 5000, 0.15),     # 15% weight
        ('Other', 50, 1000, 0.05)          # 5% weight
    ]

    # Select category based on weights
    category = random.choices(
        [cat[0] for cat in categories],
        weights=[cat[3] for cat in categories]
    )[0]

    # Find the selected category's range
    min_amount, max_amount = None, None
    for cat in categories:
        if cat[0] == category:
            min_amount, max_amount = cat[1], cat[2]
            break

    # Generate amount
    amount = round(random.uniform(min_amount, max_amount), 2)

    # Generate date within the past months
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30 * months)  # Approximate months as 30 days
    expense_date = generate_random_date(start_date, end_date)

    # Generate description based on category
    descriptions = {
        'Food': [
            'Lunch at restaurant', 'Dinner with family', 'Groceries from market',
            'Snacks and beverages', 'Breakfast at cafe', 'Food delivery',
            'Vegetables and fruits', 'Milk and dairy products'
        ],
        'Transport': [
            'Gas refill', 'Auto rickshaw fare', 'Bus ticket', 'Metro recharge',
            'Cab ride', 'Parking fee', 'Vehicle maintenance', 'Toll charges'
        ],
        'Bills': [
            'Electricity bill', 'Water bill', 'Internet bill', 'Mobile recharge',
            'Gas cylinder', 'DTH cable', 'Maintenance charges', 'Property tax'
        ],
        'Health': [
            'Pharmacy purchase', 'Doctor consultation', 'Medical test', 'Fitness supplements',
            'Ayurvedic medicine', 'Dental checkup', 'Eye checkup', 'Health checkup package'
        ],
        'Entertainment': [
            'Movie tickets', 'Concert pass', 'Amusement park', 'Streaming subscription',
            'Gaming zone', 'Sports event', 'Theater show', 'Museum entry'
        ],
        'Shopping': [
            'Clothing purchase', 'Footwear', 'Electronics accessory', 'Home decor',
            'Kitchen utensils', 'Personal care products', 'Gift items', 'Books and stationery'
        ],
        'Other': [
            'Stationery items', 'Postage charges', 'Bank fees', 'Registration charges',
            'Certificate fees', 'Donation', 'Membership fee', 'Miscellaneous expenses'
        ]
    }

    description = random.choice(descriptions[category])

    return {
        'user_id': user_id,
        'amount': amount,
        'category': category,
        'date': expense_date.strftime('%Y-%m-%d'),
        'description': description
    }

def main():
    # Parse arguments
    if len(sys.argv) != 4:
        print("Usage: /seed-expenses <user_id> <count> <months>")
        print("Example: /seed-expenses 1 50 6")
        sys.exit(1)

    try:
        user_id = int(sys.argv[1])
        count = int(sys.argv[2])
        months = int(sys.argv[3])
    except ValueError:
        print("Usage: /seed-expenses <user_id> <count> <months>")
        print("Example: /seed-expenses 1 50 6")
        sys.exit(1)

    # Validate arguments
    if user_id <= 0 or count <= 0 or months <= 0:
        print("Error: All arguments must be positive integers")
        sys.exit(1)

    # Connect to database
    conn = get_db()

    try:
        # Verify user exists
        if not user_exists(conn, user_id):
            print(f"No user found with id {user_id}.")
            sys.exit(1)

        print(f"Seeding {count} expenses for user {user_id} across past {months} months...")

        # Generate expenses
        expenses = []
        for _ in range(count):
            expense = generate_expense_data(user_id, months)
            expenses.append(expense)

        # Insert all expenses in a single transaction
        cursor = conn.cursor()
        try:
            cursor.executemany('''
                INSERT INTO expenses (user_id, amount, category, date, description)
                VALUES (:user_id, :amount, :category, :date, :description)
            ''', expenses)

            conn.commit()
            inserted_count = cursor.rowcount

            # Get date range of inserted expenses
            cursor.execute('''
                SELECT MIN(date) as min_date, MAX(date) as max_date
                FROM expenses
                WHERE user_id = ? AND date >= date('now', ?)
            ''', (user_id, f'-{months} months'))
            date_range = cursor.fetchone()

            # Get a sample of 5 inserted records
            cursor.execute('''
                SELECT id, amount, category, date, description
                FROM expenses
                WHERE user_id = ? AND date >= date('now', ?)
                ORDER BY date DESC
                LIMIT 5
            ''', (user_id, f'-{months} months'))
            sample_expenses = cursor.fetchall()

            # Print confirmation
            print(f"\nSuccessfully inserted {inserted_count} expenses.")
            if date_range['min_date'] and date_range['max_date']:
                print(f"Date range: {date_range['min_date']} to {date_range['max_date']}")
            else:
                print("Date range: Unable to determine")

            print("\nSample of 5 inserted records:")
            print("-" * 80)
            for exp in sample_expenses:
                print(f"ID: {exp['id']:3} | Amount: {exp['amount']:6.2f} | {exp['category']:12} | {exp['date']} | {exp['description']}")

        except Exception as e:
            conn.rollback()
            print(f"Error inserting expenses: {e}")
            sys.exit(1)

    finally:
        conn.close()

if __name__ == '__main__':
    main()