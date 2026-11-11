"""Verified business chatbot.

Workflow:
1. NLP parses the question into metric / dimension / period / aggregation.
2. pandas computes the result on the currently filtered dataset.
3. The text is composed from those computed values.
4. An optional LLM may add a short narrative, clearly labelled, but it never
   supplies the numbers shown in the verified result.

No arbitrary Python execution, SQL execution or unrestricted database access
is exposed through the chatbot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from retailmind.ai.nlp import Period, QueryIntent, parse_question
from retailmind.ai.provider import AIProvider
from retailmind.models import Component
from retailmind.schema import DatasetSchema
from retailmind.utils import format_number, money, safe_divide, safe_percent


CURRENCY_ROLES = {"revenue", "profit", "cost", "salary", "aov"}


@dataclass
class ChatResponse:
    text: str
    table: pd.DataFrame | None = None
    chart: Component | None = None
    sources: list[str] = field(default_factory=list)
    verified: bool = True
    intent: QueryIntent | None = None
    used_llm: bool = False
    note: str = ""
    followups: list[str] = field(default_factory=list)

    def history_record(self) -> dict[str, Any]:
        return {
            "kind": self.intent.kind if self.intent else "unknown",
            "metric_role": self.intent.metric_role if self.intent else None,
            "metric_column": self.intent.metric_column if self.intent else None,
            "dimension_role": self.intent.dimension_role if self.intent else None,
            "dimension_column": self.intent.dimension_column if self.intent else None,
        }


def _is_currency(role: str | None) -> bool:
    return role in CURRENCY_ROLES


def _format_metric(value: Any, role: str | None, aggregation: str | None = None) -> str:
    if value is None:
        return "N/A"
    if role == "attendance":
        try:
            return safe_percent(float(value))
        except (TypeError, ValueError):
            return str(value)
    if aggregation == "count" and role not in CURRENCY_ROLES:
        return format_number(value)
    if _is_currency(role):
        return money(value)
    return format_number(value)


def _metric_values(frame: pd.DataFrame, schema: DatasetSchema, intent: QueryIntent) -> pd.Series:
    """Return the raw series for a metric, or an empty series when unavailable."""
    role = intent.metric_role
    column = intent.metric_column
    if role == "orders":
        column = schema.role_column("order_id")
        return frame[column] if column and column in frame.columns else pd.Series(dtype="object")
    if role == "customers":
        column = schema.role_column("customer")
        return frame[column] if column and column in frame.columns else pd.Series(dtype="object")
    if role == "employees":
        column = schema.role_column("employee_id") or schema.role_column("employee_name")
        return frame[column] if column and column in frame.columns else pd.Series(dtype="object")
    if role == "attendance":
        column = schema.role_column("attendance")
        return frame[column] if column and column in frame.columns else pd.Series(dtype="object")
    if column and column in frame.columns:
        return frame[column]
    return pd.Series(dtype="float64")


def _aggregate(frame: pd.DataFrame, schema: DatasetSchema, intent: QueryIntent) -> float | None:
    role = intent.metric_role
    values = _metric_values(frame, schema, intent)
    if values.empty:
        return None
    if role in ("orders", "customers", "employees"):
        return float(values.nunique(dropna=True))
    if role == "attendance":
        text = values.dropna().astype("string").str.strip().str.lower()
        if text.empty:
            return None
        truthy = {"present", "yes", "y", "true", "1", "p", "attended"}
        falsy = {"absent", "no", "n", "false", "0", "a", "missed"}
        recognised = text[text.isin(truthy | falsy)]
        return float(recognised.isin(truthy).mean()) if not recognised.empty else None
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    if intent.aggregation == "count":
        return float(values.notna().sum())
    if intent.aggregation == "avg":
        return float(numeric.mean())
    if intent.aggregation == "min":
        return float(numeric.min())
    if intent.aggregation == "max":
        return float(numeric.max())
    return float(numeric.sum())


def _metric_label(schema: DatasetSchema, intent: QueryIntent) -> str:
    role = intent.metric_role
    if role == "orders":
        return "Orders"
    if role == "customers":
        return "Customers"
    if role == "employees":
        return "Employees"
    if role == "attendance":
        return "Attendance rate"
    if role == "revenue":
        return "Sales" if schema.domain in ("retail", "commerce") else "Revenue"
    if role == "profit":
        return "Profit"
    if role == "cost":
        return "Expenses"
    if role == "salary":
        return "Salary"
    if intent.metric_column:
        return schema.label_for(intent.metric_column)
    return "Value"


def _filter_period(frame: pd.DataFrame, schema: DatasetSchema, period: tuple[pd.Timestamp, pd.Timestamp] | None) -> pd.DataFrame:
    date_column = schema.role_column("date")
    if not date_column or date_column not in frame.columns or period is None:
        return frame
    start, end = period
    dates = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
    mask = dates.between(start, end + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1))
    return frame.loc[mask].copy()


def _top_table(frame: pd.DataFrame, schema: DatasetSchema, intent: QueryIntent) -> pd.DataFrame:
    dimension = intent.dimension_column
    if not dimension or dimension not in frame.columns:
        return pd.DataFrame()
    working = frame.copy()
    working[dimension] = working[dimension].astype("string").fillna("(missing)")
    role = intent.metric_role
    if role in ("orders", "customers", "employees"):
        metric_column = schema.role_column("order_id") if role == "orders" else schema.role_column("customer")
        if role == "employees":
            metric_column = schema.role_column("employee_id") or schema.role_column("employee_name")
        if metric_column and metric_column in working.columns:
            table = working.groupby(dimension, dropna=False)[metric_column].nunique().reset_index(name="value")
        else:
            table = working.groupby(dimension, dropna=False).size().reset_index(name="value")
    elif role == "attendance":
        attendance = schema.role_column("attendance")
        if not attendance or attendance not in working.columns:
            return pd.DataFrame()
        text = working[attendance].astype("string").str.strip().str.lower()
        working["_present"] = text.isin({"present", "yes", "y", "true", "1", "p", "attended"}).astype(float)
        working.loc[text.isna(), "_present"] = pd.NA
        table = working.groupby(dimension, dropna=False)["_present"].mean().reset_index(name="value")
    else:
        column = intent.metric_column
        if not column or column not in working.columns:
            table = working.groupby(dimension, dropna=False).size().reset_index(name="value")
        elif intent.aggregation == "count":
            table = working.groupby(dimension, dropna=False)[column].count().reset_index(name="value")
        else:
            working["_value"] = pd.to_numeric(working[column], errors="coerce")
            how = "mean" if intent.aggregation == "avg" else ("min" if intent.aggregation == "min" else ("max" if intent.aggregation == "max" else "sum"))
            table = getattr(working.groupby(dimension, dropna=False)["_value"], how)().reset_index(name="value")
    table = table.dropna(subset=["value"]).sort_values("value", ascending=False, kind="stable")
    if intent.top_n:
        table = table.head(intent.top_n)
    table = table.rename(columns={dimension: schema.label_for(dimension), "value": _metric_label(schema, intent)})
    return table.reset_index(drop=True)


def _chart_for(intent: QueryIntent, schema: DatasetSchema) -> Component | None:
    if not intent.dimension_column:
        return None
    measure = intent.metric_column
    if intent.metric_role in ("orders", "customers", "employees", "attendance") and not measure:
        return None
    label = _metric_label(schema, intent)
    chart_type = "bar"
    if intent.dimension_role == "date":
        chart_type = "line"
    return Component(
        type=chart_type,
        title=f"{label} by {schema.label_for(intent.dimension_column)}",
        dimension=intent.dimension_column,
        measure=measure,
        aggregation="count" if intent.metric_role in ("orders", "customers", "employees", "attendance") and not measure else intent.aggregation,
        top_n=intent.top_n or 10,
        height=340,
    )


def _compare_response(frame: pd.DataFrame, schema: DatasetSchema, intent: QueryIntent) -> ChatResponse:
    date_column = schema.role_column("date")
    if not date_column:
        return ChatResponse("A date column is required to compare periods.", intent=intent, followups=["Which product has the highest revenue?"])
    period = intent.period
    if period is None or period.start is None or period.end is None:
        reference = pd.to_datetime(frame[date_column], format="mixed", errors="coerce").dropna()
        reference_date = reference.max().normalize() if not reference.empty else pd.Timestamp.today().normalize()
        start = reference_date - pd.Timedelta(days=29)
        period = Period("Last 30 days", start, reference_date, start - pd.Timedelta(days=30), start - pd.Timedelta(days=1))
    current = _aggregate(_filter_period(frame, schema, period.current()), schema, intent)
    previous = _aggregate(_filter_period(frame, schema, period.previous()), schema, intent)
    if current is None and previous is None:
        return ChatResponse("The selected metric has no usable values for those periods.", intent=intent)
    change = safe_divide((current or 0) - (previous or 0), abs(previous)) if previous else None
    direction = "increased" if (change or 0) >= 0 else "decreased"
    label = _metric_label(schema, intent)
    text = f"{label} for {period.label.split(' vs ')[0]}: {_format_metric(current, intent.metric_role, intent.aggregation)}."
    if previous is not None:
        text += f" Previous period: {_format_metric(previous, intent.metric_role, intent.aggregation)}."
    if change is not None:
        text += f" Change: {direction} by {safe_percent(abs(change))}."
    table = pd.DataFrame(
        [
            {"Period": period.label.split(" vs ")[0], label: current},
            {"Period": "Comparison period", label: previous},
        ]
    )
    if change is not None:
        table.loc[len(table)] = {"Period": "Change", label: safe_percent(change)}
    return ChatResponse(text, table=table, intent=intent, verified=True, followups=["Show the trend by month", "Which category performs best?"])


def _explain_response(frame: pd.DataFrame, schema: DatasetSchema, intent: QueryIntent, provider: AIProvider | None) -> ChatResponse:
    from retailmind.ai.insights import generate_insights

    insights = generate_insights(frame, schema, max_items=6)
    if not insights:
        return ChatResponse("The active dataset does not contain enough variation for a reliable explanation.", intent=intent)
    lines = [f"{index}. {insight.title}: {insight.text}" for index, insight in enumerate(insights, start=1)]
    text = "\n".join(lines)
    table = pd.DataFrame(
        [{"Insight": insight.title, "Evidence": insight.evidence_text()} for insight in insights]
    )
    used_llm = False
    note = ""
    if provider is not None and provider.available:
        facts = "\n".join(f"- {insight.title}: {insight.text}" for insight in insights)
        try:
            narrative = provider.chat(
                [
                    {"role": "system", "content": "You are a business analyst. Write a short, factual summary using ONLY the provided verified facts. Do not invent numbers, causes or recommendations that are not supported by the facts."},
                    {"role": "user", "content": f"Verified facts:\n{facts}\n\nWrite 3 short sentences for a business owner."},
                ],
                temperature=0.2,
                max_tokens=260,
            )
            note = f"\n\n**AI narrative (verified facts above):** {narrative}"
            used_llm = True
        except Exception:
            note = "\n\n_AI narrative unavailable; verified insights are shown above._"
    return ChatResponse(text + note, table=table, intent=intent, used_llm=used_llm, verified=True, followups=["Which product has the highest revenue?", "Show sales by month"])


def _summary_requested(question: str, intent: QueryIntent) -> bool:
    if intent.kind in {"top", "compare", "distribution"}:
        return False
    text = question.lower()
    explicit_summary = any(term in text for term in ("summary", "overview", "performance snapshot", "key metrics", "business performance"))
    if intent.kind == "explain" and not explicit_summary:
        return False
    metrics = sum(term in text for term in ("sales", "revenue", "profit", "margin", "order", "record", "customer"))
    return metrics >= 2 or explicit_summary


def _summary_response(frame: pd.DataFrame, schema: DatasetSchema, intent: QueryIntent) -> ChatResponse:
    """Answer multi-metric summary questions with verified pandas figures."""
    scoped = _filter_period(frame, schema, intent.period.current() if intent.period else None)
    revenue_column = schema.role_column("revenue")
    profit_column = schema.role_column("profit")
    order_column = schema.role_column("order_id")
    category_column = schema.role_column("category")
    product_column = schema.role_column("product")

    revenue = pd.to_numeric(scoped[revenue_column], errors="coerce").sum() if revenue_column else None
    profit = pd.to_numeric(scoped[profit_column], errors="coerce").sum() if profit_column else None
    margin = safe_divide(profit, revenue) if revenue and profit is not None else None
    order_count = int(scoped[order_column].nunique(dropna=True)) if order_column else None

    lines = ["**Business Performance Summary**", ""]
    index = 1
    if revenue is not None:
        lines.append(f"{index}. **Total Revenue:** {money(float(revenue))}")
        index += 1
    if profit is not None:
        lines.append(f"{index}. **Total Profit:** {money(float(profit))}")
        index += 1
    if margin is not None:
        lines.append(f"{index}. **Profit Margin:** {safe_percent(margin)}")
        index += 1
    if order_count is not None:
        lines.append(f"{index}. **Total Orders:** {order_count:,}")
        index += 1
    lines.append(f"{index}. **Total Records:** {len(scoped):,}")

    insights: list[str] = []
    for label, column in (("category", category_column), ("product", product_column)):
        if not column or column not in scoped.columns or not revenue_column:
            continue
        working = scoped[[column, revenue_column]].copy()
        working[revenue_column] = pd.to_numeric(working[revenue_column], errors="coerce")
        grouped = working.dropna(subset=[revenue_column]).groupby(working[column].astype("string"))[revenue_column].sum().sort_values(ascending=False)
        if not grouped.empty:
            insights.append(f"Top {label} by revenue: **{grouped.index[0]}** ({money(float(grouped.iloc[0]))}).")

    if category_column and category_column in scoped.columns and revenue_column and profit_column:
        working = scoped[[category_column, revenue_column, profit_column]].copy()
        working[revenue_column] = pd.to_numeric(working[revenue_column], errors="coerce")
        working[profit_column] = pd.to_numeric(working[profit_column], errors="coerce")
        grouped = working.dropna().groupby(working[category_column].astype("string"))[[revenue_column, profit_column]].sum()
        grouped = grouped[grouped[revenue_column] > 0]
        if not grouped.empty:
            grouped["margin"] = grouped[profit_column] / grouped[revenue_column]
            weakest = grouped.sort_values("margin").iloc[0]
            insights.append(f"Lowest-margin category: **{grouped.sort_values('margin').index[0]}** ({safe_percent(float(weakest['margin']))}) — review pricing and discounts.")

    if insights:
        lines.extend(["", "**Key Insights**"])
        lines.extend(f"- {insight}" for insight in insights)
    lines.extend([
        "",
        "**Recommended Actions**",
        "- Protect revenue concentration by reviewing performance in your top categories.",
        "- Investigate low-margin groups before increasing discounts or promotions.",
    ])
    return ChatResponse(
        "\n".join(lines),
        intent=intent,
        followups=["Show revenue by month", "Which category has the best margin?", "Who are the top customers?"],
    )


def answer_question(
    question: str,
    frame: pd.DataFrame,
    schema: DatasetSchema,
    history: list[dict[str, Any]] | None = None,
    provider: AIProvider | None = None,
) -> ChatResponse:
    """Answer a business question using verified pandas calculations."""
    intent = parse_question(question, schema, frame)
    history = history or []

    # Follow-up context: inherit a metric/dimension when the question omits it.
    referential = any(token in question.lower() for token in (" it ", " that ", " those ", " them ", " same ", " this "))
    last = history[-1] if history else {}
    if intent.metric_column is None and last.get("metric_column") in schema.columns:
        intent.metric_column = last.get("metric_column")
        intent.metric_role = last.get("metric_role")
        if intent.kind == "unknown":
            intent.kind = "total"
    if referential and intent.dimension_column is None and last.get("dimension_column") in schema.columns:
        intent.dimension_column = last.get("dimension_column")
        intent.dimension_role = last.get("dimension_role")

    if _summary_requested(question, intent):
        return _summary_response(frame, schema, intent)

    if intent.kind == "unknown":
        suggestions = suggested_questions(schema)
        return ChatResponse(
            "I can answer questions about totals, averages, top performers and period comparisons using the uploaded dataset. "
            "I will never invent a number. Try one of these:",
            intent=intent,
            followups=suggestions,
        )

    if intent.kind == "explain":
        return _explain_response(frame, schema, intent, provider)

    if intent.special == "aov":
        revenue_column = schema.role_column("revenue")
        order_column = schema.role_column("order_id")
        if not revenue_column or not order_column:
            return ChatResponse("Average order value requires both a revenue column and an order identifier.", intent=intent)
        scoped = _filter_period(frame, schema, intent.period.current() if intent.period else None)
        revenue = pd.to_numeric(scoped[revenue_column], errors="coerce").sum()
        orders = scoped[order_column].nunique(dropna=True)
        value = safe_divide(revenue, orders)
        if value is None:
            return ChatResponse("No orders are available for the active filters.", intent=intent)
        return ChatResponse(
            f"The average order value is {money(value)} across {orders:,} distinct orders for the active filters.",
            intent=intent,
            followups=["What is the total revenue?", "Show revenue by month"],
        )

    if intent.special == "margin":
        revenue_column = schema.role_column("revenue")
        profit_column = schema.role_column("profit")
        if not revenue_column or not profit_column:
            return ChatResponse("Profit margin requires both a revenue column and a profit column.", intent=intent)
        scoped = _filter_period(frame, schema, intent.period.current() if intent.period else None)
        revenue = pd.to_numeric(scoped[revenue_column], errors="coerce").sum()
        profit = pd.to_numeric(scoped[profit_column], errors="coerce").sum()
        value = safe_divide(profit, revenue)
        if value is None:
            return ChatResponse("Revenue is zero, so a margin cannot be computed.", intent=intent)
        return ChatResponse(
            f"The profit margin is {safe_percent(value)} (profit {money(profit)} on revenue {money(revenue)}) for the active filters.",
            intent=intent,
            followups=["What is the total profit?", "Which category has the best margin?"],
        )

    if intent.kind == "distribution":
        if not intent.metric_column:
            return ChatResponse("I could not identify a numeric measure for the distribution.", intent=intent)
        values = pd.to_numeric(frame[intent.metric_column], errors="coerce").dropna()
        if values.empty:
            return ChatResponse(f"{schema.label_for(intent.metric_column)} has no numeric values in the active data.", intent=intent)
        summary = pd.DataFrame(
            [
                {"Statistic": "Count", "Value": len(values)},
                {"Statistic": "Mean", "Value": values.mean()},
                {"Statistic": "Minimum", "Value": values.min()},
                {"Statistic": "Maximum", "Value": values.max()},
            ]
        )
        chart = Component(type="histogram", title=f"Distribution of {schema.label_for(intent.metric_column)}", measure=intent.metric_column, height=340)
        return ChatResponse(
            f"{schema.label_for(intent.metric_column)} ranges from {format_number(values.min())} to {format_number(values.max())}, with a mean of {format_number(values.mean())} across {len(values):,} records.",
            table=summary,
            chart=chart,
            intent=intent,
        )

    if intent.kind == "compare":
        return _compare_response(frame, schema, intent)

    if intent.kind == "top":
        table = _top_table(frame, schema, intent)
        if table.empty:
            return ChatResponse("I could not build that ranking with the available columns.", intent=intent)
        dimension_label = schema.label_for(intent.dimension_column)
        metric_label = _metric_label(schema, intent)
        top_value = table.iloc[0]
        text = f"Top {len(table)} {dimension_label.lower()} by {metric_label.lower()}: {top_value[dimension_label]} leads with {_format_metric(top_value[metric_label], intent.metric_role, intent.aggregation)}."
        chart = _chart_for(intent, schema)
        return ChatResponse(text, table=table, chart=chart, intent=intent, followups=["Show this as a chart", "Compare with the previous period"])

    # total / average / count
    if intent.metric_column is None and intent.metric_role not in ("records",):
        return ChatResponse(
            "I could not match that metric to an uploaded column. Use the Data Fields panel to confirm the mapping.",
            intent=intent,
            followups=suggested_questions(schema),
        )
    scoped = _filter_period(frame, schema, intent.period.current() if intent.period else None)
    if intent.metric_role == "records":
        value: float | None = float(len(scoped))
    else:
        value = _aggregate(scoped, schema, intent)
    if value is None:
        return ChatResponse("That metric has no usable values in the active data.", intent=intent)
    label = _metric_label(schema, intent)
    qualifier = "average" if intent.aggregation == "avg" else ("count" if intent.aggregation == "count" else "total")
    period_label = f" for {intent.period.label}" if intent.period else " for the active filters"
    text = f"The {qualifier} {label.lower()}{period_label} is {_format_metric(value, intent.metric_role, intent.aggregation)}."
    if intent.metric_role == "attendance":
        text = f"Attendance rate{period_label} is {_format_metric(value, intent.metric_role)}."
    return ChatResponse(
        text,
        intent=intent,
        followups=[
            f"Show {label.lower()} by month",
            f"Which {schema.label_for(schema.role_column('product')) or 'category'} performs best?",
            "Compare with the previous period",
        ],
    )


def suggested_questions(schema: DatasetSchema) -> list[str]:
    questions: list[str] = ["What is the total revenue?" if schema.has("revenue") else "How many records are in the dataset?"]
    if schema.has("profit"):
        questions.append("What is the total profit?")
    if schema.has("product"):
        questions.append("Which product has the highest revenue?")
    if schema.has("category"):
        questions.append("Which category performs best?")
    if schema.has("date") and schema.has("revenue"):
        questions.append("Compare sales with the previous period")
        questions.append("Show sales by month")
    if schema.has("customer"):
        questions.append("Who are the top 10 customers?")
    if schema.has("salary"):
        questions.append("What is the average salary?")
    return questions[:6]
