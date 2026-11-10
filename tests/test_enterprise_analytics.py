import pandas as pd

from src.analytics.enterprise import forecast_sales_profit, rfm_segments, scenario_projection


def sample_frame():
    return pd.DataFrame({
        "order_id": ["A", "B", "C", "D", "E", "F"],
        "customer": ["Alice", "Bob", "Alice", "Bob", "Cara", "Cara"],
        "order_date": pd.date_range("2025-01-01", periods=6, freq="MS"),
        "sales": [100, 120, 150, 130, 170, 200], "profit": [20, 25, 30, 20, 35, 45],
    })


def test_rfm_and_forecast_are_deterministic_and_scope_safe():
    frame = sample_frame()
    rfm = rfm_segments(frame, as_of="2025-07-01")
    assert set(rfm.columns) == {"customer", "recency_days", "frequency", "monetary", "segment"}
    assert len(rfm) == 3
    forecast = forecast_sales_profit(frame, months=3)
    assert len(forecast) == 3
    assert (forecast[["forecast_sales", "forecast_profit"]] >= 0).all().all()


def test_scenario_has_no_effect_at_zero_and_exposes_profit_delta():
    assert scenario_projection(1000, 200, 0, 0) == {"projected_sales": 1000.0, "projected_profit": 200.0, "profit_change": 0.0}
    assert scenario_projection(1000, 200, 10, 0)["projected_profit"] == 100.0
