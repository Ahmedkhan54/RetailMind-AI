"""Unit tests for RetailMind AI advanced insights engine."""
from __future__ import annotations

import pandas as pd
import pytest

from retailmind.alerts import Alert
from retailmind.forecasting import forecast_dataset
from retailmind.insights_engine import generate_advanced_insights
from retailmind.inventory import build_inventory_recommendations
from retailmind.schema import infer_schema
from retailmind.segmentation import segment_customers


@pytest.fixture
def sales_df() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=30, freq="D")
    return pd.DataFrame({
        "order_id": [f"O_{i}" for i in range(30)],
        "order_date": dates,
        "sales": [100.0 + i * 10.0 for i in range(30)],
        "profit": [20.0 + i * 2.0 for i in range(30)],
        "cost": [80.0 + i * 8.0 for i in range(30)],
        "quantity": [5] * 30,
        "customer": [f"Cust_{i % 5}" for i in range(30)],
        "product": ["Widget A"] * 15 + ["Widget B"] * 15,
        "region": ["North"] * 15 + ["South"] * 15,
    })


def test_advanced_insights_empty():
    df = pd.DataFrame()
    schema = infer_schema(df)
    res = generate_advanced_insights(df, schema)
    assert res.is_empty()
    assert len(res.notes) > 0


def test_advanced_insights_comprehensive(sales_df: pd.DataFrame):
    schema = infer_schema(sales_df)
    alert = Alert(title="Revenue growth", description="Sales grew 15%", metric="revenue", severity="info")
    forecast = forecast_dataset(sales_df, schema, metric_role="revenue", periods=7)
    segmentation = segment_customers(sales_df, schema, max_clusters=3)
    inventory = build_inventory_recommendations(sales_df, schema)
    
    insights = generate_advanced_insights(
        sales_df,
        schema,
        alerts=[alert],
        forecast=forecast,
        segmentation=segmentation,
        inventory=inventory,
    )
    
    assert not insights.is_empty()
    assert len(insights.facts) > 0
    assert len(insights.forecasts) > 0
    assert len(insights.recommendations) > 0
    assert any("revenue" in f.lower() or "sales" in f.lower() for f in insights.facts)
    assert any("rule-based" in r.lower() or "review" in r.lower() or "pricing" in r.lower() for r in insights.recommendations)
