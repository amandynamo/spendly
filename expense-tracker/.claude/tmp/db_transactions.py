def get_recent_expenses(user_id, limit=5):
    conn = get_db()
    try:
        cursor = conn.execute(
            'SELECT date, description, category, amount '
            'FROM expenses '
            'WHERE user_id = ? '
            'ORDER BY date DESC, id DESC '
            'LIMIT ?',
            (user_id, limit)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
