"""Rendering layer for dashboard components.

Every number shown here is computed from the uploaded DataFrame at render
time.  No synthetic/fake data is generated.
"""

from __future__ import annotations

import html
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from retailmind.config import PALETTES
from retailmind.models import Component, Page, Theme
from retailmind.schema import DatasetSchema, profile_report
from retailmind.utils import format_number, money, safe_divide, safe_percent


def _palette(theme: Theme) -> list[str]:
    if theme.palette:
        return theme.palette
    return PALETTES.get(theme.preset, PALETTES["dark"])


def _label(schema: DatasetSchema, column: str | None) -> str:
    if not column:
        return ""
    return schema.label_for(column)


def _numeric(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if not column or column not in frame.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _aggregate_series(values: pd.Series, aggregation: str) -> float | None:
    aggregation = (aggregation or "sum").lower()
    numeric = pd.to_numeric(values, errors="coerce")
    if aggregation == "count":
        return float(values.notna().sum())
    valid = numeric.dropna()
    if valid.empty:
        return None
    if aggregation == "avg":
        return float(valid.mean())
    if aggregation == "min":
        return float(valid.min())
    if aggregation == "max":
        return float(valid.max())
    return float(valid.sum())


def aggregate_frame(
    frame: pd.DataFrame,
    dimension: str | None,
    measure: str | None,
    aggregation: str = "sum",
    top_n: int = 10,
    sort: str = "desc",
) -> pd.DataFrame:
    """Group a frame into ``[label, value]`` using only real values."""
    if frame.empty:
        return pd.DataFrame(columns=["label", "value"])
    if not dimension or dimension not in frame.columns:
        if not measure or measure not in frame.columns:
            return pd.DataFrame(columns=["label", "value"])
        values = _numeric(frame, measure).dropna()
        if values.empty:
            return pd.DataFrame(columns=["label", "value"])
        value = _aggregate_series(values, aggregation)
        return pd.DataFrame({"label": [_label(DatasetSchema([], {}, [], [], [], [], []), measure) or measure], "value": [value]})

    working = frame[[dimension] + ([measure] if measure and measure in frame.columns else [])].copy()
    working[dimension] = working[dimension].astype("string").fillna("(missing)")
    if aggregation == "count" or not measure or measure not in working.columns:
        grouped = working.groupby(dimension, dropna=False).size().reset_index(name="value")
    else:
        working["_value"] = pd.to_numeric(working[measure], errors="coerce")
        if aggregation == "avg":
            grouped = working.groupby(dimension, dropna=False)["_value"].mean().reset_index(name="value")
        elif aggregation == "min":
            grouped = working.groupby(dimension, dropna=False)["_value"].min().reset_index(name="value")
        elif aggregation == "max":
            grouped = working.groupby(dimension, dropna=False)["_value"].max().reset_index(name="value")
        else:
            grouped = working.groupby(dimension, dropna=False)["_value"].sum().reset_index(name="value")
    grouped = grouped.rename(columns={dimension: "label"}).dropna(subset=["value"])
    ascending = sort == "asc"
    grouped = grouped.sort_values("value", ascending=ascending, kind="stable")
    if top_n and len(grouped) > top_n:
        grouped = grouped.head(top_n)
    return grouped.reset_index(drop=True)


def _time_frame(frame: pd.DataFrame, dimension: str, measure: str, aggregation: str) -> pd.DataFrame:
    if dimension not in frame.columns or measure not in frame.columns:
        return pd.DataFrame(columns=["label", "value"])
    dates = pd.to_datetime(frame[dimension], format="mixed", errors="coerce")
    working = pd.DataFrame({"date": dates, "value": pd.to_numeric(frame[measure], errors="coerce")}).dropna()
    if working.empty:
        return pd.DataFrame(columns=["label", "value"])
    working["label"] = working["date"].dt.to_period("M").dt.to_timestamp()
    grouped = working.groupby("label", dropna=False)["value"]
    if aggregation == "avg":
        series = grouped.mean()
    elif aggregation == "min":
        series = grouped.min()
    elif aggregation == "max":
        series = grouped.max()
    elif aggregation == "count":
        series = grouped.count()
    else:
        series = grouped.sum()
    return series.reset_index(name="value").sort_values("label")


def _chart_base(theme: Theme, height: int) -> dict[str, Any]:
    return {
        "height": height,
        "background": "transparent",
        "config": {
            "axis": {"labelColor": "#94a3b8" if theme.preset in ("dark", "midnight") else "#475569", "titleColor": "#cbd5e1" if theme.preset in ("dark", "midnight") else "#334155"},
            "legend": {"labelColor": "#cbd5e1" if theme.preset in ("dark", "midnight") else "#334155"},
            "view": {"stroke": "transparent"},
        },
    }


def _render_chart(frame: pd.DataFrame, component: Component, schema: DatasetSchema, theme: Theme, height: int) -> None:
    palette = _palette(theme)
    accent = component.color or palette[0]
    base = _chart_base(theme, height)
    dimension = component.dimension
    measure = component.measure

    if component.type == "histogram":
        if not measure or measure not in frame.columns:
            st.info("This histogram needs a numeric measure.")
            return
        values = _numeric(frame, measure).dropna()
        if values.empty:
            st.info("No numeric values are available for this histogram.")
            return
        chart = alt.Chart(pd.DataFrame({measure: values})).mark_bar(color=accent, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X(f"{measure}:Q", bin=alt.Bin(maxbins=24), title=_label(schema, measure)),
            y=alt.Y("count():Q", title="Records"),
            tooltip=[alt.Tooltip(f"{measure}:Q", title=_label(schema, measure), format=",.2f"), alt.Tooltip("count():Q", title="Records")],
        )
        st.altair_chart(chart.properties(**base), width="stretch")
        return

    if component.type == "scatter":
        x_column = measure
        y_column = component.measure_y
        if not x_column or not y_column or x_column not in frame.columns or y_column not in frame.columns:
            if x_column and x_column in frame.columns:
                histogram = Component(type="histogram", measure=x_column, title=component.title)
                _render_chart(frame, histogram, schema, theme, height)
            else:
                st.info("This scatter plot needs two numeric measures.")
            return
        data = frame[[x_column, y_column] + ([dimension] if dimension and dimension in frame.columns else [])].copy()
        data[x_column] = pd.to_numeric(data[x_column], errors="coerce")
        data[y_column] = pd.to_numeric(data[y_column], errors="coerce")
        data = data.dropna(subset=[x_column, y_column])
        if data.empty:
            st.info("No complete pairs of numeric values are available.")
            return
        encoding: dict[str, Any] = {
            "x": alt.X(f"{x_column}:Q", title=_label(schema, x_column)),
            "y": alt.Y(f"{y_column}:Q", title=_label(schema, y_column)),
            "tooltip": [alt.Tooltip(f"{x_column}:Q", format=",.2f"), alt.Tooltip(f"{y_column}:Q", format=",.2f")],
        }
        if dimension and dimension in data.columns:
            encoding["color"] = alt.Color(f"{dimension}:N", title=_label(schema, dimension), scale=alt.Scale(range=palette))
            encoding["tooltip"].append(alt.Tooltip(f"{dimension}:N", title=_label(schema, dimension)))
        chart = alt.Chart(data).mark_circle(size=55, opacity=0.75, color=accent).encode(**encoding)
        st.altair_chart(chart.properties(**base), width="stretch")
        return

    if component.type == "table" or component.type == "matrix":
        _render_table(frame, component, schema)
        return

    if component.type in ("line", "area") and dimension and dimension in frame.columns:
        data = _time_frame(frame, dimension, measure or "", component.aggregation)
        if data.empty:
            st.info("The selected date column has no valid dates for this trend.")
            return
        chart_type = alt.Chart(data)
        if component.type == "area":
            chart = chart_type.mark_area(color=accent, opacity=0.35, line={"color": accent}).encode(
                x=alt.X("label:T", title=_label(schema, dimension)),
                y=alt.Y("value:Q", title=_label(schema, measure)),
                tooltip=[alt.Tooltip("label:T", title="Period", format="%b %Y"), alt.Tooltip("value:Q", title=_label(schema, measure), format=",.2f")],
            )
        else:
            chart = chart_type.mark_line(color=accent, strokeWidth=2.4, point=alt.OverlayMarkDef(size=45)).encode(
                x=alt.X("label:T", title=_label(schema, dimension)),
                y=alt.Y("value:Q", title=_label(schema, measure)),
                tooltip=[alt.Tooltip("label:T", title="Period", format="%b %Y"), alt.Tooltip("value:Q", title=_label(schema, measure), format=",.2f")],
            )
        st.altair_chart(chart.properties(**base), width="stretch")
        return

    data = aggregate_frame(frame, dimension, measure, component.aggregation, component.top_n, component.sort)
    if data.empty:
        st.info("No values are available for this visual with the selected fields.")
        return

    if component.type in ("pie", "donut"):
        pie_palette = [accent, *[color for color in palette if color != accent]]
        chart = alt.Chart(data).mark_arc(innerRadius=45 if component.type == "donut" else 0, outerRadius=110).encode(
            theta=alt.Theta("value:Q", title=_label(schema, measure)),
            color=alt.Color("label:N", title=_label(schema, dimension), scale=alt.Scale(range=pie_palette)),
            tooltip=[alt.Tooltip("label:N", title=_label(schema, dimension)), alt.Tooltip("value:Q", title=_label(schema, measure), format=",.2f")],
        )
        st.altair_chart(chart.properties(**base), width="stretch")
        return

    if component.type == "bar" or not dimension:
        chart = alt.Chart(data).mark_bar(color=accent, cornerRadiusEnd=4).encode(
            y=alt.Y("label:N", sort="-x", title=_label(schema, dimension)),
            x=alt.X("value:Q", title=_label(schema, measure) if measure else "Records"),
            tooltip=[alt.Tooltip("label:N", title=_label(schema, dimension)), alt.Tooltip("value:Q", title=_label(schema, measure) if measure else "Records", format=",.2f")],
        )
        st.altair_chart(chart.properties(**base), width="stretch")
        return

    # Fallback for an unknown type.
    chart = alt.Chart(data).mark_bar(color=accent).encode(
        x=alt.X("label:N", sort="-y", title=_label(schema, dimension)),
        y=alt.Y("value:Q", title=_label(schema, measure) if measure else "Value"),
        tooltip=[alt.Tooltip("label:N"), alt.Tooltip("value:Q", format=",.2f")],
    )
    st.altair_chart(chart.properties(**base), width="stretch")


def _normalise_aggregation(aggregation: str | None) -> str:
    value = (aggregation or "sum").strip().lower()
    return {"avg": "mean", "average": "mean"}.get(value, value)


def table_frame(frame: pd.DataFrame, component: Component, schema: DatasetSchema) -> pd.DataFrame:
    """Build the grouped table for a ``table``/``matrix`` component.

    Missing numeric values stay missing when *every* value in a group is
    absent (``sum(min_count=1)``), so an empty group is never shown as a
    fabricated zero.  This helper is deliberately pure so the aggregation
    logic can be unit tested without a Streamlit runtime.
    """
    dimension = component.dimension
    measure = component.measure
    if not dimension or dimension not in frame.columns:
        return frame.head(200)

    working = frame.copy()
    working[dimension] = working[dimension].astype("string").fillna("(missing)")

    # (display label, temporary source column, pandas aggregation)
    specs: list[tuple[str, str, str]] = []
    used_labels: set[str] = set()

    if measure and measure in working.columns:
        working["_measure"] = pd.to_numeric(working[measure], errors="coerce")
        label = schema.label_for(measure)
        if component.type == "matrix":
            specs.append((f"{label} (Sum)", "_measure", "sum"))
            specs.append((f"{label} (Mean)", "_measure", "mean"))
            used_labels.update({label, f"{label} (Sum)", f"{label} (Mean)"})
        else:
            aggregation = _normalise_aggregation(component.aggregation)
            display = label if aggregation == "sum" else f"{label} ({aggregation.title()})"
            specs.append((display, "_measure", aggregation))
            used_labels.add(display)

    for extra_role in ("profit", "quantity"):
        extra = schema.roles.get(extra_role)
        if extra and extra in working.columns and extra != measure:
            working[f"_{extra_role}"] = pd.to_numeric(working[extra], errors="coerce")
            label = schema.label_for(extra)
            if label in used_labels:
                label = f"{label} ({extra_role.title()})"
            specs.append((label, f"_{extra_role}", "sum"))
            used_labels.add(label)

    if not specs:
        table = working.groupby(dimension, dropna=False).size().reset_index(name="Records")
    else:
        grouped: list[pd.Series] = []
        for display, source, aggregation in specs:
            series = working.groupby(dimension, dropna=False)[source]
            if aggregation == "mean":
                values = series.mean()
            elif aggregation == "min":
                values = series.min()
            elif aggregation == "max":
                values = series.max()
            elif aggregation == "count":
                values = series.count()
            else:
                values = series.sum(min_count=1)
            grouped.append(values.rename(display))
        table = pd.concat(grouped, axis=1).reset_index()
        table = table.rename(columns={dimension: _label(schema, dimension)})

    sort_column = next((column for column in table.columns if column != _label(schema, dimension)), None)
    if sort_column:
        table = table.sort_values(sort_column, ascending=False, kind="stable")
    return table.head(200)


def _render_table(frame: pd.DataFrame, component: Component, schema: DatasetSchema) -> None:
    dimension = component.dimension
    if not dimension or dimension not in frame.columns:
        st.dataframe(frame.head(200), width="stretch", hide_index=True)
        return
    st.dataframe(table_frame(frame, component, schema), width="stretch", hide_index=True)


def _attendance_rate(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns:
        return None
    values = frame[column].dropna().astype("string").str.strip().str.lower()
    if values.empty:
        return None
    truthy = {"present", "yes", "y", "true", "1", "p", "attended", "in office", "in-office"}
    falsy = {"absent", "no", "n", "false", "0", "a", "missed", "leave"}
    recognised = values.isin(truthy | falsy)
    if not recognised.any():
        return None
    subset = values[recognised]
    return float(subset.isin(truthy).mean())


def _growth_value(frame: pd.DataFrame, schema: DatasetSchema) -> tuple[float | None, str | None]:
    date_column = schema.role_column("date")
    revenue = schema.role_column("revenue")
    if not date_column or not revenue:
        return None, None
    dates = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
    values = pd.to_numeric(frame[revenue], errors="coerce")
    working = pd.DataFrame({"date": dates, "value": values}).dropna()
    if working.empty:
        return None, None
    working = working.sort_values("date")
    start, end = working["date"].min(), working["date"].max()
    span_days = max(1, (end.normalize() - start.normalize()).days + 1)
    if span_days >= 60:
        period = pd.Timedelta(days=30)
    else:
        period = pd.Timedelta(days=max(1, span_days // 2))
    current = working[working["date"] > (end - period)]["value"].sum()
    previous = working[(working["date"] > (end - 2 * period)) & (working["date"] <= (end - period))]["value"].sum()
    growth = safe_divide(current - previous, abs(previous)) if previous else None
    label = f"vs previous {period.days} days"
    return growth, label


def render_kpi(frame: pd.DataFrame, component: Component, schema: DatasetSchema) -> tuple[str, str | None]:
    role = component.kpi_role or ""
    value: Any = None
    delta: str | None = None
    fmt = component.format

    if role == "records":
        value = len(frame)
    elif role == "revenue":
        value = _numeric(frame, schema.role_column("revenue")).sum()
    elif role == "profit":
        value = _numeric(frame, schema.role_column("profit")).sum()
    elif role == "margin":
        value = safe_divide(_numeric(frame, schema.role_column("profit")).sum(), _numeric(frame, schema.role_column("revenue")).sum())
    elif role == "quantity":
        value = _numeric(frame, schema.role_column("quantity")).sum()
    elif role == "orders":
        column = schema.role_column("order_id")
        value = frame[column].nunique(dropna=True) if column else None
    elif role == "customers":
        column = schema.role_column("customer")
        value = frame[column].nunique(dropna=True) if column else None
    elif role == "aov":
        revenue = _numeric(frame, schema.role_column("revenue")).sum()
        orders = schema.role_column("order_id")
        count = frame[orders].nunique(dropna=True) if orders else 0
        value = safe_divide(revenue, count)
    elif role == "salary":
        value = _numeric(frame, schema.role_column("salary")).sum()
    elif role == "avg_salary":
        series = _numeric(frame, schema.role_column("salary")).dropna()
        value = float(series.mean()) if not series.empty else None
    elif role == "employees":
        column = schema.role_column("employee_id") or schema.role_column("employee_name")
        value = frame[column].nunique(dropna=True) if column else None
    elif role == "cost":
        value = _numeric(frame, schema.role_column("cost")).sum()
    elif role == "attendance_rate":
        value = _attendance_rate(frame, schema.role_column("attendance") or "")
        fmt = "percent"
    elif role == "growth":
        value, delta_label = _growth_value(frame, schema)
        fmt = "percent"
        delta = delta_label
    else:
        column = component.measure
        if column and column in frame.columns:
            value = _aggregate_series(frame[column], component.aggregation)

    numeric_value: float | None
    try:
        numeric_value = float(value)  # numpy scalars are not Python int/float
    except (TypeError, ValueError):
        numeric_value = None
    if fmt == "currency":
        display = money(numeric_value)
    elif fmt == "percent":
        display = safe_percent(numeric_value)
    else:
        display = format_number(numeric_value if numeric_value is not None else value)
    return display, delta


def render_insights(frame: pd.DataFrame, schema: DatasetSchema, key: str) -> None:
    from retailmind.ai.insights import generate_insights

    insights = generate_insights(frame, schema)
    if not insights:
        st.info("Not enough data is available to generate verified insights.")
        return
    for insight in insights:
        severity = insight.severity
        icon = {"positive": "🟢", "warning": "🟠", "negative": "🔴", "info": "🔵"}.get(severity, "🔵")
        st.markdown(
            f"<div class='rm-insight rm-insight-{severity}'>"
            f"<div class='rm-insight-title'>{icon} {html.escape(insight.title)}</div>"
            f"<div class='rm-insight-text'>{html.escape(insight.text)}</div>"
            f"<div class='rm-insight-evidence'>{html.escape(insight.evidence_text())}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def render_profile_table(frame: pd.DataFrame, schema: DatasetSchema) -> None:
    report = profile_report(frame, schema)
    rows = [
        ("Total records", f"{report['total_records']:,}"),
        ("Total columns", f"{report['total_columns']:,}"),
        ("Missing values", f"{report['missing_total']:,}"),
        ("Duplicate records", f"{report['duplicate_records']:,}"),
        ("Detected domain", schema.domain_label),
        ("Date columns", ", ".join(schema.dates) or "None"),
        ("Numeric measures", ", ".join(schema.measures[:8]) or "None"),
        ("Dimensions", ", ".join(schema.dimensions[:8]) or "None"),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Profile", "Value"]), width="stretch", hide_index=True)
    if schema.warnings:
        for warning in schema.warnings:
            st.caption(f"⚠ {warning}")


def render_missing_bar(frame: pd.DataFrame, theme: Theme, height: int) -> None:
    missing = frame.isna().sum().reset_index()
    missing.columns = ["column", "missing"]
    missing = missing[missing["missing"] > 0].sort_values("missing", ascending=True).tail(20)
    if missing.empty:
        st.success("No missing values were detected in the cleaned dataset.")
        return
    palette = _palette(theme)
    chart = alt.Chart(missing).mark_bar(color=palette[3] if len(palette) > 3 else palette[0], cornerRadiusEnd=4).encode(
        y=alt.Y("column:N", sort="x", title="Column"),
        x=alt.X("missing:Q", title="Missing values"),
        tooltip=[alt.Tooltip("column:N", title="Column"), alt.Tooltip("missing:Q", title="Missing")],
    )
    st.altair_chart(chart.properties(height=height, background="transparent"), width="stretch")


def render_component(
    frame: pd.DataFrame,
    component: Component,
    schema: DatasetSchema,
    theme: Theme,
    dataset_id: str = "",
    key_prefix: str = "",
) -> None:
    """Render one component.  The caller handles the grid columns."""
    height = component.height
    if component.type == "kpi":
        display, delta = render_kpi(frame, component, schema)
        st.metric(component.title, display, delta=delta, border=True, help=component.description or None)
        return
    if component.type == "insights":
        render_insights(frame, schema, key=f"{dataset_id}_{component.id}_{key_prefix}")
        return
    if component.type == "profile_table":
        render_profile_table(frame, schema)
        return
    if component.type == "missing_bar":
        render_missing_bar(frame, theme, height)
        return
    _render_chart(frame, component, schema, theme, height)


def _rows(components: list[Component]) -> list[list[Component]]:
    rows: list[list[Component]] = []
    current: list[Component] = []
    width = 0
    for component in sorted(components, key=lambda item: item.order):
        span = max(1, min(component.width, 12))
        if current and width + span > 12:
            rows.append(current)
            current, width = [], 0
        current.append(component)
        width += span
    if current:
        rows.append(current)
    return rows


def render_page(
    frame: pd.DataFrame,
    page: Page,
    schema: DatasetSchema,
    theme: Theme,
    dataset_id: str = "",
    key_prefix: str = "",
    editable: bool = False,
    selected_id: str | None = None,
    on_select: Any = None,
) -> None:
    """Render all components on a page using a 12-column responsive grid."""
    if not page.components:
        st.info("This page has no visuals yet. Add a KPI or chart from the Visualizations panel.")
        return
    for row in _rows(page.components):
        columns = st.columns([component.width for component in row], gap="medium")
        for column, component in zip(columns, row):
            with column:
                if editable:
                    with st.container(border=False):
                        header_cols = st.columns([0.82, 0.18])
                        with header_cols[0]:
                            st.markdown(
                                f"<div class='rm-component-title'>{html.escape(component.title)}</div>",
                                unsafe_allow_html=True,
                            )
                        with header_cols[1]:
                            if st.button("✎", key=f"rm_edit_{component.id}_{key_prefix}", help="Edit this visual"):
                                if on_select:
                                    on_select(component.id)
                        render_component(frame, component, schema, theme, dataset_id, key_prefix)
                else:
                    if component.type not in ("kpi", "insights", "profile_table", "missing_bar"):
                        st.markdown(
                            f"<div class='rm-component-title'>{html.escape(component.title)}</div>",
                            unsafe_allow_html=True,
                        )
                    render_component(frame, component, schema, theme, dataset_id, key_prefix)
