from pathlib import Path
import pandas as pd

# Project root is the folder one level above this Python file.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "sales.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "sales_cleaned.csv"

def main():
    print("Reading raw sales data...")
    df = pd.read_csv(INPUT_FILE)

    print(f"Rows before cleaning: {len(df)}")
    print("\nMissing values in each column:")
    print(df.isnull().sum())

    # Remove duplicate order IDs, keeping the first row.
    df = df.drop_duplicates(subset=["order_id"], keep="first")

    # Convert columns to the correct data types.
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    numeric_columns = [
        "customer_id", "quantity", "unit_price",
        "discount_pct", "sales", "profit"
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    # Remove rows that are missing required values or have invalid values.
    required_columns = [
        "order_id", "order_date", "customer_id", "product_name",
        "category", "city", "region", "quantity", "unit_price",
        "discount_pct", "sales", "profit", "payment_method"
    ]
    df = df.dropna(subset=required_columns)
    df = df[
        (df["quantity"] > 0)
        & (df["unit_price"] >= 0)
        & (df["sales"] >= 0)
        & (df["discount_pct"].between(0, 1))
    ]

    # Save dates in MySQL-friendly YYYY-MM-DD format.
    df["order_date"] = df["order_date"].dt.strftime("%Y-%m-%d")
    df["customer_id"] = df["customer_id"].astype(int)
    df["quantity"] = df["quantity"].astype(int)

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nRows after cleaning: {len(df)}")
    print(f"Cleaned file saved to: {OUTPUT_FILE}")
    print("\nPreview:")
    print(df.head())

if __name__ == "__main__":
    main()
