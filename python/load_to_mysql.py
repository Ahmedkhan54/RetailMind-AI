from pathlib import Path
import csv
import os
import mysql.connector
from mysql.connector import Error

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "sales_cleaned.csv"

def load_env_file():
    """Read simple KEY=VALUE lines from the project's .env file."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        raise FileNotFoundError(
            "Missing .env file. Copy .env.example to .env and add your MySQL settings."
        )
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

def main():
    load_env_file()
    if not DATA_FILE.exists():
        raise FileNotFoundError("Cleaned CSV not found. Run: python python/data_cleaning.py")

    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "retail_sales_db"),
        )
        cursor = connection.cursor()

        # Clear existing rows first, so running this script again does not duplicate data.
        cursor.execute("DELETE FROM sales")

        insert_sql = """
            INSERT INTO sales (
                order_id, order_date, customer_id, product_name, category,
                city, region, quantity, unit_price, discount_pct, sales,
                profit, payment_method
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        with DATA_FILE.open("r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            batch = []
            for row in reader:
                batch.append((
                    row["order_id"], row["order_date"], int(row["customer_id"]),
                    row["product_name"], row["category"], row["city"],
                    row["region"], int(row["quantity"]), float(row["unit_price"]),
                    float(row["discount_pct"]), float(row["sales"]),
                    float(row["profit"]), row["payment_method"]
                ))
            if batch:
                cursor.executemany(insert_sql, batch)

        connection.commit()
        cursor.execute("SELECT COUNT(*) FROM sales")
        total_rows = cursor.fetchone()[0]
        print(f"Successfully loaded {total_rows} rows into retail_sales_db.sales.")

    except Error as error:
        if connection and connection.is_connected():
            connection.rollback()
        print("MySQL error:", error)
        print("Check that MySQL Server is running and .env credentials are correct.")
        raise
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

if __name__ == "__main__":
    main()
