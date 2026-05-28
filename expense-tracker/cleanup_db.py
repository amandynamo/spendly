from database.db import get_db

def cleanup_bogus_expense():
    conn = get_db()
    try:
        # Delete the bogus expense with user_id=999 if it exists
        cursor = conn.execute("DELETE FROM expenses WHERE user_id = 999")
        deleted_rows = cursor.rowcount
        conn.commit()
        print(f"Deleted {deleted_rows} bogus expense(s) with user_id=999")

        # Also delete any other test data we might have added
        cursor = conn.execute("DELETE FROM expenses WHERE user_id = 999")
        deleted_rows2 = cursor.rowcount
        if deleted_rows2 > 0:
            conn.commit()
            print(f"Deleted {deleted_rows2} additional bogus expense(s)")

    finally:
        conn.close()

if __name__ == "__main__":
    cleanup_bogus_expense()