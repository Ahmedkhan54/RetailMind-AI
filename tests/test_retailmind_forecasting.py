"""Unit tests for RetailMind AI sales and profit forecasting."""
from __future__ import annotations

import pandas as pd
import pytest

from retailmind.forecasting import (
    available_dimension_values,
    forecast_dataset,
    prepare_series,
)
from retailmind.schema import infer_schema


@pytest.fixture
def daily_sales_df() -> pd.DataFrame:
    # 40 days of linear increasing sales
    dates = pd.date_range("2025-01-01", periods=40, freq="D")
    records = []
    for i, d in enumerate(dates):
        records.append({
            "order_date": d,
            "sales": 100.0 + i * 5.0,
            "profit": 20.0 + i * 1.5,
            "product": "Widget A" if i % 2 == 0 else "Widget B",
            "region": "North",
        })
    return pd.DataFrame(records)


def test_prepare_series_missing_columns():
    df = pd.DataFrame({"product": ["A", "B"]})
    schema = infer_schema(df)
    series, notes = prepare_series(df, schema, "revenue")
    assert series.empty
    assert any("No column is mapped" in n or "Forecasting needs a date column" in n for n in notes)


def test_prepare_series_with_daily_aggregation(daily_sales_df: pd.DataFrame):
    schema = infer_schema(daily_sales_df)
    series, notes = prepare_series(daily_sales_df, schema, "revenue", frequency="Daily")
    assert not series.empty
    assert len(series) == 40
    assert "ds" in series.columns
    assert "y" in series.columns


def test_forecast_short_series_returns_unavailable():
    # Only 5 observations
    dates = pd.date_range("2025-01-01", periods=5, freq="D")
    df = pd.DataFrame({"order_date": dates, "sales": [10, 20, 30, 40, 50]})
    schema = infer_schema(df)
    res = forecast_dataset(df, schema, metric_role="revenue", frequency="Daily")
    assert not res.available
    assert any("observations are available" in note for note in res.notes)


def test_forecast_dataset_methods(daily_sales_df: pd.DataFrame):
    schema = infer_schema(daily_sales_df)
    
    # Test Linear trend
    res_linear = forecast_dataset(
        daily_sales_df, schema, metric_role="revenue",
        frequency="Daily", periods=7, method="Linear trend",
    )
    assert res_linear.available
    assert len(res_linear.forecast) == 7
    assert "forecast" in res_linear.forecast.columns
    assert "lower_bound" in res_linear.forecast.columns
    assert "upper_bound" in res_linear.forecast.columns
    assert res_linear.metrics.get("mae") is not None
    assert res_linear.metrics.get("rmse") is not None
    
    # Test Moving average
    res_ma = forecast_dataset(
        daily_sales_df, schema, metric_role="revenue",
        frequency="Daily", periods=7, method="Moving average",
    )
    assert res_ma.available
    assert len(res_ma.forecast) == 7
    
    # Test Exponential smoothing
    res_es = forecast_dataset(
        daily_sales_df, schema, metric_role="revenue",
        frequency="Daily", periods=7, method="Exponential smoothing",
    )
    assert res_es.available
    assert len(res_es.forecast) == 7
    
    # Test Auto backtest
    res_auto = forecast_dataset(
        daily_sales_df, schema, metric_role="revenue",
        frequency="Daily", periods=7, method="Auto (backtest)",
    )
    assert res_auto.available
    assert len(res_auto.forecast) == 7
    assert res_auto.method in ("Moving average", "Exponential smoothing", "Linear trend")


def test_forecast_dataset_with_dimension_filter(daily_sales_df: pd.DataFrame):
    schema = infer_schema(daily_sales_df)
    res = forecast_dataset(
        daily_sales_df, schema, metric_role="revenue",
        frequency="Daily", periods=7,
        dimension_role="product", dimension_value="Widget A",
    )
    assert res.available
    assert res.dimension == "product"
    assert res.dimension_value == "Widget A"
    assert (res.history["actual"] > 0).sum() == 20  # exactly 20 days with Widget A sales


def test_forecast_exports(daily_sales_df: pd.DataFrame):
    schema = infer_schema(daily_sales_df)
    res = forecast_dataset(daily_sales_df, schema, metric_role="revenue", frequency="Daily", periods=7)
    assert res.available
    
    csv_bytes = res.to_csv_bytes()
    assert isinstance(csv_bytes, bytes)
    assert b"forecast" in csv_bytes
    
    excel_bytes = res.to_excel_bytes()
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0


def test_available_dimension_values(daily_sales_df: pd.DataFrame):
    schema = infer_schema(daily_sales_df)
    values = available_dimension_values(daily_sales_df, schema, "product")
    assert "Widget A" in values
    assert "Widget B" in values
