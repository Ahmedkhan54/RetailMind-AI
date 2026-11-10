"""Rule-based natural-language understanding.

This module maps a question to a *structured data operation* (metric, dimension,
aggregation, period).  It never executes code and never invents values.
Numerical execution happens in :mod:`retailmind.ai.chat` with pandas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import re
from typing import Any

import pandas as pd

from data_sources import normalise_name
from retailmind.schema import DatasetSchema


METRIC_SYNONYMS: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "sales", "turnover", "income", "top line", "money", "earned", "earnings", "generated", "billing", "amount"),
    "profit": ("profit", "net profit", "gross profit", "net income", "bottom line", "margin amount"),
    "quantity": ("quantity", "qty", "units", "unit", "volume", "pieces", "sold"),
    "orders": ("order", "orders", "transaction", "transactions", "invoice", "invoices", "purchase", "purchases"),
    "customers": ("customer", "customers", "client", "clients", "buyer", "buyers", "consumer", "consumers"),
    "salary": ("salary", "salaries", "wage", "wages", "payroll", "compensation", "stipend"),
    "cost": ("expense", "expenses", "cost", "costs", "spend", "spending", "expenditure", "overhead"),
    "attendance": ("attendance", "present", "absent", "presence"),
    "employees": ("employee", "employees", "staff", "headcount", "worker", "workers"),
    "grade": ("grade", "grades", "marks", "score", "scores", "result", "results", "gpa"),
    "discount": ("discount", "discounts", "markdown", "rebate"),
}

DIMENSION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "product": ("product", "products", "item", "items", "sku", "skus", "goods"),
    "category": ("category", "categories", "segment", "segments", "type", "types", "class"),
    "city": ("city", "cities", "town", "towns"),
    "region": ("region", "regions", "area", "areas", "zone", "zones", "state", "states", "territory"),
    "customer": ("customer", "customers", "client", "clients", "buyer", "buyers"),
    "department": ("department", "departments", "dept", "division", "team", "teams"),
    "store": ("store", "stores", "branch", "branches", "outlet", "outlets", "shop", "shops"),
    "sales_rep": ("sales rep", "sales representative", "salesperson", "agent", "representative", "rep"),
    "payment_method": ("payment method", "payment type", "payment mode", "tender"),
    "employee_name": ("employee", "employees", "staff", "worker"),
    "course": ("course", "courses", "subject", "subjects", "program", "programme", "class"),
    "gender": ("gender", "sex"),
    "attendance": ("attendance", "present", "absent"),
}

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

COMPARE_WORDS = ("compare", "comparison", "versus", " vs ", "growth", "grew", "increase", "decrease", "change", "trend", "decline")
TOP_WORDS = ("top", "best", "highest", "most", "largest", "leading", "rank", "worst", "lowest")
CHART_WORDS = ("chart", "plot", "graph", "visualise", "visualize", "diagram", "heatmap")


@dataclass
class Period:
    label: str
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None
    comparison_start: pd.Timestamp | None = None
    comparison_end: pd.Timestamp | None = None

    def current(self) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        if self.start is None or self.end is None:
            return None
        return self.start, self.end

    def previous(self) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        if self.comparison_start is None or self.comparison_end is None:
            return None
        return self.comparison_start, self.comparison_end


@dataclass
class QueryIntent:
    kind: str = "unknown"  # total | average | top | compare | count | distribution | explain | unknown
    metric_role: str | None = None
    metric_column: str | None = None
    dimension_role: str | None = None
    dimension_column: str | None = None
    aggregation: str = "sum"
    top_n: int | None = None
    period: Period | None = None
    wants_chart: bool = False
    wants_table: bool = False
    raw: str = ""
    confidence: float = 0.0
    special: str | None = None  # aov | margin
    alternatives: list[str] = field(default_factory=list)

    @property
    def is_actionable(self) -> bool:
        return self.kind != "unknown" and (self.metric_column is not None or self.kind in ("explain", "distribution"))


def _contains(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _find_hint(text: str, synonyms: dict[str, tuple[str, ...]]) -> str | None:
    best: tuple[int, str] | None = None
    for key, phrases in synonyms.items():
        for phrase in phrases:
            if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text):
                score = len(phrase)
                if best is None or score > best[0]:
                    best = (score, key)
    return best[1] if best else None


def _match_column(schema: DatasetSchema, hint: str | None, role: str | None = None) -> str | None:
    if role:
        column = schema.role_column(role)
        if column:
            return column
    if not hint:
        return None
    needle = normalise_name(hint)
    for column in schema.columns:
        if needle == normalise_name(column):
            return column
    for column in schema.columns:
        if needle and needle in normalise_name(column):
            return column
    return None


def resolve_metric(schema: DatasetSchema, hint: str | None) -> tuple[str | None, str | None]:
    """Resolve a metric hint to (role, column) without inventing a column."""
    if not hint:
        return None, None
    role_map = {
        "revenue": "revenue",
        "profit": "profit",
        "quantity": "quantity",
        "orders": "order_id",
        "customers": "customer",
        "salary": "salary",
        "cost": "cost",
        "attendance": "attendance",
        "employees": "employee_id",
        "grade": "grade",
        "discount": "discount",
    }
    role = role_map.get(hint)
    if role:
        column = schema.role_column(role)
        if column:
            return hint, column
    # Fall back to a column whose name contains the hint (e.g. "amount").
    if hint in ("revenue", "profit", "quantity", "salary", "cost", "grade", "discount"):
        column = _match_column(schema, hint)
        if column:
            return hint, column
    if hint == "orders":
        column = schema.role_column("order_id")
        return ("orders", column) if column else (None, None)
    if hint == "customers":
        column = schema.role_column("customer")
        return ("customers", column) if column else (None, None)
    return None, None


def resolve_dimension(schema: DatasetSchema, hint: str | None, text: str = "") -> tuple[str | None, str | None]:
    if not hint:
        return None, None
    role_map = {
        "product": "product", "category": "category", "city": "city", "region": "region",
        "customer": "customer", "department": "department", "store": "store",
        "sales_rep": "sales_rep", "payment_method": "payment_method",
        "employee_name": "employee_name", "course": "course", "gender": "gender",
        "attendance": "attendance",
    }
    role = role_map.get(hint)
    if role:
        column = schema.role_column(role)
        if column:
            return hint, column
    column = _match_column(schema, hint)
    if column:
        return hint, column
    if hint == "month" or "month" in text:
        column = schema.role_column("date")
        if column:
            return "date", column
    return None, None


def _dataset_reference_date(frame: pd.DataFrame | None, schema: DatasetSchema) -> pd.Timestamp:
    if frame is not None:
        for column in schema.dates:
            if column in frame.columns:
                parsed = pd.to_datetime(frame[column], format="mixed", errors="coerce").dropna()
                if not parsed.empty:
                    return parsed.max().normalize()
    return pd.Timestamp.today().normalize()


def parse_period(text: str, reference: pd.Timestamp) -> Period | None:
    """Parse common business periods relative to the dataset's latest date."""
    text = text.lower()
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else reference.year

    quarter = re.search(r"\bq([1-4])\b", text)
    if quarter:
        number = int(quarter.group(1))
        start = pd.Timestamp(year=year, month=(number - 1) * 3 + 1, day=1)
        end = start + pd.offsets.MonthEnd(3)
        return Period(f"Q{number} {year}", start, end)

    month_names = [name for name in MONTHS if re.search(rf"\b{name}\b", text)]
    if month_names:
        first = MONTHS[month_names[0]]
        if len(month_names) >= 2 and ("between" in text or " to " in text or " and " in text):
            last = MONTHS[month_names[-1]]
            start = pd.Timestamp(year=year, month=first, day=1)
            end = pd.Timestamp(year=year, month=last, day=1) + pd.offsets.MonthEnd(1)
        else:
            start = pd.Timestamp(year=year, month=first, day=1)
            end = start + pd.offsets.MonthEnd(1)
        return Period(f"{start:%b %Y}" if start == end.replace(day=1) else f"{start:%b}–{end:%b %Y}", start, end)

    if "this month" in text:
        start = reference.replace(day=1)
        return Period("This month", start, reference)
    if "last month" in text or "previous month" in text:
        end = reference.replace(day=1) - pd.Timedelta(days=1)
        start = end.replace(day=1)
        return Period("Last month", start, end)
    if "this year" in text:
        start = pd.Timestamp(year=reference.year, month=1, day=1)
        return Period("This year", start, reference)
    if "last year" in text or "previous year" in text:
        start = pd.Timestamp(year=reference.year - 1, month=1, day=1)
        end = pd.Timestamp(year=reference.year - 1, month=12, day=31)
        return Period("Last year", start, end)

    days_match = re.search(r"(?:last|past|previous)\s+(\d{1,3})\s+days?", text)
    if days_match:
        days = max(1, min(int(days_match.group(1)), 3650))
        end = reference
        start = end - pd.Timedelta(days=days - 1)
        return Period(f"Last {days} days", start, end)

    if year_match:
        start = pd.Timestamp(year=year, month=1, day=1)
        end = pd.Timestamp(year=year, month=12, day=31)
        return Period(f"Year {year}", start, end)
    return None


def _comparison_period(period: Period) -> Period:
    if period.start is None or period.end is None:
        return period
    days = max(1, (period.end.normalize() - period.start.normalize()).days + 1)
    comparison_end = period.start.normalize() - pd.Timedelta(days=1)
    comparison_start = comparison_end - pd.Timedelta(days=days - 1)
    return Period(
        label=f"{period.label} vs previous {days} days",
        start=period.start,
        end=period.end,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
    )


def parse_question(question: str, schema: DatasetSchema, frame: pd.DataFrame | None = None) -> QueryIntent:
    raw = (question or "").strip()
    text = raw.lower()
    intent = QueryIntent(raw=raw)
    if not text:
        return intent
    reference = _dataset_reference_date(frame, schema)

    # Chart / table modifiers
    intent.wants_chart = _contains(text, CHART_WORDS)
    intent.wants_table = any(word in text for word in ("table", "list", "breakdown", "ranking"))

    # Period (including "between ...")
    intent.period = parse_period(text, reference)

    # Special derived metrics
    if "average order value" in text or re.search(r"\baov\b", text):
        intent.special = "aov"
    elif "profit margin" in text or "margin percentage" in text:
        intent.special = "margin"

    # Metric
    metric_hint = _find_hint(text, METRIC_SYNONYMS)
    # "how much money" / "how many orders" style handling
    if metric_hint is None and "how much" in text:
        metric_hint = "revenue"
    if metric_hint is None and "how many" in text:
        for candidate in ("orders", "customers", "employees", "quantity"):
            if candidate in text:
                metric_hint = candidate
                break
    role, column = resolve_metric(schema, metric_hint)
    intent.metric_role, intent.metric_column = role, column

    # Dimension
    dimension_hint = _find_hint(text, DIMENSION_SYNONYMS)
    if dimension_hint:
        intent.dimension_role, intent.dimension_column = resolve_dimension(schema, dimension_hint, text)
    if ("month" in text or "monthly" in text or "over time" in text or "trend" in text) and schema.has("date"):
        intent.dimension_role, intent.dimension_column = "date", schema.role_column("date")

    # Top N
    top_match = re.search(r"\btop\s+(\d{1,3})\b", text)
    if top_match:
        intent.top_n = max(1, min(int(top_match.group(1)), 100))
    elif _contains(text, TOP_WORDS):
        intent.top_n = 10

    # Aggregation / intent
    if _contains(text, COMPARE_WORDS):
        intent.kind = "compare"
        intent.aggregation = "sum"
        if intent.period:
            intent.period = _comparison_period(intent.period)
    elif any(word in text for word in ("average", "avg", "mean", "per order", "per customer")):
        intent.kind = "average"
        intent.aggregation = "avg"
    elif any(word in text for word in ("how many", "count", "number of", "distinct")):
        intent.kind = "count"
        intent.aggregation = "count"
        if not metric_hint:
            intent.metric_role, intent.metric_column = "records", None
    elif any(word in text for word in ("distribution", "histogram", "spread", "outliers")):
        intent.kind = "distribution"
    elif any(word in text for word in ("explain", "summarise", "summarize", "summary", "performance", "overview", "insights", "what is happening", "how is the business")):
        intent.kind = "explain"
    elif intent.top_n is not None or any(word in text for word in TOP_WORDS):
        intent.kind = "top"
    elif intent.metric_column or intent.wants_chart:
        intent.kind = "total"
    else:
        intent.kind = "unknown"

    if intent.kind == "top" and intent.dimension_column is None:
        # Pick a sensible default dimension that actually exists.
        for candidate in ("product", "category", "region", "city", "customer", "department", "course"):
            column = schema.role_column(candidate)
            if column:
                intent.dimension_role, intent.dimension_column = candidate, column
                break
    if intent.kind == "top" and intent.metric_column is None:
        for candidate in ("revenue", "profit", "cost", "salary", "quantity"):
            column = schema.role_column(candidate)
            if column:
                intent.metric_role, intent.metric_column = candidate, column
                break
    if intent.kind == "compare" and intent.metric_column is None:
        for candidate in ("revenue", "profit", "cost", "salary", "quantity"):
            column = schema.role_column(candidate)
            if column:
                intent.metric_role, intent.metric_column = candidate, column
                break
    if intent.kind == "average" and intent.metric_column is None:
        for candidate in ("revenue", "profit", "salary", "grade", "cost"):
            column = schema.role_column(candidate)
            if column:
                intent.metric_role, intent.metric_column = candidate, column
                break
    if intent.kind == "distribution" and intent.metric_column is None:
        for candidate in ("revenue", "profit", "salary", "grade", "cost"):
            column = schema.role_column(candidate)
            if column:
                intent.metric_role, intent.metric_column = candidate, column
                break

    intent.confidence = 0.85 if intent.kind != "unknown" and intent.metric_column else 0.45
    for alternative in ("total sales", "top products", "profit margin", "sales by month", "average order value"):
        if alternative not in text:
            intent.alternatives.append(alternative)
    return intent
