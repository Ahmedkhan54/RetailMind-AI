"""Safely verify the dashboard's MySQL configuration without changing data."""

from pathlib import Path
import sys

import mysql.connector
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
REQUIRED_SETTINGS = (
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
)


def main():
    if not ENV_FILE.exists():
        print("Connection test failed: .env file project root mein nahi mili.")
        return 1

    settings = dotenv_values(ENV_FILE)
    missing = [key for key in REQUIRED_SETTINGS if not settings.get(key)]
    if missing:
        print("Connection test failed: missing setting(s): " + ", ".join(missing))
        print("Apni .env file ko locally update karein. Password output mein kabhi print nahi hoga.")
        return 1

    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(
            host=settings["MYSQL_HOST"],
            port=int(settings["MYSQL_PORT"]),
            user=settings["MYSQL_USER"],
            password=settings["MYSQL_PASSWORD"],
            database=settings["MYSQL_DATABASE"],
            connection_timeout=5,
        )
        cursor = connection.cursor()
        cursor.execute("SELECT DATABASE(), COUNT(*) FROM sales")
        database, row_count = cursor.fetchone()
        print(f"Connection successful: database={database}, sales_rows={row_count}")
        return 0
    except mysql.connector.Error as error:
        if error.errno == 1045:
            print("Connection failed: MySQL rejected the username or password.")
            print("Update MYSQL_PASSWORD locally in .env with the current MySQL password.")
        else:
            print(f"Connection failed: MySQL error {error.errno} ({error.sqlstate}).")
            print("Check MySQL Server, host, port, database name, and table name.")
        return 1
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    sys.exit(main())
