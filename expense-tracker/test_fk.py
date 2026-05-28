from database.db import get_db

def test_foreign_keys():
    conn = get_db()
    try:
        # Check if foreign keys are enabled
        cursor = conn.execute("PRAGMA foreign_keys")
        fk_status = cursor.fetchone()[0]
        print(f"Foreign keys status: {fk_status} (1=enabled, 0=disabled)")

        # Try to insert expense with invalid user_id
        try:
            conn.execute("INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
                        (999, 10.0, 'Food', '2026-05-01', 'Test'))
            conn.commit()
            print("ERROR: Insert succeeded - foreign keys NOT enforced")
        except Exception as e:
            print(f"SUCCESS: Insert failed with error: {e}")
            print("Foreign keys ARE enforced")
    finally:
        conn.close()

if __name__ == "__main__":
    test_foreign_keys()