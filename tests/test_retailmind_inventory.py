"""Unit tests for RetailMind AI predictive stock recommendations."""
from __future__ import annotations

import pandas as pd
import pytest

from retailmind.inventory import (
    build_inventory_recommendations,
    detect_inventory_columns,
)
from retailmind.schema import infer_schema


@pytest.fixture
def sales_with_stock_df() -> pd.DataFrame:
    # 30 days of sales for 3 products
    dates = pd.date_range("2025-01-01", periods=30, freq="D")
    records = []
    for d in dates:
        # Product A: 10 units/day, stock = 20 (critical, only 2 days left)
        records.append({"product_name": "Product A", "order_date": d, "quantity": 10, "current_stock": 20, "lead_time": 5})
        # Product B: 2 units/day, stock = 100 (healthy)
        records.append({"product_name": "Product B", "order_date": d, "quantity": 2, "current_stock": 100, "lead_time": 7})
        # Product C: 5 units/day, stock = 0 (out of stock)
        records.append({"product_name": "Product C", "order_date": d, "quantity": 5, "current_stock": 0, "lead_time": 3})
    return pd.DataFrame(records)


def test_detect_inventory_columns(sales_with_stock_df: pd.DataFrame):
    schema = infer_schema(sales_with_stock_df)
    cols = detect_inventory_columns(sales_with_stock_df, schema)
    assert cols["product"] == "product_name"
    assert cols["date"] == "order_date"
    assert cols["quantity"] == "quantity"
    assert cols["stock"] == "current_stock"
    assert cols["lead_time"] == "lead_time"


def test_inventory_missing_required_columns():
    df = pd.DataFrame({"product": ["A", "B"], "price": [10, 20]})
    schema = infer_schema(df)
    res = build_inventory_recommendations(df, schema)
    assert not res.available
    assert any("Missing" in note for note in res.notes)


def test_inventory_without_stock_column():
    # Only product, date and quantity; no stock column
    dates = pd.date_range("2025-01-01", periods=20, freq="D")
    df = pd.DataFrame({
        "product": ["Widget"] * 20,
        "date": dates,
        "quantity": [5] * 20,
    })
    schema = infer_schema(df)
    res = build_inventory_recommendations(df, schema)
    assert res.available
    assert not res.stock_available
    assert not res.table.empty
    row = res.table.iloc[0]
    assert row["product"] == "Widget"
    assert row["avg_daily_sales"] == 5.0
    assert row["reorder_point"] > 0
    assert row["current_stock"] is None
    assert row["days_remaining"] is None
    assert row["status"] == "Stock data required"
    assert any("No current-stock column was found" in note for note in res.notes)


def test_inventory_with_stock_status_classification(sales_with_stock_df: pd.DataFrame):
    schema = infer_schema(sales_with_stock_df)
    res = build_inventory_recommendations(sales_with_stock_df, schema)
    assert res.available
    assert res.stock_available
    assert len(res.table) == 3
    
    # Check status classifications
    c_row = res.table[res.table["product"] == "Product C"].iloc[0]
    assert c_row["status"] == "Out of stock"
    
    a_row = res.table[res.table["product"] == "Product A"].iloc[0]
    assert a_row["status"] in ("Critical — reorder now", "Low — reorder soon")
    assert a_row["days_remaining"] is not None
    assert a_row["estimated_depletion_date"] is not None
    assert a_row["suggested_reorder_quantity"] is not None
    assert a_row["suggested_reorder_quantity"] > 0
    
    b_row = res.table[res.table["product"] == "Product B"].iloc[0]
    assert b_row["status"] == "Healthy"


def test_inventory_methods_and_exports(sales_with_stock_df: pd.DataFrame):
    schema = infer_schema(sales_with_stock_df)
    res_ma = build_inventory_recommendations(sales_with_stock_df, schema, method="Moving average")
    assert res_ma.available
    
    # Check CSV export
    csv_bytes = res_ma.to_csv_bytes()
    assert isinstance(csv_bytes, bytes)
    assert b"Product A" in csv_bytes
    
    # Check Excel export
    excel_bytes = res_ma.to_excel_bytes()
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0


def test_inventory_flags_overstock_from_excess_days_of_cover():
    frame = pd.DataFrame({
        "product_name": ["Slow Mover"] * 30,
        "order_date": pd.date_range("2025-01-01", periods=30, freq="D"),
        "quantity": [1] * 30,
        "current_stock": [500] * 30,
    })
    schema = infer_schema(frame)
    res = build_inventory_recommendations(frame, schema)
    assert res.available
    assert res.stock_available
    row = res.table.iloc[0]
    assert row["status"] == "Overstock — review cover"
    assert row["suggested_reorder_quantity"] == 0
    assert any("Overstock is flagged" in assumption for assumption in res.assumptions)
