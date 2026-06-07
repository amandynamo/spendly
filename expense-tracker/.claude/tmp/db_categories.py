def get_category_breakdown(user_id):
    conn = get_db()
    try:
        cursor = conn.execute(
            'SELECT category, SUM(amount) AS total FROM expenses WHERE user_id = ? GROUP BY category ORDER BY total DESC',
            (user_id,)
        )
        rows = cursor.fetchall()
        if not rows:
            return []
        grand_total = sum(row['total'] for row in rows)
        if grand_total == 0:
            return []
        result = [
            {
                'name': row['category'],
                'total': float(row['total']),
                'pct': int(float(row['total']) / grand_total * 100),
            }
            for row in rows
        ]
        pct_sum = sum(item['pct'] for item in result)
        if pct_sum != 100:
            result[0]['pct'] += (100 - pct_sum)
        return result
    finally:
        conn.close()
