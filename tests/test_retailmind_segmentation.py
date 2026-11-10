"""Unit tests for RetailMind AI customer segmentation."""
from __future__ import annotations

import io
import numpy as np
import pandas as pd
import pytest

from retailmind.schema import infer_schema
from retailmind.segmentation import (
    detect_customer_columns,
    kmeans_numpy,
    segment_customers,
    silhouette_score_numpy,
)


@pytest.fixture
def multi_customer_df() -> pd.DataFrame:
    # 5 customers with distinct behavior patterns
    data = []
    # Cust 1: Loyal / High frequency / High spend
    for i in range(10):
        data.append({"cust_id": "C1", "order_date": f"2025-03-{i+1:02d}", "sales": 500.0, "order_id": f"O1_{i}"})
    # Cust 2: Big spender / low frequency
    data.append({"cust_id": "C2", "order_date": "2025-03-10", "sales": 5000.0, "order_id": "O2_1"})
    # Cust 3: Churn risk / purchased long ago
    data.append({"cust_id": "C3", "order_date": "2024-01-01", "sales": 50.0, "order_id": "O3_1"})
    # Cust 4: New customer
    data.append({"cust_id": "C4", "order_date": "2025-03-11", "sales": 80.0, "order_id": "O4_1"})
    # Cust 5: Moderate
    for i in range(3):
        data.append({"cust_id": "C5", "order_date": f"2025-02-{i+1:02d}", "sales": 150.0, "order_id": f"O5_{i}"})
        
    return pd.DataFrame(data)


def test_kmeans_numpy_deterministic():
    matrix = np.array([
        [1.0, 1.0], [1.1, 0.9], [0.9, 1.2],
        [10.0, 10.0], [10.2, 9.8], [9.9, 10.1],
    ])
    labels1, centers1, inertia1 = kmeans_numpy(matrix, k=2, seed=42)
    labels2, centers2, inertia2 = kmeans_numpy(matrix, k=2, seed=42)
    
    assert np.array_equal(labels1, labels2)
    assert np.allclose(centers1, centers2)
    assert inertia1 == inertia2
    assert len(np.unique(labels1)) == 2


def test_silhouette_score_numpy():
    matrix = np.array([
        [1.0, 1.0], [1.1, 0.9], [0.9, 1.2],
        [10.0, 10.0], [10.2, 9.8], [9.9, 10.1],
    ])
    labels = np.array([0, 0, 0, 1, 1, 1])
    score = silhouette_score_numpy(matrix, labels)
    assert score is not None
    assert 0.8 < score <= 1.0


def test_detect_customer_columns(multi_customer_df: pd.DataFrame):
    schema = infer_schema(multi_customer_df)
    cols = detect_customer_columns(multi_customer_df, schema)
    assert cols["customer"] == "cust_id"
    assert cols["date"] == "order_date"
    assert cols["revenue"] == "sales"
    assert cols["order"] == "order_id"


def test_segment_customers_missing_columns():
    df = pd.DataFrame({"product": ["A", "B"], "price": [10, 20]})
    schema = infer_schema(df)
    res = segment_customers(df, schema)
    assert not res.available
    assert any("Missing" in note for note in res.notes)


def test_segment_customers_derived_revenue():
    # Dataset has quantity and unit_price but not revenue
    df = pd.DataFrame({
        "customer": ["Alice", "Bob", "Alice"],
        "order_date": ["2025-01-01", "2025-01-02", "2025-02-01"],
        "quantity": [2, 3, 4],
        "unit_price": [10.0, 20.0, 10.0],
    })
    schema = infer_schema(df)
    res = segment_customers(df, schema)
    assert res.available
    assert not res.rfm.empty
    assert "monetary_value" in res.rfm.columns
    # Alice: 2*10 + 4*10 = 60; Bob: 3*20 = 60
    assert len(res.rfm) == 2


def test_segment_customers_full_run(multi_customer_df: pd.DataFrame):
    schema = infer_schema(multi_customer_df)
    res = segment_customers(multi_customer_df, schema, max_clusters=3)
    assert res.available
    assert not res.rfm.empty
    assert not res.summary.empty
    assert res.k >= 2
    assert "segment" in res.rfm.columns
    assert "recency_days" in res.rfm.columns
    assert "churn_risk_rule" in res.rfm.columns
    
    # Check export bytes
    csv_bytes = res.to_csv_bytes()
    assert isinstance(csv_bytes, bytes)
    assert b"customer_id" in csv_bytes
    
    excel_bytes = res.to_excel_bytes()
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0
