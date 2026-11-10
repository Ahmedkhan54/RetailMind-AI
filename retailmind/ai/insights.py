"""Verified, rule-based business insights.

Insights are generated from calculations on the active dataset.  The wording
distinguishes correlation from causation and always states the analysis period
or comparison baseline when one is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from retailmind.schema import DatasetSchema
from retailmind.utils import format_number, money, safe_divide, safe_percent


@dataclass
class Insight:
    title: str
    text: str
    severity: str = "info"  # positive | warning | negative | info
    evidence: dict[str, Any] = field(default_factory=dict)
    period: str | None = None
    baseline: str | None = None

    def evidence_text(self) -> str:
        parts: list[str] = []
        for key, value in self.evidence.items():
            if isinstance(value, float):
                parts.append(f"{key}: {format_number(value)}")
            else:
                parts.append(f"{key}: {value}")
        if self.period:
            parts.append(f"Period: {self.period}")
        if self.baseline:
            parts.append(f"Baseline: {self.baseline}")
        return " · ".join(parts)


def _dimension_candidates(schema: DatasetSchema) -> list[str]:
    ordered: list[str] = []
    for role in ("product", "category", "region", "city", "store", "department", "course", "customer", "sales_rep", "payment_method"):
        column = schema.role_column(role)
        if column and column not in ordered:
            ordered.append(column)
    return ordered


def _top_share(frame: pd.DataFrame, dimension: str, measure: str, top_fraction: float = 0.2) -> tuple[float | None, int]:
    working = frame[[dimension, measure]].copy()
    working[measure] = pd.to_numeric(working[measure], errors="coerce")
    grouped = working.dropna(subset=[measure]).groupby(dimension, dropna=False)[measure].sum().sort_values(ascending=False)
    if grouped.empty or grouped.sum() == 0:
        return None, 0
    count = max(1, int(len(grouped) * top_fraction))
    return float(grouped.head(count).sum() / grouped.sum()), count


def _trend(frame: pd.DataFrame, schema: DatasetSchema) -> tuple[str, float, float, float | None] | None:
    date_column = schema.role_column("date")
    measure = schema.role_column("revenue") or schema.role_column("profit") or schema.role_column("salary")
    if not date_column or not measure:
        return None
    dates = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
    values = pd.to_numeric(frame[measure], errors="coerce")
    working = pd.DataFrame({"date": dates, "value": values}).dropna()
    if len(working) < 4:
        return None
    start, end = working["date"].min().normalize(), working["date"].max().normalize()
    span_days = max(1, (end - start).days + 1)
    period_days = 30 if span_days >= 60 else max(1, span_days // 2)
    current = working[working["date"] > end - pd.Timedelta(days=period_days)]["value"].sum()
    previous = working[(working["date"] > end - pd.Timedelta(days=period_days * 2)) & (working["date"] <= end - pd.Timedelta(days=period_days))]["value"].sum()
    change = safe_divide(current - previous, abs(previous)) if previous else None
    label = f"{end - pd.Timedelta(days=period_days - 1):%d %b %Y} to {end:%d %b %Y}"
    return label, float(current), float(previous), change


def generate_insights(frame: pd.DataFrame, schema: DatasetSchema, max_items: int = 8) -> list[Insight]:
    insights: list[Insight] = []
    if frame.empty:
        return [Insight("No records", "No rows match the active filters, so no business insight can be calculated.", "warning")]

    revenue_column = schema.role_column("revenue")
    profit_column = schema.role_column("profit")
    cost_column = schema.role_column("cost")

    if revenue_column:
        revenue = pd.to_numeric(frame[revenue_column], errors="coerce").sum()
        insights.append(
            Insight(
                "Revenue baseline",
                f"Total revenue for the active filters is {money(revenue)} across {len(frame):,} records.",
                "info",
                {"Revenue": float(revenue), "Records": len(frame)},
            )
        )

    if revenue_column and profit_column:
        revenue = pd.to_numeric(frame[revenue_column], errors="coerce").sum()
        profit = pd.to_numeric(frame[profit_column], errors="coerce").sum()
        margin = safe_divide(profit, revenue)
        severity = "positive" if margin is not None and margin >= 0.15 else ("warning" if margin is not None and margin >= 0 else "negative")
        insights.append(
            Insight(
                "Profitability",
                f"Profit is {money(profit)} on revenue of {money(revenue)}, a margin of {safe_percent(margin)}.",
                severity,
                {"Profit": float(profit), "Margin": margin},
            )
        )
        negative = pd.to_numeric(frame[profit_column], errors="coerce") < 0
        if negative.any():
            insights.append(
                Insight(
                    "Loss-making records",
                    f"{int(negative.sum()):,} of {len(frame):,} records ({negative.mean():.1%}) have negative profit.",
                    "negative",
                    {"Negative records": int(negative.sum()), "Share": float(negative.mean())},
                )
            )

    dimensions = _dimension_candidates(schema)
    measure = revenue_column or profit_column or (schema.measures[0] if schema.measures else None)
    for dimension in dimensions[:2]:
        if not measure or dimension not in frame.columns:
            continue
        working = frame[[dimension, measure]].copy()
        working[measure] = pd.to_numeric(working[measure], errors="coerce")
        grouped = working.dropna(subset=[measure]).groupby(dimension, dropna=False)[measure].sum().sort_values(ascending=False)
        if grouped.empty or grouped.sum() == 0:
            continue
        leader = grouped.index[0]
        share = float(grouped.iloc[0] / grouped.sum())
        insights.append(
            Insight(
                f"Top {schema.label_for(dimension)}",
                f"{leader} contributes {share:.1%} of total {schema.label_for(measure).lower()} ({money(float(grouped.iloc[0])) if measure in (revenue_column, profit_column) else format_number(float(grouped.iloc[0]))}).",
                "info",
                {"Leader": str(leader), "Share": share, "Groups": int(grouped.size)},
            )
        )
        concentration, count = _top_share(frame, dimension, measure)
        if concentration is not None and count > 1:
            insights.append(
                Insight(
                    "Concentration risk",
                    f"The top {count} {schema.label_for(dimension).lower()} account for {concentration:.1%} of total {schema.label_for(measure).lower()}.",
                    "warning" if concentration >= 0.6 else "info",
                    {"Top groups": count, "Share": concentration},
                )
            )
        break

    if revenue_column and profit_column:
        working = frame[[revenue_column, profit_column]].copy()
        working[revenue_column] = pd.to_numeric(working[revenue_column], errors="coerce")
        working[profit_column] = pd.to_numeric(working[profit_column], errors="coerce")
        working = working.dropna()
        if not working.empty:
            working["margin"] = working[profit_column] / working[revenue_column].replace(0, pd.NA)
            median_revenue = working[revenue_column].median()
            median_margin = working["margin"].median()
            underperformers = working[(working[revenue_column] >= median_revenue) & (working["margin"] < median_margin)]
            if not underperformers.empty:
                insights.append(
                    Insight(
                        "Margin watchlist",
                        f"{len(underperformers):,} high-revenue records have below-median margin ({safe_percent(median_margin)} median).",
                        "warning",
                        {"Records": len(underperformers), "Median margin": float(median_margin) if pd.notna(median_margin) else None},
                    )
                )

    trend = _trend(frame, schema)
    if trend:
        label, current, previous, change = trend
        if change is not None:
            direction = "increased" if change >= 0 else "decreased"
            insights.append(
                Insight(
                    "Recent movement",
                    f"{schema.label_for(schema.role_column('revenue') or schema.role_column('profit') or schema.role_column('salary'))} {direction} by {safe_percent(abs(change))} in the latest period.",
                    "positive" if change >= 0 else "negative",
                    {"Current": current, "Previous": previous, "Change": change},
                    period=label,
                    baseline="Immediately preceding equal-length period",
                )
            )

    discount = schema.role_column("discount")
    if discount and revenue_column and profit_column:
        working = frame[[discount, revenue_column, profit_column]].copy()
        for column in (discount, revenue_column, profit_column):
            working[column] = pd.to_numeric(working[column], errors="coerce")
        working = working.dropna()
        if len(working) > 5 and working[discount].nunique() > 1:
            working["margin"] = working[profit_column] / working[revenue_column].replace(0, pd.NA)
            correlation = working[discount].corr(working["margin"])
            if pd.notna(correlation):
                insights.append(
                    Insight(
                        "Discount association",
                        f"Discount and margin show a {correlation:+.2f} correlation. This is an association, not proof that discounts caused the margin change.",
                        "info",
                        {"Correlation": float(correlation), "Records": len(working)},
                    )
                )

    salary = schema.role_column("salary")
    if salary:
        values = pd.to_numeric(frame[salary], errors="coerce").dropna()
        if not values.empty:
            insights.append(
                Insight(
                    "Compensation",
                    f"Average salary is {money(float(values.mean()))}; the range is {money(float(values.min()))} to {money(float(values.max()))}.",
                    "info",
                    {"Average": float(values.mean()), "Minimum": float(values.min()), "Maximum": float(values.max())},
                )
            )
        employee = schema.role_column("employee_id") or schema.role_column("employee_name")
        if employee:
            insights.append(
                Insight(
                    "Headcount",
                    f"{frame[employee].nunique(dropna=True):,} distinct employees are present in the active data.",
                    "info",
                    {"Employees": int(frame[employee].nunique(dropna=True))},
                )
            )

    if cost_column and revenue_column:
        cost = pd.to_numeric(frame[cost_column], errors="coerce").sum()
        revenue = pd.to_numeric(frame[revenue_column], errors="coerce").sum()
        ratio = safe_divide(cost, revenue)
        if ratio is not None:
            insights.append(
                Insight(
                    "Expense ratio",
                    f"Expenses are {money(cost)}, equal to {safe_percent(ratio)} of revenue.",
                    "warning" if ratio > 0.8 else "info",
                    {"Expenses": float(cost), "Ratio": ratio},
                )
            )

    if schema.has("attendance"):
        attendance_column = schema.role_column("attendance")
        values = frame[attendance_column].dropna().astype("string").str.strip().str.lower()
        truthy = {"present", "yes", "y", "true", "1", "p", "attended"}
        falsy = {"absent", "no", "n", "false", "0", "a", "missed"}
        recognised = values[values.isin(truthy | falsy)]
        if not recognised.empty:
            rate = float(recognised.isin(truthy).mean())
            insights.append(
                Insight(
                    "Attendance",
                    f"Attendance rate is {safe_percent(rate)} across {len(recognised):,} recognised attendance records.",
                    "positive" if rate >= 0.9 else ("warning" if rate >= 0.75 else "negative"),
                    {"Attendance rate": rate, "Records": len(recognised)},
                )
            )

    missing_share = float(frame.isna().sum().sum() / max(1, frame.size))
    if missing_share >= 0.1:
        insights.append(
            Insight(
                "Data completeness",
                f"{missing_share:.1%} of all cells are missing. Review the Data Quality page before relying on totals.",
                "warning",
                {"Missing share": missing_share},
            )
        )

    return insights[:max_items]
