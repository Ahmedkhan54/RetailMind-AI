"""Advanced business insights with explicit evidence categories.

The output separates:

* verified facts — deterministic aggregates of the active dataset
* statistical anomalies — alerts with a stated method and comparison
* forecasts — model output with its measured error
* recommendations — rule-based next steps, never causal claims

Correlation is never described as causation, and no recommendation is phrased
as a proven cause.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from retailmind.alerts import Alert
from retailmind.forecasting import ForecastResult
from retailmind.inventory import InventoryResult
from retailmind.schema import DatasetSchema
from retailmind.segmentation import SegmentationResult
from retailmind.utils import format_number, money, safe_divide, safe_percent


@dataclass
class AdvancedInsights:
    facts: list[str] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)
    forecasts: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.facts or self.anomalies or self.forecasts or self.recommendations)


def _sum(frame: pd.DataFrame, column: str | None) -> float:
    if not column or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").sum())


def _top_share(frame: pd.DataFrame, dimension: str | None, measure: str | None) -> tuple[str | None, float | None, float | None]:
    if not dimension or not measure or dimension not in frame.columns or measure not in frame.columns:
        return None, None, None
    working = pd.DataFrame(
        {
            "group": frame[dimension].astype("string"),
            "value": pd.to_numeric(frame[measure], errors="coerce"),
        }
    ).dropna()
    if working.empty:
        return None, None, None
    totals = working.groupby("group")["value"].sum().sort_values(ascending=False)
    total = float(totals.sum())
    if total == 0:
        return str(totals.index[0]) if len(totals) else None, 0.0, total
    return str(totals.index[0]), float(totals.iloc[0] / total), total


def _monthly_revenue(frame: pd.DataFrame, schema: DatasetSchema) -> pd.Series:
    date = schema.role_column("date")
    revenue = schema.role_column("revenue")
    if not date or not revenue:
        return pd.Series(dtype=float)
    working = pd.DataFrame(
        {
            "date": pd.to_datetime(frame[date], format="mixed", errors="coerce"),
            "value": pd.to_numeric(frame[revenue], errors="coerce"),
        }
    ).dropna()
    if working.empty:
        return pd.Series(dtype=float)
    return working.assign(month=lambda data: data["date"].dt.to_period("M")).groupby("month")["value"].sum().sort_index()


def generate_advanced_insights(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    alerts: Iterable[Alert] = (),
    forecast: ForecastResult | None = None,
    segmentation: SegmentationResult | None = None,
    inventory: InventoryResult | None = None,
) -> AdvancedInsights:
    result = AdvancedInsights()
    if frame is None or frame.empty:
        result.notes.append("No rows are available in the active filtered dataset.")
        return result

    revenue_column = schema.role_column("revenue")
    profit_column = schema.role_column("profit")
    cost_column = schema.role_column("cost")
    order_column = schema.role_column("order_id")
    quantity_column = schema.role_column("quantity")
    customer_column = schema.role_column("customer")
    date_column = schema.role_column("date")

    revenue = _sum(frame, revenue_column)
    profit = _sum(frame, profit_column)
    cost = _sum(frame, cost_column)
    orders = int(frame[order_column].nunique(dropna=True)) if order_column else len(frame)
    quantity = _sum(frame, quantity_column) if quantity_column else None
    margin = safe_divide(profit, revenue) if profit_column and revenue else None
    result.metrics = {
        "rows": int(len(frame)),
        "revenue": revenue if revenue_column else None,
        "profit": profit if profit_column else None,
        "cost": cost if cost_column else None,
        "margin": margin,
        "orders": orders,
        "quantity": quantity,
    }

    if revenue_column:
        result.facts.append(f"Total revenue in the active filtered data is {money(revenue)} across {len(frame):,} rows.")
    if profit_column:
        result.facts.append(f"Total profit is {money(profit)} and profit margin is {safe_percent(margin)}.")
    if cost_column:
        result.facts.append(f"Total recorded cost/expenses are {money(cost)}.")
    result.facts.append(f"The active data contains {orders:,} distinct orders (or rows when no order ID is mapped).")
    if quantity is not None:
        result.facts.append(f"Total quantity is {format_number(quantity)} units.")

    category = schema.role_column("category")
    product = schema.role_column("product")
    region = schema.role_column("region") or schema.role_column("city")
    for label, dimension in (("category", category), ("product", product), ("region", region)):
        name, share, total = _top_share(frame, dimension, revenue_column)
        if name is not None and share is not None:
            result.facts.append(
                f"The largest {label} by revenue is '{name}' with {share:.1%} of the {label} total "
                f"({money(total * share)} of {money(total)})."
            )
            if share >= 0.50:
                result.recommendations.append(
                    f"Revenue concentration in the largest {label} ('{name}', {share:.1%}) is high; "
                    "review dependency risk and the breadth of the contributing base."
                )

    if customer_column:
        customers = int(frame[customer_column].nunique(dropna=True))
        result.facts.append(f"The active data contains {customers:,} distinct customers.")
        working = pd.DataFrame(
            {
                "customer": frame[customer_column].astype("string"),
                "value": pd.to_numeric(frame[revenue_column], errors="coerce") if revenue_column else np.nan,
            }
        ).dropna()
        if len(working) >= 10:
            totals = working.groupby("customer")["value"].sum().sort_values(ascending=False)
            top_count = max(1, int(round(len(totals) * 0.1)))
            top_share = float(totals.head(top_count).sum() / totals.sum()) if totals.sum() else None
            if top_share is not None:
                result.facts.append(
                    f"The top 10% of customers account for {top_share:.1%} of revenue."
                )
                if top_share >= 0.60:
                    result.recommendations.append(
                        "Customer revenue is concentrated in the top 10%; review retention risk for those accounts."
                    )

    monthly = _monthly_revenue(frame, schema)
    if len(monthly) >= 2:
        first, last = float(monthly.iloc[0]), float(monthly.iloc[-1])
        change = safe_divide(last - first, abs(first)) if first else None
        if change is not None:
            result.facts.append(
                f"Monthly revenue moved from {money(first)} in {monthly.index[0]} to {money(last)} "
                f"in {monthly.index[-1]} ({change:+.1%}). This is a descriptive comparison, not a causal claim."
            )

    # Data completeness facts for the fields used above.
    key_columns = [column for column in (revenue_column, profit_column, date_column, customer_column) if column]
    if key_columns:
        missing = int(frame[key_columns].isna().sum().sum())
        total_cells = max(1, len(frame) * len(key_columns))
        result.facts.append(f"Key analytical fields are {missing / total_cells:.1%} missing ({missing:,} cells).")
        if missing / total_cells >= 0.10:
            result.recommendations.append(
                "Key fields have material missingness; improve completeness before relying on totals or trends."
            )

    # Anomalies are copied from auditable alerts, not invented here.
    for alert in alerts:
        if alert.severity in {"critical", "warning"}:
            result.anomalies.append(f"[{alert.severity.upper()}] {alert.title}: {alert.description}")
        elif alert.metric.endswith(("_outliers", "_iqr_outliers")):
            result.anomalies.append(f"[INFO] {alert.title}: {alert.description}")
    if not result.anomalies:
        result.anomalies.append("No critical or warning statistical anomalies were detected in the current comparison window.")

    if forecast and forecast.available and not forecast.forecast.empty:
        next_value = float(forecast.forecast["forecast"].iloc[0])
        mape = forecast.metrics.get("mape")
        mae = forecast.metrics.get("mae")
        result.forecasts.append(
            f"{forecast.metric} is forecast to be {format_number(next_value)} at the next {forecast.frequency} "
            f"period using {forecast.method}."
        )
        result.forecasts.append(
            f"Hold-out error: MAE {format_number(mae)}, MAPE {f'{mape:.1f}%' if mape is not None else 'N/A'} "
            f"(train {forecast.train_size}, test {forecast.test_size} observations)."
        )
        if mape is not None and mape > 30:
            result.recommendations.append(
                "Forecast error is high (MAPE above 30%); treat the forecast as directional and add more history before operational use."
            )
    elif forecast and not forecast.available and forecast.notes:
        result.forecasts.append("Forecast unavailable: " + forecast.notes[0])

    if segmentation and segmentation.available and not segmentation.summary.empty:
        for _index, row in segmentation.summary.head(3).iterrows():
            result.facts.append(
                f"Customer segment '{row['segment']}' contains {int(row['customers']):,} customers "
                f"({row['customer_share']:.1%}) and {row['revenue_share']:.1%} of revenue."
            )
        at_risk = segmentation.rfm[segmentation.rfm["segment"].isin(["At-Risk Customers", "Churn Risk Customers"])]
        if len(at_risk):
            result.recommendations.append(
                f"{len(at_risk):,} customers are in At-Risk or Churn Risk segments; review retention outreach. "
                "The risk flag is rule-based, not a validated future-churn probability."
            )
    elif segmentation and not segmentation.available and segmentation.notes:
        result.forecasts.append("Customer segmentation unavailable: " + segmentation.notes[0])

    if inventory and inventory.available and not inventory.table.empty:
        critical = inventory.table[inventory.table["status"].isin(["Out of stock", "Critical — reorder now", "Low — reorder soon"])]
        if len(critical):
            result.facts.append(f"{len(critical):,} product(s) are at or below their reorder point in the inventory analysis.")
            result.recommendations.append(
                "Review the inventory recommendations for products at or below their reorder point before the next replenishment cycle."
            )
        if not inventory.stock_available:
            result.notes.append(
                "Inventory recommendations are partial because no current-stock column was supplied; "
                "days remaining and suggested quantities are intentionally blank."
            )
    elif inventory and not inventory.available and inventory.notes:
        result.notes.append(inventory.notes[0])

    if not result.recommendations:
        result.recommendations.append(
            "No rule-based action is implied by the current data; continue monitoring the verified KPIs and alerts."
        )
    result.notes.append(
        "Facts are deterministic aggregates. Anomalies state their statistical method. Forecasts report hold-out error. "
        "Recommendations are rules, not causal claims."
    )
    return result
