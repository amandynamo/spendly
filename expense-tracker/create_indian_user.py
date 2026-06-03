import sqlite3
from werkzeug.security import generate_password_hash
import random
from datetime import datetime

# Common Indian first names and last names
FIRST_NAMES = [
    'Rahul', 'Priya', 'Amit', 'Neha', 'Vikas', 'Anjali', 'Sameer', 'Pooja',
    'Arjun', 'Kavita', 'Rohit', 'Sneha', 'Karan', 'Deepika', 'Yash', 'Sonali',
    'Abhishek', 'Aishwarya', 'Manish', 'Divya', 'Nikhil', 'Ritu', 'Gaurav',
    'Megha', 'Siddharth', 'Trisha', 'Varun', 'Shreya', 'Aditya', 'Kajal',
    'Aamir', 'Zoya', 'Farhan', 'Diya', 'Imran', 'Sania'
]

LAST_NAMES = [
    'Sharma', 'Patel', 'Singh', 'Kumar', 'Reddy', 'Joshi', 'Shah', 'Jain',
    'Mehta', 'Gupta', 'Agarwal', 'Kaur', 'Khan', 'Das', 'Banerjee', 'Mukherjee',
    'Ghosh', 'Iyer', 'Iyengar', 'Pillai', 'Menon', 'Nair', 'Rao', 'Choudhury',
    'Biswas', 'Paul', 'Saha', 'Kar', 'Pradhan', 'Patro', 'Mishra', 'Tripathi'
]

def get_db():
    """Open a connection to the database with foreign keys enabled and row factory set."""
    conn = sqlite3.connect('expense_tracker.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def email_exists(conn, email):
    """Check if email already exists in users table."""
    cursor = conn.execute('SELECT COUNT(*) FROM users WHERE email = ?', (email,))
    count = cursor.fetchone()[0]
    return count > 0

def generate_indian_user():
    """Generate a realistic random Indian user."""
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    name = f"{first_name} {last_name}"

    # Create email: firstname.lastname + random 2-3 digit number @gmail.com
    # Remove any spaces and make lowercase
    base_email = f"{first_name.lower()}.{last_name.lower()}"
    random_suffix = random.randint(10, 999)  # 2-3 digit number
    email = f"{base_email}{random_suffix}@gmail.com"

    # Password hash
    password_hash = generate_password_hash('password123')

    return name, email, password_hash

def main():
    conn = get_db()
    try:
        # Generate unique user
        attempts = 0
        max_attempts = 100

        while attempts < max_attempts:
            name, email, password_hash = generate_indian_user()

            if not email_exists(conn, email):
                break
            attempts += 1

        if attempts >= max_attempts:
            print("Failed to generate unique email after maximum attempts")
            return

        # Insert user into database
        cursor = conn.execute(
            'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
            (name, email, password_hash)
        )

        user_id = cursor.lastrowid
        conn.commit()

        # Print confirmation
        print(f"User created successfully!")
        print(f"ID: {user_id}")
        print(f"Name: {name}")
        print(f"Email: {email}")

    finally:
        conn.close()

if __name__ == '__main__':
    main()