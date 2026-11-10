from pathlib import Path
import os
import mysql.connector

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_env_file():
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        raise FileNotFoundError("Missing .env. Copy .env.example to .env first.")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

def run_report(cursor, title, query):
    print("\n" + "=" * 65)
    print(title)
    print("=" * 65)
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    print(" | ".join(columns))
    for row in rows:
        print(" | ".join(str(value) for value in row))
    if not rows:
        print("No rows found.")

def main():
    load_env_file()
    connection = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "retail_sales_db"),
    )
    cursor = None
    try:
        cursor = connection.cursor()
        run_report(cursor, "OVERALL SALES SUMMARY", """
            WITH order_totals AS (
                SELECT order_id, SUM(sales) AS order_sales
                FROM sales
                GROUP BY order_id
            )
            SELECT (SELECT COUNT(*) FROM order_totals) AS total_orders,
                   ROUND((SELECT SUM(order_sales) FROM order_totals), 2) AS total_sales,
                   ROUND(SUM(profit), 2) AS total_profit,
                   ROUND((SELECT AVG(order_sales) FROM order_totals), 2) AS average_order_sales
            FROM sales
        """)
        run_report(cursor, "SALES BY CATEGORY", """
            SELECT category, ROUND(SUM(sales), 2) AS total_sales,
                   ROUND(SUM(profit), 2) AS total_profit
            FROM sales
            GROUP BY category
            ORDER BY total_profit DESC
        """)
        run_report(cursor, "TOP 5 CITIES BY SALES", """
            SELECT city, ROUND(SUM(sales), 2) AS total_sales
            FROM sales
            GROUP BY city
            ORDER BY total_sales DESC
            LIMIT 5
        """)
        run_report(cursor, "TOP 10 PRODUCTS BY SALES", """
            SELECT product_name, SUM(quantity) AS units_sold,
                   ROUND(SUM(sales), 2) AS total_sales
            FROM sales
            GROUP BY product_name
            ORDER BY total_sales DESC
            LIMIT 10
        """)
        run_report(cursor, "MONTHLY SALES TREND", """
            SELECT DATE_FORMAT(order_date, '%Y-%m') AS sales_month,
                   ROUND(SUM(sales), 2) AS total_sales,
                   ROUND(SUM(profit), 2) AS total_profit
            FROM sales
            GROUP BY DATE_FORMAT(order_date, '%Y-%m')
            ORDER BY sales_month
        """)
        run_report(cursor, "NEGATIVE PROFIT ORDERS", """
            SELECT order_id, product_name, city, sales, profit
            FROM sales
            WHERE profit < 0
            ORDER BY profit ASC
            LIMIT 20
        """)
    finally:
        if cursor:
            cursor.close()
        connection.close()

if __name__ == "__main__":
    main()
