def get_profile_stats(user_id):
    conn = get_db()
    try:
        cursor = conn.execute(
            'SELECT SUM(amount), COUNT(*) FROM expenses WHERE user_id = ?',
            (user_id,)
        )
        row = cursor.fetchone()
        total_spent = row[0] if row[0] is not None else 0.0
        transaction_count = row[1] if row[1] is not None else 0

        cursor = conn.execute(
            'SELECT category FROM expenses WHERE user_id = ? GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1',
            (user_id,)
        )
        top_row = cursor.fetchone()
        top_category = top_row[0] if top_row is not None else '—'

        return {
            'total_spent': float(total_spent),
            'transaction_count': int(transaction_count),
            'top_category': top_category,
        }
    finally:
        conn.close()
