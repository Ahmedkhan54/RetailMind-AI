"""Predictive stock recommendations.

Stock levels are never invented.  When a stock column is absent the module
still calculates demand, reorder points and safety stock from sales history,
but leaves days-remaining, depletion dates and suggested quantities blank and
explains exactly which column is required.

All formulas are documented in the result's ``assumptions`` list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import math
from typing import Any

import numpy as np
import pandas as pd

from data_sources import normalise_name
from retailmind.schema import DatasetSchema


STOCK_ALIASES = (
    "current stock", "stock", "stock level", "inventory", "inventory level",
    "on hand", "onhand", "quantity on hand", "available stock", "closing stock",
    "stock on hand", "units in stock",
)
LEAD_ALIASES = ("lead time", "supplier lead time", "delivery lead time", "lead days", "delivery days")
SAFETY_ALIASES = ("safety stock", "safety_stock", "buffer stock", "minimum stock", "min stock")
INCOMING_ALIASES = ("incoming", "incoming orders", "on order", "purchase orders", "incoming stock", "open orders")


@dataclass
class InventoryResult:
    available: bool
    table: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    stock_available: bool = False
    columns: dict[str, str | None] = field(default_factory=dict)

    def to_csv_bytes(self) -> bytes:
        return self.table.to_csv(index=False).encode("utf-8-sig")

    def to_excel_bytes(self) -> bytes:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            self.table.to_excel(writer, sheet_name="Inventory Recommendations", index=False)
            pd.DataFrame({"assumption": self.assumptions + self.notes}).to_excel(
                writer, sheet_name="Assumptions", index=False
            )
        return output.getvalue()


def _find_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    normalised = {column: normalise_name(str(column)) for column in frame.columns}
    for alias in aliases:
        for column, name in normalised.items():
            if name == alias:
                return column
    for alias in aliases:
        for column, name in normalised.items():
            if alias in name:
                return column
    return None


def detect_inventory_columns(frame: pd.DataFrame, schema: DatasetSchema) -> dict[str, str | None]:
    product = schema.role_column("product") or _find_column(frame, ("product", "product name", "sku", "item", "item name"))
    date = schema.role_column("date") or (schema.dates[0] if schema.dates else None)
    quantity = schema.role_column("quantity") or _find_column(
        frame, ("quantity", "qty", "units sold", "sales quantity", "units", "quantity sold")
    )
    stock = _find_column(frame, STOCK_ALIASES)
    if stock == quantity:
        stock = None
    lead = _find_column(frame, LEAD_ALIASES)
    safety = _find_column(frame, SAFETY_ALIASES)
    incoming = _find_column(frame, INCOMING_ALIASES)
    return {
        "product": product,
        "date": date,
        "quantity": quantity,
        "stock": stock,
        "lead_time": lead,
        "safety_stock": safety,
        "incoming": incoming,
    }


def _first_numeric(series: pd.Series, default: float) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.iloc[0]) if len(values) else default


def _es_level(values: np.ndarray, alpha: float = 0.3) -> float:
    level = float(values[0])
    for value in values[1:]:
        level = alpha * float(value) + (1 - alpha) * level
    return level


def build_inventory_recommendations(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    lead_time_days: float = 7.0,
    safety_days: float = 7.0,
    service_level: float = 0.95,
    history_window: int = 28,
    target_cover_days: float = 14.0,
    method: str = "Exponential smoothing",
) -> InventoryResult:
    columns = detect_inventory_columns(frame, schema)
    missing = [name for name in ("product", "date", "quantity") if not columns.get(name)]
    if missing:
        return InventoryResult(
            available=False,
            columns=columns,
            notes=[
                "Stock recommendations need a product, a sales date and a quantity sold. "
                f"Missing: {', '.join(missing)}."
            ],
        )
    working = pd.DataFrame(
        {
            "product": frame[columns["product"]].astype("string"),
            "date": pd.to_datetime(frame[columns["date"]], format="mixed", errors="coerce"),
            "quantity": pd.to_numeric(frame[columns["quantity"]], errors="coerce"),
        }
    )
    if columns.get("stock"):
        working["stock"] = pd.to_numeric(frame[columns["stock"]], errors="coerce")
    if columns.get("lead_time"):
        working["lead_time"] = pd.to_numeric(frame[columns["lead_time"]], errors="coerce")
    if columns.get("safety_stock"):
        working["safety_stock"] = pd.to_numeric(frame[columns["safety_stock"]], errors="coerce")
    if columns.get("incoming"):
        working["incoming"] = pd.to_numeric(frame[columns["incoming"]], errors="coerce")
    working = working.dropna(subset=["product", "date", "quantity"])
    working = working[working["product"].str.strip() != ""]
    if working.empty:
        return InventoryResult(
            available=False,
            columns=columns,
            notes=["No valid product/date/quantity rows were found."],
        )

    z = {0.90: 1.2816, 0.95: 1.6449, 0.98: 2.0537, 0.99: 2.3263}.get(round(float(service_level), 2), 1.6449)
    stock_available = bool(columns.get("stock"))
    rows: list[dict[str, Any]] = []
    last_date = working["date"].max()
    for product, group in working.groupby("product", dropna=True):
        daily = group.set_index("date")["quantity"].resample("D").sum()
        if daily.empty:
            continue
        # A regular daily calendar is required for days-of-cover maths.  Days
        # with no recorded sale are zero demand, not missing observations.
        full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
        daily = daily.reindex(full_index, fill_value=0.0)
        recent = daily.tail(max(7, int(history_window))).to_numpy(dtype=float)
        total_quantity = float(daily.sum())
        span_days = max(1, int((daily.index.max() - daily.index.min()).days) + 1)
        avg_daily = float(total_quantity / span_days)
        avg_daily_recent = float(np.mean(recent)) if len(recent) else avg_daily
        if method == "Moving average":
            forecast_daily = float(np.mean(recent[-min(7, len(recent)):])) if len(recent) else avg_daily
        else:
            forecast_daily = _es_level(recent) if len(recent) else avg_daily
        forecast_daily = max(0.0, forecast_daily)
        std_daily = float(np.std(recent, ddof=1)) if len(recent) > 1 else 0.0
        lead = _first_numeric(group["lead_time"], lead_time_days) if "lead_time" in group else lead_time_days
        lead = max(1.0, float(lead))
        safety_override = (
            _first_numeric(group["safety_stock"], float("nan")) if "safety_stock" in group else float("nan")
        )
        safety = (
            float(safety_override)
            if math.isfinite(safety_override)
            else z * std_daily * math.sqrt(lead) if std_daily > 0 else forecast_daily * safety_days
        )
        reorder_point = forecast_daily * lead + safety
        stock = _first_numeric(group["stock"], float("nan")) if "stock" in group else float("nan")
        incoming = _first_numeric(group["incoming"], 0.0) if "incoming" in group else 0.0
        days_remaining = stock / avg_daily_recent if stock_available and avg_daily_recent > 0 and math.isfinite(stock) else None
        depletion_date = (
            (last_date + pd.Timedelta(days=float(days_remaining))).date().isoformat()
            if days_remaining is not None
            else None
        )
        suggested = None
        if stock_available and math.isfinite(stock):
            target = reorder_point + forecast_daily * target_cover_days
            suggested = max(0.0, target - (stock + incoming))
        if not stock_available or not math.isfinite(stock):
            status = "Stock data required"
        elif stock <= 0:
            status = "Out of stock"
        elif days_remaining is not None and days_remaining <= lead:
            status = "Critical — reorder now"
        elif stock <= reorder_point:
            status = "Low — reorder soon"
        else:
            status = "Healthy"
        rows.append(
            {
                "product": str(product),
                "avg_daily_sales": round(avg_daily, 3),
                "avg_weekly_sales": round(avg_daily * 7, 3),
                "recent_daily_demand": round(avg_daily_recent, 3),
                "forecast_daily_demand": round(forecast_daily, 3),
                "lead_time_days": round(lead, 1),
                "safety_stock": round(safety, 2),
                "reorder_point": round(reorder_point, 2),
                "current_stock": round(stock, 2) if math.isfinite(stock) else None,
                "incoming_orders": round(incoming, 2) if incoming else None,
                "days_remaining": round(days_remaining, 1) if days_remaining is not None else None,
                "estimated_depletion_date": depletion_date,
                "suggested_reorder_quantity": round(suggested, 2) if suggested is not None else None,
                "status": status,
                "history_start": daily.index.min().date().isoformat(),
                "history_end": daily.index.max().date().isoformat(),
            }
        )
    table = pd.DataFrame(rows)
    if table.empty:
        return InventoryResult(available=False, columns=columns, notes=["No product had enough history for a recommendation."])
    order = {
        "Out of stock": 0,
        "Critical — reorder now": 1,
        "Low — reorder soon": 2,
        "Stock data required": 3,
        "Healthy": 4,
    }
    table["_order"] = table["status"].map(order).fillna(5)
    table = table.sort_values(["_order", "days_remaining"], na_position="last").drop(columns="_order").reset_index(drop=True)
    notes: list[str] = []
    if not stock_available:
        notes.append(
            "No current-stock column was found. Demand, safety stock and reorder points are shown, "
            "but days remaining, depletion dates and suggested quantities require a stock level. "
            "Add a column such as 'Current Stock' or 'On Hand' to unlock them."
        )
    assumptions = [
        f"Average daily sales uses the full product history; recent demand uses the last {max(7, int(history_window))} days.",
        f"Lead time defaults to {lead_time_days:g} days when no supplier lead-time column is present.",
        f"Safety stock uses z={z:.4f} for a {service_level:.0%} service level when demand variability exists; "
        f"otherwise it falls back to {safety_days:g} days of forecast demand.",
        f"Suggested quantity targets the reorder point plus {target_cover_days:g} days of cover, minus current stock and incoming orders.",
        "Missing calendar days are treated as zero demand; no stock level is ever invented.",
    ]
    return InventoryResult(
        available=True,
        table=table,
        notes=notes,
        assumptions=assumptions,
        stock_available=stock_available,
        columns=columns,
    )
