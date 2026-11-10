"""Deterministic enterprise analytics with no optional ML runtime dependency."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _customer_column(frame: pd.DataFrame) -> str | None:
    for name in ("customer", "customer_id"):
        if name in frame.columns and frame[name].notna().any():
            return name
    return None


def rfm_segments(frame: pd.DataFrame, *, as_of: object | None = None) -> pd.DataFrame:
    """Return explainable five-quintile RFM segments for the active filter scope."""
    customer = _customer_column(frame)
    required = {"order_date", "order_id", "sales"}
    if customer is None or not required.issubset(frame.columns):
        return pd.DataFrame(columns=["customer", "recency_days", "frequency", "monetary", "segment"])
    data = frame.dropna(subset=[customer, "order_date"]).copy()
    if data.empty:
        return pd.DataFrame(columns=["customer", "recency_days", "frequency", "monetary", "segment"])
    anchor = pd.Timestamp(as_of) if as_of is not None else data["order_date"].max() + pd.Timedelta(days=1)
    result = data.groupby(customer, dropna=True).agg(
        recency_days=("order_date", lambda values: int((anchor - values.max()).days)),
        frequency=("order_id", "nunique"), monetary=("sales", "sum"),
    ).reset_index().rename(columns={customer: "customer"})
    # rank(method='first') makes equal values deterministic and qcut safe for small datasets.
    bins = min(5, len(result))
    result["r_score"] = pd.qcut(result["recency_days"].rank(method="first", ascending=False), bins, labels=False) + 1
    result["f_score"] = pd.qcut(result["frequency"].rank(method="first"), bins, labels=False) + 1
    result["m_score"] = pd.qcut(result["monetary"].rank(method="first"), bins, labels=False) + 1
    score = result[["r_score", "f_score", "m_score"]].mean(axis=1)
    result["segment"] = np.select([score >= 4, score >= 3, score >= 2], ["Champions", "Loyal", "Potential"], default="At Risk")
    return result.sort_values(["segment", "monetary"], ascending=[True, False], kind="stable").drop(columns=["r_score", "f_score", "m_score"])


def forecast_sales_profit(frame: pd.DataFrame, *, months: int = 3) -> pd.DataFrame:
    """Forecast 3--6 monthly periods with a transparent least-squares trend."""
    if not 3 <= months <= 6:
        raise ValueError("months must be between 3 and 6")
    if not {"order_date", "sales", "profit"}.issubset(frame.columns):
        return pd.DataFrame(columns=["month", "forecast_sales", "forecast_profit"])
    data = frame.dropna(subset=["order_date"]).copy()
    if data.empty:
        return pd.DataFrame(columns=["month", "forecast_sales", "forecast_profit"])
    data["month"] = pd.to_datetime(data["order_date"]).dt.to_period("M").dt.to_timestamp()
    history = data.groupby("month", as_index=False)[["sales", "profit"]].sum().sort_values("month")
    if len(history) < 3:
        return pd.DataFrame(columns=["month", "forecast_sales", "forecast_profit"])
    x = np.arange(len(history), dtype=float)
    future_x = np.arange(len(history), len(history) + months, dtype=float)
    future = pd.DataFrame({"month": pd.date_range(history["month"].iloc[-1] + pd.offsets.MonthBegin(), periods=months, freq="MS")})
    for source, target in (("sales", "forecast_sales"), ("profit", "forecast_profit")):
        slope, intercept = np.polyfit(x, history[source].astype(float), 1)
        future[target] = np.maximum(0, slope * future_x + intercept).round(2)
    return future


def scenario_projection(total_sales: float, total_profit: float, discount_shift_points: float, margin_shift_points: float) -> dict[str, float]:
    """Model discount as revenue erosion and margin as a profit-rate adjustment."""
    adjusted_sales = float(total_sales) * (1 - float(discount_shift_points) / 100)
    projected_profit = float(total_profit) - (float(total_sales) - adjusted_sales) + adjusted_sales * float(margin_shift_points) / 100
    return {"projected_sales": adjusted_sales, "projected_profit": projected_profit, "profit_change": projected_profit - float(total_profit)}
