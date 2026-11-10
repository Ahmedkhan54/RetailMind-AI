"""RetailMind AI — Streamlit entry point.

This module is the Phase 1 shell of *RetailMind AI – Intelligent Universal
Business Analytics Platform*.  It keeps the original upload key, sidebar filter
contracts and export labels while adding universal profiling, an automatic
dashboard engine, a Power BI-inspired editor, an AI assistant, a verified
chatbot, RAG document Q&A and business insights.

Numerical answers are always computed from the uploaded DataFrame.  The
optional AI provider may only phrase verified facts; it never supplies the
numbers and the application runs fully without it.
"""

from __future__ import annotations

from io import BytesIO
import hashlib
import html
import inspect
import json
import logging
import os
from pathlib import Path
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from analytics import (
    calculate_correlation_matrix,
    flag_dataset_outliers,
    grouped_performance,
    monthly_summary,
)
from data_sources import (
    detect_column_mapping,
    duplicate_source_columns,
    inspect_excel_worksheets,
    preferred_excel_worksheet,
    read_uploaded_file,
)
from retailmind import storage, ui
from retailmind.alerts import (
    Alert,
    Notification,
    NotificationPreferences,
    acknowledge,
    alerts_csv_bytes,
    detect_alerts,
    dismiss,
    filter_alerts,
    merge_alerts,
    send_email_notification,
)
from retailmind.ai.assistant import AssistantAction, apply_action, parse_command, parse_with_llm
from retailmind.ai.chat import answer_question, suggested_questions
from retailmind.ai.insights import generate_insights
from retailmind.ai.nlp import _find_hint, DIMENSION_SYNONYMS, METRIC_SYNONYMS
from retailmind.ai.provider import AIProviderError, get_provider
from retailmind.ai.rag import RAGError, RAGStore
from retailmind.cleaning import DEFAULT_OPTIONS, CleaningReport, analyse_cleaning, apply_cleaning, cleaning_summary
from retailmind.compat import clean_uploaded_data, parse_uploaded_dates, render_sidebar_filters
from retailmind.config import AGGREGATIONS, APP_NAME, APP_TITLE, CHART_TYPES, MAX_UPLOAD_BYTES, PALETTES, THEME_PRESETS
from retailmind.engine import build_dashboard
from retailmind.exports import (
    business_analysis_pdf,
    executive_pdf,
    theme_json_bytes,
)
from retailmind.filters import render_universal_filters
from retailmind.forecasting import (
    available_dimension_values,
    forecast_dataset,
)
from retailmind.inventory import (
    build_inventory_recommendations,
    detect_inventory_columns,
)
from retailmind.models import Component, DashboardConfig, Theme
from retailmind.powerbi import (
    build_pbip,
    detect_power_bi_desktop,
)
from retailmind.render import render_component, render_insights, render_page
from retailmind.schema import DatasetSchema, ROLE_LABELS, apply_manual_mapping, infer_schema, profile_report
from retailmind.segmentation import (
    detect_customer_columns,
    segment_customers,
)
from retailmind.utils import dataframe_to_csv_bytes, excel_bytes, format_number, money, safe_divide, safe_percent
from src.business.reports import excel_report, generate_executive_summary_markdown

logger = logging.getLogger(__name__)

MAX_PREVIEW_ROWS = 200
SUPPORTED_EXTENSIONS = ("csv", "xlsx", "xls", "xlsm")
FLASH_KEY = "rm_flash"
CLEAR_UPLOAD_KEY = "rm_clear_upload"

# Roles offered in the manual mapping review.  Order identifiers are handled by
# automatic detection only, which keeps the legacy "Order Id" selectbox absent.
MAPPING_ROLES = (
    "revenue", "profit", "cost", "quantity", "unit_price", "discount",
    "date", "product", "category", "customer", "region", "city", "store",
    "department", "sales_rep", "payment_method", "employee_name", "salary",
    "attendance", "grade", "course",
)
MEASURE_ROLES = {"revenue", "profit", "cost", "quantity", "unit_price", "discount", "salary", "grade", "age"}
CURRENCY_ROLES = {"revenue", "profit", "cost", "salary", "unit_price"}
DERIVED_KPI_ROLES = {
    "records", "margin", "orders", "customers", "aov", "growth",
    "avg_salary", "employees", "attendance_rate", "measure_sum",
}


def _flash(message: str, kind: str = "success") -> None:
    """Queue a message that survives the following ``st.rerun``."""
    st.session_state[FLASH_KEY] = {"message": message, "kind": kind}


def _render_flash() -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if not flash:
        return
    renderer = {
        "success": st.success,
        "warning": st.warning,
        "error": st.error,
        "info": st.info,
    }.get(flash.get("kind", "success"), st.info)
    renderer(flash["message"])


def _role_for_column(schema: DatasetSchema, column: str | None) -> str | None:
    if not column:
        return None
    return next((role for role, mapped in schema.roles.items() if mapped == column), None)


def _format_for_measure(schema: DatasetSchema, column: str | None) -> str:
    return "currency" if _role_for_column(schema, column) in CURRENCY_ROLES else "number"


# ---------------------------------------------------------------------------
# Page + theme
# ---------------------------------------------------------------------------
def _current_theme() -> Theme:
    preset = st.session_state.get("rm_theme_preset", "dark")
    accent = st.session_state.get("rm_accent", PALETTES.get(preset, PALETTES["dark"])[0])
    return Theme(preset=preset, accent=accent, palette=PALETTES.get(preset, PALETTES["dark"]))


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------
def _identity(content: bytes, filename: str, sheet_name: str | None) -> str:
    digest = hashlib.sha256()
    digest.update(content)
    digest.update(filename.encode("utf-8"))
    digest.update(str(sheet_name or "").encode("utf-8"))
    return digest.hexdigest()[:20]


@st.cache_data(show_spinner=False, max_entries=8)
def _read_source(content: bytes, filename: str, sheet_name: str | None) -> pd.DataFrame:
    """Read an uploaded file once per distinct byte payload."""
    return read_uploaded_file(content, filename, sheet_name)


def _frame_signature(frame: pd.DataFrame) -> str:
    """Stable, cheap content signature for the active (filtered) frame.

    Used as part of session-state cache keys so a cached result can never be
    reused for a different dataset, filter selection or cleaning option set.
    """
    if frame is None or frame.empty:
        return "empty"
    try:
        hashed = pd.util.hash_pandas_object(frame, index=False).to_numpy()
        return f"{len(frame)}-{hashlib.sha256(hashed.tobytes()).hexdigest()[:16]}"
    except (TypeError, ValueError):
        # Fall back to an unambiguous repr for exotic object dtypes.
        digest = hashlib.sha256()
        digest.update(str(len(frame)).encode())
        digest.update(str(tuple(frame.columns)).encode())
        for column in frame.columns:
            digest.update(str(frame[column].tolist()).encode("utf-8", "replace"))
        return f"{len(frame)}-{digest.hexdigest()[:16]}"


def _value_signature(*values: Any) -> str:
    return hashlib.sha256(repr(values).encode("utf-8", "replace")).hexdigest()[:12]


def _cached_result(key: str, compute):
    """Memoise an expensive pure computation in ``st.session_state``."""
    if key not in st.session_state:
        st.session_state[key] = compute()
    return st.session_state[key]


def _purge_dataset_cache(identity: str) -> None:
    prefix = f"rm_perf_{identity}_"
    for key in [key for key in st.session_state if isinstance(key, str) and key.startswith(prefix)]:
        st.session_state.pop(key, None)



def _cleaning_signature(options: dict[str, bool]) -> str:
    return hashlib.sha256(json.dumps(options, sort_keys=True).encode("utf-8")).hexdigest()[:10]


def _render_cleaning_controls(identity: str) -> dict[str, bool]:
    """Render explicit, non-destructive cleaning switches."""
    options = dict(DEFAULT_OPTIONS)
    with st.expander("Data preparation & cleaning review", expanded=False):
        st.caption(
            "Cleaning is transparent and reviewable. The original upload stays untouched; "
            "rows are only removed when you explicitly enable de-duplication."
        )
        options["trim_whitespace"] = st.checkbox("Trim extra whitespace", value=True, key=f"rm_clean_trim_{identity}")
        options["normalise_categories"] = st.checkbox("Normalise category spelling", value=True, key=f"rm_clean_cat_{identity}")
        options["parse_dates"] = st.checkbox("Parse dates (incl. Excel serial dates)", value=True, key=f"rm_clean_dates_{identity}")
        options["coerce_numerics"] = st.checkbox("Coerce numeric columns", value=True, key=f"rm_clean_numeric_{identity}")
        options["drop_duplicate_rows"] = st.checkbox("Remove exact duplicate rows", value=False, key=f"rm_clean_dupes_{identity}")
        options["drop_empty_rows"] = st.checkbox("Remove completely empty rows", value=False, key=f"rm_clean_empty_{identity}")
        options["fill_invalid_numeric_zero"] = st.checkbox(
            "Replace invalid numeric values with 0 (not recommended)", value=False, key=f"rm_clean_zero_{identity}"
        )
    return options


def _render_cleaning_suggestions(suggestions, identity: str) -> None:
    if not suggestions:
        return
    with st.expander(f"Cleaning suggestions ({len(suggestions)})", expanded=False):
        for suggestion in suggestions[:16]:
            risk = {"low": "🟢", "medium": "🟠", "high": "🔴"}.get(suggestion.risk, "🔵")
            st.caption(
                f"{risk} **{suggestion.column}** · {suggestion.issue} ({suggestion.count:,}) — {suggestion.action}"
            )
        st.caption("Suggestions are reports, not silent edits. High-risk actions default to off.")


def _mapping_options(schema: DatasetSchema, role: str) -> list[str]:
    if role in MEASURE_ROLES:
        candidates = schema.numeric
    elif role == "date":
        candidates = schema.dates
    else:
        candidates = schema.dimensions or schema.categorical
    current = schema.roles.get(role)
    values = list(dict.fromkeys([column for column in candidates if column in schema.columns]))
    if current and current in schema.columns and current not in values:
        values.insert(0, current)
    return ["(not mapped)", *values]


def _render_mapping_editor(schema: DatasetSchema, identity: str) -> DatasetSchema:
    """Manual correction of detected semantic roles with type-aware options."""
    with st.expander("Column mapping — review & correct", expanded=False):
        st.caption(
            "Automatic detection is explainable, not final. Correct any uncertain mapping below; "
            "the dashboard rebuilds only from columns that actually exist."
        )
        with st.form(f"rm_mapping_form_{identity}"):
            columns = st.columns(2)
            updates: dict[str, str | None] = {}
            for index, role in enumerate(MAPPING_ROLES):
                options = _mapping_options(schema, role)
                current = schema.roles.get(role)
                selected_index = options.index(current) if current in options else 0
                with columns[index % 2]:
                    choice = st.selectbox(
                        ROLE_LABELS.get(role, role.replace("_", " ").title()),
                        options,
                        index=selected_index,
                        key=f"rm_map_{identity}_{role}",
                    )
                updates[role] = None if choice == "(not mapped)" else choice
            submitted = st.form_submit_button("Apply column mapping", width="stretch")
        if submitted:
            st.session_state[f"rm_manual_schema_{identity}"] = apply_manual_mapping(schema, updates)
            st.session_state[f"rm_rebuild_{identity}"] = True
            _flash("Column mapping applied. The dashboard was rebuilt from the new roles.", "success")
            st.rerun()
    return schema


# ---------------------------------------------------------------------------
# Dataset preparation
# ---------------------------------------------------------------------------
def _prepare_dataset(
    source: pd.DataFrame,
    mapping: dict[str, str | None],
    options: dict[str, bool],
    analysis_base: pd.DataFrame | None = None,
    base_schema: DatasetSchema | None = None,
    legacy_summary: dict[str, Any] | None = None,
):
    """Return (analysis frame, schema, cleaning report, retail_compatible).

    ``analysis_base``/``base_schema`` may be supplied by the caller when the
    canonical preparation has already been computed (and cached) for this
    upload, so the same work is never performed twice per rerun.
    """
    retail_compatible = bool(mapping.get("sales"))
    if retail_compatible:
        # Reuse the original canonical preparation so the legacy filter and KPI
        # contracts (product/category dependency, "Total sales") stay intact.
        if analysis_base is None:
            base, legacy_summary = clean_uploaded_data(source, mapping)
        else:
            base = analysis_base
        if base_schema is None:
            base_schema = infer_schema(base)
        cleaned, report = apply_cleaning(base, base_schema, options)
        report.applied.setdefault("legacy_canonical_rows", len(base))
        report.applied.setdefault("legacy_invalid_dates", int((legacy_summary or {}).get("invalid_dates", 0)))
    else:
        if base_schema is None:
            base_schema = infer_schema(source)
        cleaned, report = apply_cleaning(analysis_base if analysis_base is not None else source, base_schema, options)
    schema = infer_schema(cleaned) if not cleaned.empty else base_schema
    return cleaned, schema, report, retail_compatible


# ---------------------------------------------------------------------------
# Universal report artefacts
# ---------------------------------------------------------------------------
def _kpi_numbers(frame: pd.DataFrame, schema: DatasetSchema) -> dict[str, Any]:
    revenue_column = schema.role_column("revenue")
    profit_column = schema.role_column("profit")
    order_column = schema.role_column("order_id")
    quantity_column = schema.role_column("quantity")
    revenue = float(pd.to_numeric(frame[revenue_column], errors="coerce").sum()) if revenue_column else 0.0
    profit = float(pd.to_numeric(frame[profit_column], errors="coerce").sum()) if profit_column else 0.0
    orders = int(frame[order_column].nunique(dropna=True)) if order_column else len(frame)
    quantity = float(pd.to_numeric(frame[quantity_column], errors="coerce").sum()) if quantity_column else None
    return {
        "total_sales": revenue,
        "total_profit": profit,
        "profit_margin": safe_divide(profit, revenue) if profit_column and revenue else None,
        "order_count": orders,
        "average_order_value": safe_divide(revenue, orders) if revenue and orders else None,
        "quantity_sold": quantity,
    }


def _universal_markdown(frame: pd.DataFrame, schema: DatasetSchema, filename: str, insights: list[Any]) -> str:
    profile = profile_report(frame, schema)
    lines = [
        f"# RetailMind AI — Executive Summary",
        f"**Dataset:** {filename}  ",
        f"**Records:** {len(frame):,}  ",
        f"**Columns:** {len(frame.columns):,}  ",
        f"**Detected domain:** {schema.domain_label}",
        "",
        "## Detected fields",
    ]
    if schema.roles:
        for role, column in schema.roles.items():
            lines.append(f"- **{ROLE_LABELS.get(role, role.title())}:** {column}")
    else:
        lines.append("- No semantic roles were confidently detected.")
    lines.extend(["", "## Verified measures"])
    for column, summary in list(profile["numeric_summary"].items())[:12]:
        lines.append(
            f"- **{schema.label_for(column)}:** sum {format_number(summary['sum'])}, "
            f"mean {format_number(summary['mean'])}, min {format_number(summary['min'])}, max {format_number(summary['max'])}"
        )
    if not profile["numeric_summary"]:
        lines.append("- No numeric measures are available.")
    if profile["date_ranges"]:
        lines.extend(["", "## Date coverage"])
        for column, values in profile["date_ranges"].items():
            lines.append(f"- **{column}:** {values['min']} to {values['max']} ({values['valid']:,} valid dates)")
    if insights:
        lines.extend(["", "## Verified insights"])
        for insight in insights:
            lines.append(f"- **{insight.title}.** {insight.text}")
    lines.extend(
        [
            "",
            "---",
            "*All values were computed directly from the active uploaded data. No synthetic values are included.*",
        ]
    )
    return "\n".join(lines)


def _generic_workbook(frame: pd.DataFrame, schema: DatasetSchema, report: CleaningReport) -> bytes:
    output = BytesIO()
    profile = profile_report(frame, schema)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Cleaned Data", index=False)
        pd.DataFrame(
            [{"Profile": key, "Value": json.dumps(value, default=str) if isinstance(value, (dict, list)) else value}
             for key, value in profile.items()]
        ).to_excel(writer, sheet_name="Data Profile", index=False)
        cleaning_summary(report).to_excel(writer, sheet_name="Cleaning Report", index=False)
    return output.getvalue()


def _executive_markdown(frame, schema, filename, filters, insights, category_summary, top_products):
    if schema.has("revenue") or schema.has("profit"):
        kpis = _kpi_numbers(frame, schema)
        return generate_executive_summary_markdown(
            filtered=frame,
            kpis=kpis,
            dataset_name=filename,
            filters=filters,
            insights=[f"{insight.title}: {insight.text}" for insight in insights],
            category_summary=category_summary,
            top_products=top_products,
        )
    return _universal_markdown(frame, schema, filename, insights)


def _executive_workbook(frame, schema, report, filename, filters, insights, category_summary, top_products, profile):
    if schema.has("revenue") and schema.has("profit") and "order_id" in frame.columns:
        try:
            monthly = monthly_summary(frame) if "order_date" in frame.columns else pd.DataFrame()
            quality = {
                "Records": len(frame),
                "Columns": len(frame.columns),
                "Missing cells": int(frame.isna().sum().sum()),
                "Duplicate rows": int(frame.duplicated().sum()),
            }
            return excel_report(
                frame,
                category_summary if category_summary is not None else pd.DataFrame(),
                top_products if top_products is not None else pd.DataFrame(),
                monthly,
                pd.DataFrame(),
                quality,
                [f"{insight.title}: {insight.text}" for insight in insights],
            )
        except Exception:
            logger.exception("Legacy executive workbook failed; using the universal workbook")
    return _generic_workbook(frame, schema, report)


def _dimension_summary(frame, schema, dimension_role: str, measure_role: str):
    dimension = schema.role_column(dimension_role)
    measure = schema.role_column(measure_role)
    if not dimension or not measure or dimension not in frame.columns or measure not in frame.columns:
        return None
    working = frame[[dimension, measure]].copy()
    working[measure] = pd.to_numeric(working[measure], errors="coerce")
    table = working.dropna(subset=[measure]).groupby(dimension, dropna=False)[measure].sum().reset_index()
    table = table.sort_values(measure, ascending=False)
    table = table.rename(columns={dimension: dimension_role, measure: measure_role})
    if dimension_role == "category" and measure_role == "revenue":
        table = table.rename(columns={"category": "category", "revenue": "sales"})
        table["profit"] = None
        profit = schema.role_column("profit")
        if profit and profit in frame.columns:
            profit_table = frame.groupby(schema.role_column("category"), dropna=False)[profit].sum()
            table["profit"] = table["category"].map(profit_table)
        table["margin"] = [
            safe_divide(profit_value, sales_value) if pd.notna(profit_value) else None
            for profit_value, sales_value in zip(table["profit"], table["sales"])
        ]
    if dimension_role == "product" and measure_role == "revenue":
        table = table.rename(columns={"product": "product_name", "revenue": "sales"})
    return table


def _download_artifacts(frame, schema, report, filename, filters, insights, alerts) -> dict[str, Any]:
    """Prepare every export once per (dataset + filters) combination.

    Byte-heavy artefacts (PDF, Excel workbook, PBIP zip) are returned as
    zero-argument callables so Streamlit only generates them when the user
    actually clicks the matching download button — rendering the download
    row stays cheap even though the artefacts are expensive.
    """
    profile = profile_report(frame, schema)
    category_summary = _dimension_summary(frame, schema, "category", "revenue")
    top_products = _dimension_summary(frame, schema, "product", "revenue")
    markdown = _executive_markdown(frame, schema, filename, filters, insights, category_summary, top_products)
    workbook = _executive_workbook(frame, schema, report, filename, filters, insights, category_summary, top_products, profile)
    stem = Path(filename).stem or "dataset"

    def _make_pdf(builder):
        def _compute():
            kwargs = dict(filename=filename, insights=insights, alerts=alerts or ())
            if "filters" in inspect.signature(builder).parameters:
                kwargs["filters"] = filters
            result = builder(frame, schema, **kwargs)
            return result.data

        return _compute

    def _make_pbip():
        return lambda: build_pbip(frame, schema, project_name=stem).to_zip_bytes()

    return {
        "csv": lambda frame=frame: dataframe_to_csv_bytes(frame),
        "excel": lambda frame=frame: excel_bytes(frame),
        "markdown": markdown,
        "workbook": lambda: workbook,
        "exec_pdf_data": _make_pdf(executive_pdf),
        "exec_pdf_name": f"executive_summary_{stem}.pdf",
        "exec_pdf_mime": "application/pdf",
        "biz_pdf_data": _make_pdf(business_analysis_pdf),
        "biz_pdf_name": f"business_analysis_{stem}.pdf",
        "biz_pdf_mime": "application/pdf",
        "pbip_zip": _make_pbip(),
        "_theme": lambda: theme_json_bytes("RetailMind AI"),
    }


def render_downloads(frame, schema, report, filename, filters, insights, identity, alerts: Iterable[Any] = ()):
    st.subheader("Downloads & report export")
    st.caption("Every export is generated from the active filtered data in memory. The original upload is never modified.")
    stem = Path(filename).stem or "dataset"
    artifacts_sig = _value_signature(
        _frame_signature(frame),
        _cleaning_signature(report.applied),
        _value_signature(report.rows_before, report.rows_after),
        _cleaning_signature({key: str(value) for key, value in filters.items()}),
        tuple(insight.title for insight in insights),
        tuple(getattr(alert, "id", None) for alert in (alerts or ())),
        stem,
    )
    artifacts = _cached_result(
        f"rm_perf_{identity}_downloads_{artifacts_sig}",
        lambda: _download_artifacts(frame, schema, report, filename, filters, insights, list(alerts or ())),
    )
    markdown = artifacts["markdown"]
    columns = st.columns(4)
    columns[0].download_button(
        "Download cleaned CSV",
        artifacts["csv"],
        f"{stem}_cleaned.csv",
        "text/csv",
        key=f"rm_dl_csv_{identity}",
        width="stretch",
    )
    columns[1].download_button(
        "Download cleaned Excel",
        artifacts["excel"],
        f"{stem}_cleaned.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"rm_dl_xlsx_{identity}",
        width="stretch",
    )
    columns[2].download_button(
        "Download executive summary (Markdown)",
        markdown.encode("utf-8"),
        f"executive_summary_{stem}.md",
        "text/markdown",
        key=f"rm_dl_md_{identity}",
        width="stretch",
    )
    columns[3].download_button(
        "Download executive workbook (Excel)",
        artifacts["workbook"],
        f"{stem}_cleaned.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"rm_dl_workbook_{identity}",
        width="stretch",
    )
    # Row 2: Additional exports (PDF reports, Power BI PBIP zip, and Power BI theme)
    cols2 = st.columns(4)
    cols2[0].download_button(
        "Download executive summary (PDF)",
        artifacts["exec_pdf_data"],
        artifacts["exec_pdf_name"],
        artifacts["exec_pdf_mime"],
        key=f"rm_dl_exec_pdf_{identity}",
        width="stretch",
    )
    cols2[1].download_button(
        "Download business analysis (PDF)",
        artifacts["biz_pdf_data"],
        artifacts["biz_pdf_name"],
        artifacts["biz_pdf_mime"],
        key=f"rm_dl_biz_pdf_{identity}",
        width="stretch",
    )
    cols2[2].download_button(
        "Download Power BI project (ZIP)",
        artifacts["pbip_zip"],
        f"{stem}_pbip.zip",
        "application/zip",
        key=f"rm_dl_pbip_zip_{identity}",
        width="stretch",
    )
    cols2[3].download_button(
        "Download Power BI theme (JSON)",
        artifacts["_theme"],
        f"{stem}_theme.json",
        "application/json",
        key=f"rm_dl_theme_json_{identity}",
        width="stretch",
    )
    with st.expander("Preview executive summary", expanded=False):
        st.markdown(markdown)


def render_advanced_analytics(frame: pd.DataFrame, schema: DatasetSchema, identity: str) -> None:
    """Preserve the original project's outlier and correlation analytics."""
    numeric_columns = [column for column in schema.numeric if column in frame.columns]
    if not numeric_columns:
        return
    with st.expander("Advanced analytics — outliers & correlation", expanded=False):
        st.caption("Statistical diagnostics only. Nothing is deleted or altered.")
        if numeric_columns:
            left, middle, right = st.columns([2, 1, 1])
            with left:
                column = st.selectbox("Numerical column", numeric_columns, key=f"rm_outlier_col_{identity}")
            with middle:
                method_label = st.radio("Method", ["IQR", "Z-score"], horizontal=True, key=f"rm_outlier_method_{identity}")
            with right:
                default_threshold = 1.5 if method_label == "IQR" else 3.0
                threshold = st.number_input(
                    "Threshold", 0.5, 10.0, value=default_threshold, step=0.1,
                    key=f"rm_outlier_thresh_{identity}_{method_label}",
                )
            method = "zscore" if method_label == "Z-score" else "iqr"
            frame_sig = _frame_signature(frame)
            try:
                flagged, summary = _cached_result(
                    f"rm_perf_{identity}_out_{frame_sig}_{column}_{method}_{threshold:.1f}",
                    lambda: flag_dataset_outliers(frame, column, method=method, threshold=threshold),
                )
            except Exception as error:
                st.warning(f"Outlier analysis is unavailable for this column: {error}")
            else:
                metrics = st.columns(3)
                metrics[0].metric("Analysed rows", f"{summary['valid_count']:,}", border=True)
                metrics[1].metric("Outliers", f"{summary['outlier_count']:,}", border=True)
                metrics[2].metric("Outlier rate", f"{summary['outlier_percentage']:.2f}%", border=True)
                if summary["outlier_count"]:
                    st.dataframe(flagged.head(50), hide_index=True)
                else:
                    st.success("No statistical outliers were detected at this threshold.")
        if len(numeric_columns) >= 2:
            st.divider()
            method_label = st.radio(
                "Correlation coefficient",
                ["Pearson", "Spearman"],
                horizontal=True,
                key=f"rm_corr_method_{identity}",
            )
            method = "spearman" if method_label == "Spearman" else "pearson"
            matrix = _cached_result(
                f"rm_perf_{identity}_corr_{_frame_signature(frame)}_{method}",
                lambda: calculate_correlation_matrix(frame, method=method),
            )
            if matrix.empty or len(matrix.columns) < 2:
                st.info("Insufficient non-constant numerical columns for a correlation matrix.")
                return
            melted = matrix.reset_index().rename(columns={"index": "Variable 1"})
            melted = pd.melt(melted, id_vars=["Variable 1"], var_name="Variable 2", value_name="Correlation")
            base = alt.Chart(melted).encode(
                x=alt.X("Variable 1:N", title=None, axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("Variable 2:N", title=None),
            )
            heatmap = base.mark_rect().encode(
                color=alt.Color("Correlation:Q", scale=alt.Scale(domain=[-1, 0, 1], scheme="redblue", reverse=True)),
                tooltip=["Variable 1:N", "Variable 2:N", alt.Tooltip("Correlation:Q", format=".3f")],
            )
            text = base.mark_text(baseline="middle", fontSize=11).encode(
                text=alt.Text("Correlation:Q", format=".2f"),
                color=alt.condition("abs(datum.Correlation) > 0.5", alt.value("white"), alt.value("black")),
            )
            chart = (heatmap + text).properties(height=max(240, len(matrix.columns) * 34))
            st.altair_chart(chart, width="stretch")
            st.dataframe(matrix, width="stretch")


def render_alerts_panel(frame: pd.DataFrame, schema: DatasetSchema, identity: str) -> list[Alert]:
    alerts_key = f"rm_alerts_{identity}"
    frame_sig = _frame_signature(frame)
    raw_alerts = _cached_result(
        f"rm_perf_{identity}_alerts_{frame_sig}",
        lambda: detect_alerts(frame, schema),
    )
    if alerts_key not in st.session_state:
        st.session_state[alerts_key] = raw_alerts
    else:
        st.session_state[alerts_key] = merge_alerts(st.session_state[alerts_key], raw_alerts)
    all_alerts: list[Alert] = st.session_state[alerts_key]

    with st.expander(f"AI Smart Alerts ({len(all_alerts)})", expanded=bool(any(a.severity == "critical" and a.status == "new" for a in all_alerts))):
        if not all_alerts:
            st.info("No anomalies or threshold alerts detected on the active filtered dataset.")
            return []

        crit_count = sum(1 for a in all_alerts if a.severity == "critical" and a.status != "dismissed")
        warn_count = sum(1 for a in all_alerts if a.severity == "warning" and a.status != "dismissed")
        info_count = sum(1 for a in all_alerts if a.severity == "info" and a.status != "dismissed")
        ack_count = sum(1 for a in all_alerts if a.status == "acknowledged")

        kpi_cols = st.columns(4)
        kpi_cols[0].metric("Critical Alerts", crit_count)
        kpi_cols[1].metric("Warnings", warn_count)
        kpi_cols[2].metric("Informational", info_count)
        kpi_cols[3].metric("Acknowledged", ack_count)

        f_col1, f_col2, f_col3 = st.columns([1, 1, 1])
        with f_col1:
            sev_filter = st.selectbox("Severity", ["All", "critical", "warning", "info"], key=f"rm_alert_sev_{identity}")
        with f_col2:
            status_filter = st.selectbox("Status", ["All", "new", "acknowledged", "dismissed"], key=f"rm_alert_stat_{identity}")
        with f_col3:
            st.download_button(
                "Download Alerts CSV",
                alerts_csv_bytes(all_alerts),
                f"smart_alerts_{identity[:8]}.csv",
                "text/csv",
                key=f"rm_dl_alerts_{identity}",
                width="stretch",
            )

        filtered_alerts = all_alerts
        if sev_filter != "All":
            filtered_alerts = filter_alerts(filtered_alerts, severity=sev_filter)
        if status_filter != "All":
            filtered_alerts = filter_alerts(filtered_alerts, status=status_filter)

        if not filtered_alerts:
            st.caption("No alerts match the selected severity and status filters.")

        for alert in filtered_alerts:
            sev_badge = ui.pill(alert.severity.upper(), "warn" if alert.severity == "warning" else ("accent" if alert.severity == "info" else "warn"))
            status_badge = ui.pill(alert.status.title(), "ok" if alert.status == "acknowledged" else "warn")
            border_col = "#f43f5e" if alert.severity == "critical" else ("#f59e0b" if alert.severity == "warning" else "#38bdf8")
            st.markdown(
                f"<div style='border:1px solid rgba(148,163,184,0.18);border-left:4px solid {border_col};"
                f"border-radius:12px;padding:12px 16px;margin:8px 0;background:rgba(20,27,49,0.7);'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;'>"
                f"<span style='font-weight:700;font-size:0.92rem;color:#e7ecff;'>{html.escape(alert.title)}</span>"
                f"<div>{sev_badge} {status_badge}</div></div>"
                f"<div style='font-size:0.83rem;color:#cbd5e1;margin-bottom:6px;'>{html.escape(alert.description)}</div>"
                f"<div style='font-size:0.75rem;color:#94a3b8;'><strong>Scope:</strong> {html.escape(alert.scope)} · <strong>Period:</strong> {html.escape(alert.comparison_period or 'N/A')}</div>"
                f"{f'<div style=\"font-size:0.78rem;color:#a5b4fc;margin-top:4px;\">💡 <em>{html.escape(alert.suggestion)}</em></div>' if alert.suggestion else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )
            btn_col1, btn_col2, _ = st.columns([1, 1, 4])
            if alert.status == "new":
                if btn_col1.button("Acknowledge", key=f"rm_ack_{alert.id}_{identity}", width="stretch"):
                    acknowledge(alert)
                    _flash(f"Acknowledged alert: {alert.title}", "success")
                    st.rerun()
            if alert.status != "dismissed":
                if btn_col2.button("Dismiss", key=f"rm_dsm_{alert.id}_{identity}", width="stretch"):
                    dismiss(alert)
                    _flash(f"Dismissed alert: {alert.title}", "info")
                    st.rerun()

        with st.expander("Notification preferences & email test", expanded=False):
            prefs = NotificationPreferences.from_env()
            st.caption(f"Min severity: **{prefs.min_severity}** · Email notifications: **{'Enabled' if prefs.email_enabled else 'Disabled'}**")
            test_recipient = st.text_input("Test recipient address", value=prefs.recipients[0] if prefs.recipients else "", key=f"rm_notif_email_{identity}")
            if st.button("Send test alert email", key=f"rm_test_email_{identity}"):
                if not test_recipient.strip():
                    st.warning("Enter a valid recipient email address.")
                else:
                    test_prefs = NotificationPreferences(
                        min_severity=prefs.min_severity,
                        email_enabled=True,
                        recipients=(test_recipient.strip(),),
                        smtp_host=prefs.smtp_host,
                        smtp_port=prefs.smtp_port,
                        smtp_user=prefs.smtp_user,
                        smtp_password=prefs.smtp_password,
                        sender=prefs.sender or "alerts@retailmind.ai",
                        use_tls=prefs.use_tls,
                    )
                    sample_notif = Notification(
                        alert_id="test",
                        title="RetailMind AI Test Notification",
                        message="This is a test notification from RetailMind AI Smart Alerts.",
                        severity="info",
                        fingerprint="test_fp",
                    )
                    status = send_email_notification(sample_notif, test_prefs)
                    if status == "accepted_by_smtp":
                        st.success(f"Notification accepted by SMTP server for {test_recipient}.")
                    elif status == "not_configured":
                        st.warning("SMTP server is not configured. Set RETAILMIND_SMTP_HOST, RETAILMIND_SMTP_USER, and RETAILMIND_SMTP_PASSWORD.")
                    else:
                        st.error(f"Email delivery status: {status}")
    return all_alerts


def render_intelligence_hub(frame: pd.DataFrame, schema: DatasetSchema, identity: str, filename: str, filters: dict[str, Any], alerts: list[Alert]):
    st.subheader("Advanced Business Intelligence")
    st.caption("AI-powered customer tagging, predictive inventory recommendations, multi-method forecasting, and Power BI PBIP exports.")
    frame_sig = _frame_signature(frame)

    seg_tab, inv_tab, fc_tab, pbi_tab = st.tabs([
        "Customer Segmentation",
        "Predictive Stock",
        "Sales & Profit Forecasting",
        "Power BI Export Center",
    ])

    with seg_tab:
        cust_cols = detect_customer_columns(frame, schema)
        has_cust = bool(cust_cols.get("customer") and cust_cols.get("date"))
        if not has_cust:
            st.info("Customer segmentation requires a customer identifier and order date. Map these columns in the sidebar column mapping.")
        else:
            k_clusters = st.slider("Number of clusters (k)", 2, 6, value=4, key=f"rm_seg_k_{identity}")
            seg_result = _cached_result(
                f"rm_perf_{identity}_seg_{frame_sig}_{k_clusters}",
                lambda: segment_customers(frame, schema, max_clusters=k_clusters),
            )
            if seg_result.available:
                m_cols = st.columns(4)
                total_cust = len(seg_result.rfm)
                churn_risk_cust = int(seg_result.rfm["is_rule_based_churn_risk"].sum())
                top_segment = seg_result.summary.iloc[0]["segment"] if not seg_result.summary.empty else "N/A"
                sil_score = f"{seg_result.silhouette:.3f}" if seg_result.silhouette is not None else "N/A"

                m_cols[0].metric("Total Customers", f"{total_cust:,}")
                m_cols[1].metric("Top Segment", top_segment)
                m_cols[2].metric("Churn Risk Rule", f"{churn_risk_cust:,}")
                m_cols[3].metric("Silhouette Score", sil_score)

                st.markdown("**Segment Summary**")
                st.dataframe(seg_result.summary, width="stretch", hide_index=True)

                chart = alt.Chart(seg_result.summary).mark_bar(cornerRadius=6).encode(
                    x=alt.X("segment:N", title="Segment", sort="-y"),
                    y=alt.Y("customers:Q", title="Customers"),
                    color=alt.Color("segment:N", legend=None),
                    tooltip=[
                        alt.Tooltip("segment:N", title="Segment"),
                        alt.Tooltip("customers:Q", title="Customers"),
                        alt.Tooltip("revenue_share:Q", title="Revenue Share", format=".1%"),
                        alt.Tooltip("avg_monetary_value:Q", title="Avg Monetary", format=",.2f"),
                    ],
                ).properties(height=260)
                st.altair_chart(chart, use_container_width=True)

                with st.expander("Customer RFM details preview", expanded=False):
                    st.dataframe(seg_result.rfm.head(MAX_PREVIEW_ROWS), width="stretch", hide_index=True)

                dl_col1, dl_col2 = st.columns(2)
                dl_col1.download_button(
                    "Download Customer Segments (CSV)",
                    lambda r=seg_result: r.to_csv_bytes(),
                    f"customer_segments_{identity[:8]}.csv",
                    "text/csv",
                    key=f"rm_dl_seg_csv_{identity}",
                    width="stretch",
                )
                dl_col2.download_button(
                    "Download Customer Segments (Excel)",
                    lambda r=seg_result: r.to_excel_bytes(),
                    f"customer_segments_{identity[:8]}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"rm_dl_seg_xlsx_{identity}",
                    width="stretch",
                )
            else:
                for note in seg_result.notes:
                    st.warning(note)

    with inv_tab:
        inv_cols = detect_inventory_columns(frame, schema)
        has_inv = bool(inv_cols.get("product") and inv_cols.get("date") and inv_cols.get("quantity"))
        if not has_inv:
            st.info("Predictive stock recommendations require a product name, date and sales quantity. Add or map these columns to enable inventory recommendations.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                lead_days = st.number_input("Lead time (days)", min_value=1.0, max_value=60.0, value=7.0, step=1.0, key=f"rm_lead_{identity}")
            with c2:
                safety_days = st.number_input("Safety stock (days)", min_value=1.0, max_value=60.0, value=7.0, step=1.0, key=f"rm_safe_{identity}")
            with c3:
                service_level = st.selectbox("Service level", [0.90, 0.95, 0.98, 0.99], index=1, format_func=lambda x: f"{x:.0%}", key=f"rm_service_{identity}")
            with c4:
                target_cover = st.number_input("Target cover (days)", min_value=1.0, max_value=90.0, value=14.0, step=1.0, key=f"rm_cover_{identity}")

            inv_res = _cached_result(
                f"rm_perf_{identity}_inv_{frame_sig}_{lead_days}_{safety_days}_{service_level}_{target_cover}",
                lambda: build_inventory_recommendations(
                    frame,
                    schema,
                    lead_time_days=lead_days,
                    safety_days=safety_days,
                    service_level=service_level,
                    target_cover_days=target_cover,
                ),
            )
            if inv_res.available:
                critical_items = inv_res.table[inv_res.table["status"].isin(["Out of stock", "Critical — reorder now", "Low — reorder soon"])]
                kpi_c1, kpi_c2, kpi_c3, kpi_c4 = st.columns(4)
                kpi_c1.metric("Products Analysed", f"{len(inv_res.table):,}")
                kpi_c2.metric("At-Risk / Low Stock", f"{len(critical_items):,}")
                kpi_c3.metric("Stock Column", "Detected" if inv_res.stock_available else "Not Provided")
                kpi_c4.metric("Healthy Stock", f"{len(inv_res.table[inv_res.table['status'] == 'Healthy']):,}")

                st.markdown("**Stock Reorder Recommendations**")
                st.dataframe(inv_res.table, width="stretch", hide_index=True)

                with st.expander("Inventory formulas & assumptions", expanded=False):
                    for a in inv_res.assumptions:
                        st.caption(f"• {a}")
                    for n in inv_res.notes:
                        st.info(n)

                inv_dl1, inv_dl2 = st.columns(2)
                inv_dl1.download_button(
                    "Download Stock Recommendations (CSV)",
                    lambda r=inv_res: r.to_csv_bytes(),
                    f"stock_recommendations_{identity[:8]}.csv",
                    "text/csv",
                    key=f"rm_dl_inv_csv_{identity}",
                    width="stretch",
                )
                inv_dl2.download_button(
                    "Download Stock Recommendations (Excel)",
                    lambda r=inv_res: r.to_excel_bytes(),
                    f"stock_recommendations_{identity[:8]}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"rm_dl_inv_xlsx_{identity}",
                    width="stretch",
                )
            else:
                for note in inv_res.notes:
                    st.warning(note)

    with fc_tab:
        date_col = schema.role_column("date")
        if not date_col:
            st.info("Forecasting requires a date column. Map a date column in the column mapping review.")
        else:
            fc_col1, fc_col2, fc_col3, fc_col4 = st.columns(4)
            with fc_col1:
                available_metrics = [r for r in ("revenue", "profit", "cost", "quantity") if schema.role_column(r)] or ["revenue"]
                metric_role = st.selectbox("Metric to forecast", available_metrics, format_func=lambda x: x.title(), key=f"rm_fc_metric_{identity}")
            with fc_col2:
                freq = st.selectbox("Frequency", ["Daily", "Weekly", "Monthly"], key=f"rm_fc_freq_{identity}")
            with fc_col3:
                horizon = st.slider("Forecast horizon (periods)", 7, 60, value=14, key=f"rm_fc_horizon_{identity}")
            with fc_col4:
                method = st.selectbox("Method", ["Auto (backtest)", "Moving average", "Exponential smoothing", "Linear trend", "ARIMA / SARIMA"], key=f"rm_fc_method_{identity}")

            dim_role = None
            dim_val = None
            if schema.role_column("product") or schema.role_column("category"):
                choose_dim = schema.role_column("product") or schema.role_column("category")
                dim_role = "product" if choose_dim == schema.role_column("product") else "category"
                options = ["(All)"] + available_dimension_values(frame, schema, dim_role)[:30]
                selected_dim_val = st.selectbox(f"Filter by {dim_role.title()}", options, key=f"rm_fc_dimval_{identity}")
                if selected_dim_val != "(All)":
                    dim_val = selected_dim_val

            fc_result = _cached_result(
                f"rm_perf_{identity}_fc_{frame_sig}_{metric_role}_{freq}_{horizon}_{method}_{dim_role}_{dim_val}",
                lambda: forecast_dataset(
                    frame,
                    schema,
                    metric_role=metric_role,
                    frequency=freq,
                    periods=horizon,
                    method=method,
                    dimension_role=dim_role if dim_val else None,
                    dimension_value=dim_val,
                ),
            )
            if fc_result.available:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Selected Model", fc_result.method)
                m2.metric("MAE", f"{fc_result.metrics.get('mae', 0):,.2f}" if fc_result.metrics.get('mae') is not None else "N/A")
                m3.metric("RMSE", f"{fc_result.metrics.get('rmse', 0):,.2f}" if fc_result.metrics.get('rmse') is not None else "N/A")
                mape_val = fc_result.metrics.get("mape")
                m4.metric("MAPE", f"{mape_val:.2f}%" if mape_val is not None else "N/A")

                hist_df = fc_result.history.copy()
                hist_df["series"] = "Actual"
                fc_df = fc_result.forecast.copy().rename(columns={"forecast": "actual"})
                fc_df["series"] = "Forecast"
                combined_chart_df = pd.concat([hist_df[["date", "actual", "series"]], fc_df[["date", "actual", "series"]]], ignore_index=True)

                line_chart = alt.Chart(combined_chart_df).mark_line().encode(
                    x=alt.X("date:T", title="Date"),
                    y=alt.Y("actual:Q", title=f"{metric_role.title()}"),
                    color=alt.Color("series:N", scale=alt.Scale(domain=["Actual", "Forecast"], range=["#38bdf8", "#f59e0b"])),
                    strokeDash=alt.condition(alt.datum.series == "Forecast", alt.value([4, 4]), alt.value([0]))
                ).properties(height=280)

                band_chart = alt.Chart(fc_result.forecast).mark_area(opacity=0.2, color="#f59e0b").encode(
                    x="date:T",
                    y="lower_bound:Q",
                    y2="upper_bound:Q"
                )
                st.altair_chart(band_chart + line_chart, use_container_width=True)

                with st.expander("Forecast numbers table", expanded=False):
                    st.dataframe(fc_result.forecast, width="stretch", hide_index=True)

                fc_dl1, fc_dl2 = st.columns(2)
                fc_dl1.download_button(
                    "Download Forecast (CSV)",
                    lambda r=fc_result: r.to_csv_bytes(),
                    f"forecast_{metric_role}_{identity[:8]}.csv",
                    "text/csv",
                    key=f"rm_dl_fc_csv_{identity}",
                    width="stretch",
                )
                fc_dl2.download_button(
                    "Download Forecast (Excel)",
                    lambda r=fc_result: r.to_excel_bytes(),
                    f"forecast_{metric_role}_{identity[:8]}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"rm_dl_fc_xlsx_{identity}",
                    width="stretch",
                )
            else:
                for note in fc_result.notes:
                    st.warning(note)

    with pbi_tab:
        alert_sig = _value_signature(tuple((a.id, a.description) for a in alerts[:5] if a is not None))
        pbip_project = _cached_result(
            f"rm_perf_{identity}_pbip_{frame_sig}_{alert_sig}_{Path(filename).stem}",
            lambda: build_pbip(
                frame,
                schema,
                project_name=Path(filename).stem or "RetailMindReport",
                insights=[a.description for a in alerts[:5]] if alerts else (),
            ),
        )
        pbi_status = ui.pill("PBIP Validated (0 errors)", "ok") if pbip_project.valid else ui.pill(f"{len(pbip_project.validation)} errors", "warn")
        st.markdown(f"**Power BI Desktop Export Center** · {pbi_status}", unsafe_allow_html=True)
        st.caption("Generate an authentic Power BI Project (.pbip) with a complete TMDL semantic model, star schema tables, DAX measures, and PBIR report pages.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Semantic Tables", len(pbip_project.tables))
        c2.metric("DAX Measures", len(pbip_project.measures))
        c3.metric("Report Pages", len(pbip_project.pages))
        desktop_path = detect_power_bi_desktop()
        c4.metric("Power BI Desktop", "Detected" if desktop_path else "Not Detected")

        with st.expander("Semantic Model & Report Details", expanded=False):
            st.markdown(f"**Tables:** {', '.join(pbip_project.tables)}")
            st.markdown(f"**Measures:** {', '.join(pbip_project.measures)}")
            st.markdown(f"**Report Pages:** {', '.join(pbip_project.pages)}")
            if desktop_path:
                st.caption(f"Power BI Desktop executable found: `{desktop_path}`")
            else:
                st.caption("Power BI Desktop executable was not detected in standard system paths. You can still download the .pbip archive and open it on any computer with Power BI Desktop.")

        st.markdown(
            """
            **How to open in Power BI Desktop:**
            1. Click **Download Power BI Project (.pbip ZIP)** below.
            2. Extract the downloaded ZIP file to a local folder.
            3. Double-click the `.pbip` file to open the project directly in **Microsoft Power BI Desktop**.
            4. In Power BI Desktop, you can customize visuals, refresh data, or select **File > Save As > Power BI file (*.pbix)** to generate a `.pbix` file.
            """
        )

        pbip_zip = pbip_project.to_zip_bytes()
        stem_name = Path(filename).stem or "RetailMindReport"
        pbi_dl1, pbi_dl2 = st.columns(2)
        pbi_dl1.download_button(
            "Download Power BI Project (.pbip ZIP)",
            pbip_zip,
            f"{stem_name}_powerbi.zip",
            "application/zip",
            key=f"rm_dl_pbip_{identity}",
            type="primary",
            width="stretch",
        )
        pbi_dl2.download_button(
            "Download Power BI Theme (JSON)",
            theme_json_bytes("RetailMind AI"),
            f"{stem_name}_theme.json",
            "application/json",
            key=f"rm_dl_pbip_theme_{identity}",
            width="stretch",
        )


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------
def _config_key(identity: str) -> str:
    return f"rm_config_{identity}"


def _original_key(identity: str) -> str:
    return f"rm_original_{identity}"


def _save_state(config: DashboardConfig) -> None:
    st.session_state[_config_key(config.dataset_id)] = config


def _commit(config: DashboardConfig, message: str, kind: str = "success") -> None:
    """Persist a mutation, autosave, notify the user and rerun."""
    try:
        storage.autosave(config)
    except OSError:
        logger.warning("Autosave failed", exc_info=True)
    _save_state(config)
    _flash(message, kind)
    st.rerun()


def _mutate(config: DashboardConfig, callback) -> None:
    """Run a mutation, honour its success flag and always give feedback."""
    namespace = config.dataset_id
    before = config.to_json()
    try:
        result = callback(config)
    except Exception as error:  # never leave the UI silently broken
        logger.exception("Dashboard action failed")
        _flash(f"Action failed: {type(error).__name__}: {error}", "error")
        st.rerun()
        return
    if isinstance(result, tuple):
        changed, message = result
    else:
        changed, message = True, result
    if changed:
        # Only record history for actions that actually changed the layout.
        storage.push_undo(
            st.session_state, DashboardConfig.from_json(before), namespace=namespace
        )
        _commit(config, message or "Dashboard updated.")
    else:
        _flash(message or "That action made no change.", "warning")
        st.rerun()


def _missing_columns(config: DashboardConfig, schema: DatasetSchema) -> list[str]:
    """Columns/roles referenced by a dashboard that the current dataset lacks."""
    used: set[str] = set()
    for page in config.pages:
        for component in page.components:
            for column in (component.dimension, component.measure, component.measure_y):
                if column:
                    used.add(column)
            if component.kpi_role and component.kpi_role not in DERIVED_KPI_ROLES:
                used.add(schema.roles.get(component.kpi_role, f"role:{component.kpi_role}"))
    return sorted(column for column in used if column not in schema.columns)


def _add_component_to_page(page, component: Component) -> str:
    page.add(component)
    return f"Added '{component.title}'."


def _move_visual(page, component_id: str, offset: int) -> tuple[bool, str]:
    if page is None:
        return False, "The page no longer exists."
    if page.move(component_id, offset):
        return True, "Moved the visual up." if offset < 0 else "Moved the visual down."
    return False, ("The visual is already first." if offset < 0 else "The visual is already last.")


def _move_visual_top(page, component_id: str) -> tuple[bool, str]:
    if page is None:
        return False, "The page no longer exists."
    if page.move_to_top(component_id):
        return True, "Moved the visual to the top."
    return False, "The visual is already at the top."


def _duplicate_visual(page, component_id: str) -> tuple[bool, str]:
    if page is None:
        return False, "The page no longer exists."
    clone = page.duplicate(component_id)
    if clone is None:
        return False, "That visual no longer exists."
    return True, f"Duplicated the visual as '{clone.title}'."


def _delete_visual(page, component_id: str) -> tuple[bool, str]:
    if page is None:
        return False, "The page no longer exists."
    if page.remove(component_id):
        return True, "Deleted the visual."
    return False, "That visual no longer exists."


def _visual_options(schema: DatasetSchema) -> tuple[list[str], list[str]]:
    return (
        ["(none)", *[column for column in schema.dimensions if column in schema.columns]],
        ["(none)", *[column for column in schema.measures if column in schema.columns]],
    )


def _render_builder(config: DashboardConfig, schema: DatasetSchema, page_name: str, identity: str) -> None:
    page = config.page(page_name) or config.add_page(page_name)
    ui.section_label("Data fields")
    with st.expander("Fields & roles", expanded=False):
        st.caption(f"{len(schema.measures)} measure(s) · {len(schema.dimensions)} dimension(s)")
        for role, column in schema.roles.items():
            st.caption(f"**{ROLE_LABELS.get(role, role.title())}:** {column}")

    ui.section_label("Visualizations")
    dimensions, measures = _visual_options(schema)
    with st.form(f"rm_add_visual_{identity}", clear_on_submit=True):
        visual = st.selectbox(
            "Visual type",
            [
                "KPI card", "Bar chart", "Line chart", "Area chart", "Pie chart", "Donut chart",
                "Scatter plot", "Histogram", "Table", "Matrix",
            ],
            key=f"rm_add_type_{identity}",
        )
        title = st.text_input("Title", key=f"rm_add_title_{identity}", placeholder="Optional title")
        dimension = st.selectbox("Dimension (group by)", dimensions, key=f"rm_add_dim_{identity}")
        measure = st.selectbox("Measure", measures, key=f"rm_add_measure_{identity}")
        measure_y = st.selectbox("Second measure (scatter)", measures, key=f"rm_add_measure_y_{identity}")
        aggregation = st.selectbox("Aggregation", list(AGGREGATIONS), key=f"rm_add_agg_{identity}")
        top_n = st.number_input("Top N", min_value=1, max_value=100, value=10, key=f"rm_add_topn_{identity}")
        width = st.slider("Width (12-column grid)", 1, 12, 6, key=f"rm_add_width_{identity}")
        height = st.slider("Height (px)", 180, 900, 320, step=20, key=f"rm_add_height_{identity}")
        color = st.color_picker("Chart colour", "#7c5cff", key=f"rm_add_colour_{identity}")
        add_clicked = st.form_submit_button("Add visual", width="stretch")

    if add_clicked:
        dim = None if dimension == "(none)" else dimension
        chosen_measure = None if measure == "(none)" else measure
        second_measure = None if measure_y == "(none)" else measure_y
        if visual == "KPI card":
            if not chosen_measure:
                st.warning("Choose a measure for the KPI card.")
            else:
                label = f"Total {schema.label_for(chosen_measure)}"
                component = Component(
                    type="kpi", title=title or label, kpi_role="measure_sum", measure=chosen_measure,
                    aggregation=aggregation, format=_format_for_measure(schema, chosen_measure), width=3, height=180,
                )
                _mutate(config, lambda cfg: _add_component_to_page(cfg.page(page_name), component))
        elif visual == "Scatter plot":
            if not chosen_measure or not second_measure:
                st.warning("A scatter plot needs two measures.")
            elif chosen_measure == second_measure:
                st.warning("Choose two different measures for a scatter plot.")
            else:
                component = Component(
                    type="scatter", title=title or f"{schema.label_for(chosen_measure)} vs {schema.label_for(second_measure)}",
                    dimension=dim, measure=chosen_measure, measure_y=second_measure, width=width, height=height,
                    color=color,
                )
                _mutate(config, lambda cfg: _add_component_to_page(cfg.page(page_name), component))
        elif visual == "Histogram":
            if not chosen_measure:
                st.warning("A histogram needs a numeric measure.")
            else:
                component = Component(
                    type="histogram", title=title or f"Distribution of {schema.label_for(chosen_measure)}",
                    measure=chosen_measure, width=width, height=height, color=color,
                )
                _mutate(config, lambda cfg: _add_component_to_page(cfg.page(page_name), component))
        elif visual in ("Table", "Matrix"):
            if not dim and not chosen_measure:
                st.warning("A table needs a dimension or a measure.")
            else:
                component = Component(
                    type="matrix" if visual == "Matrix" else "table",
                    title=title or f"{schema.label_for(dim or chosen_measure)} table",
                    dimension=dim, measure=chosen_measure, aggregation=aggregation,
                    width=12, height=height,
                )
                _mutate(config, lambda cfg: _add_component_to_page(cfg.page(page_name), component))
        else:
            type_map = {
                "Bar chart": "bar", "Line chart": "line", "Area chart": "area",
                "Pie chart": "pie", "Donut chart": "donut",
            }
            chart_type = type_map[visual]
            if not dim and not chosen_measure:
                st.warning("A chart needs at least one dataset column.")
            else:
                if chart_type in ("line", "area") and not (dim and dim in schema.dates):
                    dim = schema.role_column("date") or dim
                component = Component(
                    type=chart_type,
                    title=title or (
                        f"{schema.label_for(chosen_measure)} by {schema.label_for(dim)}"
                        if chosen_measure and dim else f"{schema.label_for(chosen_measure or dim or 'Records')}"
                    ),
                    dimension=dim, measure=chosen_measure, aggregation=aggregation,
                    top_n=int(top_n), width=width, height=height, color=color,
                )
                _mutate(config, lambda cfg: _add_component_to_page(cfg.page(page_name), component))

    ui.section_label("Selected visual")
    if not page.components:
        st.caption("This page has no visuals yet.")
    else:
        labels = {f"{component.title} ({component.id})": component.id for component in page.components}
        select_key = f"rm_selected_{identity}_{page_name}"
        focus = st.session_state.pop(f"rm_focus_{identity}", None)
        if focus:
            focused_label = next((label for label, component_id in labels.items() if component_id == focus), None)
            if focused_label:
                st.session_state[select_key] = focused_label
        elif st.session_state.get(select_key) not in labels:
            # The previously selected visual was deleted or the page changed.
            st.session_state.pop(select_key, None)
        selected_label = st.selectbox("Edit visual", list(labels), key=select_key)
        selected_id = labels[selected_label]
        st.session_state[f"rm_selected_id_{identity}"] = selected_id
        component = page.get(selected_id)
        if component is not None:
            edit_suffix = f"{identity}_{selected_id}"
            with st.form(f"rm_edit_visual_{identity}"):
                new_title = st.text_input("Title", value=component.title, key=f"rm_edit_title_{edit_suffix}")
                new_type = st.selectbox(
                    "Visual type",
                    ["kpi", *CHART_TYPES, "insights", "profile_table", "missing_bar"],
                    index=["kpi", *CHART_TYPES, "insights", "profile_table", "missing_bar"].index(component.type)
                    if component.type in ["kpi", *CHART_TYPES, "insights", "profile_table", "missing_bar"] else 0,
                    key=f"rm_edit_type_{edit_suffix}",
                )
                new_dimension = st.selectbox(
                    "Dimension", dimensions,
                    index=dimensions.index(component.dimension) if component.dimension in dimensions else 0,
                    key=f"rm_edit_dim_{edit_suffix}",
                )
                new_measure = st.selectbox(
                    "Measure", measures,
                    index=measures.index(component.measure) if component.measure in measures else 0,
                    key=f"rm_edit_measure_{edit_suffix}",
                )
                new_aggregation = st.selectbox(
                    "Aggregation", list(AGGREGATIONS),
                    index=list(AGGREGATIONS).index(component.aggregation) if component.aggregation in AGGREGATIONS else 0,
                    key=f"rm_edit_agg_{edit_suffix}",
                )
                new_width = st.slider("Width", 1, 12, component.width, key=f"rm_edit_width_{edit_suffix}")
                new_height = st.slider("Height", 180, 900, component.height, step=20, key=f"rm_edit_height_{edit_suffix}")
                new_colour = st.color_picker("Colour", component.color or "#7c5cff", key=f"rm_edit_colour_{edit_suffix}")
                saved = st.form_submit_button("Save visual", width="stretch")
            if saved:
                def _update(cfg: DashboardConfig) -> tuple[bool, str]:
                    target = cfg.component(selected_id)
                    if target is None:
                        return False, "That visual no longer exists."
                    target.title = new_title or target.title
                    target.type = new_type
                    target.dimension = None if new_dimension == "(none)" else new_dimension
                    target.measure = None if new_measure == "(none)" else new_measure
                    target.aggregation = new_aggregation
                    target.width = int(new_width)
                    target.height = int(new_height)
                    target.color = new_colour
                    return True, f"Updated '{target.title}'."
                _mutate(config, _update)
            positions = st.columns(2)
            if positions[0].button("Move up", key=f"rm_move_up_{identity}", width="stretch"):
                _mutate(config, lambda cfg: _move_visual(cfg.page(page_name), selected_id, -1))
            if positions[1].button("Move down", key=f"rm_move_down_{identity}", width="stretch"):
                _mutate(config, lambda cfg: _move_visual(cfg.page(page_name), selected_id, 1))
            positions = st.columns(2)
            if positions[0].button("Move to top", key=f"rm_move_top_{identity}", width="stretch"):
                _mutate(config, lambda cfg: _move_visual_top(cfg.page(page_name), selected_id))
            if positions[1].button("Duplicate", key=f"rm_duplicate_{identity}", width="stretch"):
                _mutate(config, lambda cfg: _duplicate_visual(cfg.page(page_name), selected_id))
            confirm_delete = st.checkbox("Confirm delete", key=f"rm_confirm_delete_{identity}")
            if st.button("Delete visual", key=f"rm_delete_{identity}", width="stretch", disabled=not confirm_delete):
                _mutate(config, lambda cfg: _delete_visual(cfg.page(page_name), selected_id))

    ui.section_label("Pages")
    with st.expander("Manage report pages", expanded=False):
        with st.form(f"rm_add_page_{identity}", clear_on_submit=True):
            new_page = st.text_input("New page name", key=f"rm_new_page_name_{identity}")
            create_page = st.form_submit_button("Add page", width="stretch")
        if create_page:
            name = new_page.strip()
            if not name:
                st.warning("Enter a page name.")
            elif config.page(name):
                st.warning("That page already exists.")
            else:
                def _create_page(cfg: DashboardConfig) -> tuple[bool, str]:
                    created = cfg.add_page(name)
                    st.session_state[f"rm_page_{identity}"] = created.name
                    return True, f"Created the '{created.name}' page."
                _mutate(config, _create_page)
        if config.pages:
            page_names = config.page_names()
            manage_key = f"rm_manage_page_{identity}"
            if st.session_state.get(manage_key) not in page_names:
                # The managed page was renamed or deleted.
                st.session_state.pop(manage_key, None)
            chosen = st.selectbox(
                "Page to manage", page_names,
                index=page_names.index(page_name) if page_name in page_names else 0,
                key=manage_key,
            )
            with st.form(f"rm_rename_page_{identity}"):
                renamed = st.text_input(
                    "Rename page",
                    value=chosen,
                    key=f"rm_rename_page_name_{identity}_{chosen}",
                )
                rename_clicked = st.form_submit_button("Rename page", width="stretch")
            if rename_clicked:
                new_name = renamed.strip()
                if not new_name:
                    st.warning("Enter a new page name.")
                elif new_name == chosen:
                    st.info("Enter a different name to rename the page.")
                elif config.page(new_name):
                    st.warning("That page name already exists.")
                else:
                    def _rename_page(cfg: DashboardConfig) -> tuple[bool, str]:
                        if not cfg.rename_page(chosen, new_name):
                            return False, f"Could not rename the '{chosen}' page."
                        if st.session_state.get(f"rm_page_{identity}") == chosen:
                            st.session_state[f"rm_page_{identity}"] = new_name
                        return True, f"Renamed '{chosen}' to '{new_name}'."
                    _mutate(config, _rename_page)
            page_actions = st.columns(2)
            if page_actions[0].button("Move left", key=f"rm_page_left_{identity}", width="stretch"):
                _mutate(
                    config,
                    lambda cfg: (
                        (True, f"Moved the '{chosen}' page left.")
                        if cfg.move_page(chosen, -1)
                        else (False, f"'{chosen}' is already the first page.")
                    ),
                )
            if page_actions[1].button("Move right", key=f"rm_page_right_{identity}", width="stretch"):
                _mutate(
                    config,
                    lambda cfg: (
                        (True, f"Moved the '{chosen}' page right.")
                        if cfg.move_page(chosen, 1)
                        else (False, f"'{chosen}' is already the last page.")
                    ),
                )
            page_actions = st.columns(2)
            if page_actions[0].button("Duplicate page", key=f"rm_page_duplicate_{identity}", width="stretch"):
                def _duplicate_page(cfg: DashboardConfig) -> tuple[bool, str]:
                    clone = cfg.duplicate_page(chosen)
                    if clone is None:
                        return False, f"The '{chosen}' page no longer exists."
                    return True, f"Duplicated '{chosen}' as '{clone.name}'."
                _mutate(config, _duplicate_page)
            confirm_page_delete = st.checkbox("Confirm page delete", key=f"rm_confirm_page_delete_{identity}")
            if st.button(
                "Delete page",
                key=f"rm_page_delete_{identity}",
                width="stretch",
                disabled=not confirm_page_delete,
            ):
                def _remove_page(cfg: DashboardConfig) -> tuple[bool, str]:
                    if not cfg.remove_page(chosen):
                        return False, "At least one page must remain."
                    st.session_state[f"rm_page_{identity}"] = cfg.pages[0].name
                    return True, f"Deleted the '{chosen}' page."
                _mutate(config, _remove_page)

    ui.section_label("Appearance")
    with st.expander("Theme & typography", expanded=False):
        font_options = ["Inter, Segoe UI, sans-serif", "Segoe UI, sans-serif", "Georgia, serif", "Consolas, monospace"]
        theme_key = f"rm_theme_select_{identity}"
        accent_key = f"rm_theme_accent_{identity}"
        font_key = f"rm_theme_font_{identity}"
        theme_signature = (config.theme.preset, config.theme.accent, config.theme.font)
        signature_key = f"rm_theme_signature_{identity}"
        if st.session_state.get(signature_key) != theme_signature:
            # The configuration changed externally (undo, restore, assistant or
            # dataset switch). Reset the widgets so they pick up the new values
            # without clobbering an in-progress user selection.
            st.session_state[signature_key] = theme_signature
            st.session_state.pop(theme_key, None)
            st.session_state.pop(accent_key, None)
            st.session_state.pop(font_key, None)
        preset = st.selectbox(
            "Theme", list(THEME_PRESETS),
            index=list(THEME_PRESETS).index(config.theme.preset) if config.theme.preset in THEME_PRESETS else 0,
            key=theme_key,
        )
        accent = st.color_picker("Accent colour", config.theme.accent, key=accent_key)
        font = st.selectbox(
            "Font", font_options,
            index=font_options.index(config.theme.font) if config.theme.font in font_options else 0,
            key=font_key,
        )
        if st.button("Apply appearance", key=f"rm_apply_theme_{identity}", width="stretch"):
            def _theme(cfg: DashboardConfig) -> str:
                cfg.theme.preset = preset
                cfg.theme.accent = accent
                cfg.theme.font = font
                cfg.theme.palette = list(PALETTES.get(preset, PALETTES["dark"]))
                st.session_state["rm_theme_preset"] = preset
                st.session_state["rm_accent"] = accent
                return "Appearance updated."
            _mutate(config, _theme)

    ui.section_label("Save & history")
    with st.expander("Save, undo and restore", expanded=False):
        history = st.columns(2)
        if history[0].button(
            "Undo",
            key=f"rm_undo_{identity}",
            width="stretch",
            disabled=not storage.can_undo(st.session_state, namespace=identity),
        ):
            previous = storage.undo(st.session_state, config, namespace=identity)
            if previous is None:
                _flash("There is nothing to undo for this dataset.", "warning")
                st.rerun()
            else:
                previous.dataset_id = identity
                st.session_state[_config_key(identity)] = previous
                _flash("Undid the last dashboard change.", "success")
                st.rerun()
        if history[1].button(
            "Redo",
            key=f"rm_redo_{identity}",
            width="stretch",
            disabled=not storage.can_redo(st.session_state, namespace=identity),
        ):
            following = storage.redo(st.session_state, config, namespace=identity)
            if following is None:
                _flash("There is nothing to redo for this dataset.", "warning")
                st.rerun()
            else:
                following.dataset_id = identity
                st.session_state[_config_key(identity)] = following
                _flash("Redid the dashboard change.", "success")
                st.rerun()
        if st.button("Save dashboard now", key=f"rm_save_{identity}", width="stretch"):
            try:
                path = storage.save_dashboard(config)
            except OSError as error:
                st.error(f"Could not save the dashboard: {error}")
            else:
                st.success(f"Saved '{config.name}' to {path.name}.")
        if st.button("Autosave now", key=f"rm_autosave_{identity}", width="stretch"):
            try:
                path = storage.autosave(config)
            except OSError as error:
                st.error(f"Could not write the autosave file: {error}")
            else:
                st.success(f"Autosave written to {path.name}.")
        if st.button("Save as new dashboard", key=f"rm_save_as_{identity}", width="stretch"):
            clone = config.clone()
            try:
                path = storage.save_dashboard(clone)
            except OSError as error:
                st.error(f"Could not save the copy: {error}")
            else:
                st.success(f"Saved a copy as '{clone.name}' ({path.name}).")
        with st.form(f"rm_rename_dashboard_{identity}"):
            dashboard_name = st.text_input("Dashboard name", value=config.name, key=f"rm_dashboard_name_{identity}")
            rename_clicked = st.form_submit_button("Rename dashboard", width="stretch")
        if rename_clicked:
            new_dashboard_name = dashboard_name.strip()[:120]
            if not new_dashboard_name:
                st.warning("Enter a dashboard name.")
            elif new_dashboard_name == config.name:
                st.info("Enter a different name to rename the dashboard.")
            else:
                config.name = new_dashboard_name
                _commit(config, f"Dashboard renamed to '{new_dashboard_name}'.")

        confirm_reset = st.checkbox(
            "I understand this replaces the current layout",
            key=f"rm_confirm_reset_{identity}",
        )
        if st.button(
            "Reset to original auto dashboard",
            key=f"rm_reset_{identity}",
            width="stretch",
            disabled=not confirm_reset,
        ):
            original = st.session_state.get(_original_key(identity))
            if not original:
                _flash(
                    "The original auto dashboard is not available in this session. "
                    "Switch the cleaning options or re-upload to regenerate it.",
                    "warning",
                )
                st.rerun()
            else:
                restored_original = DashboardConfig.from_json(original)
                restored_original.dataset_id = identity
                st.session_state[_config_key(identity)] = restored_original
                storage.clear_history(st.session_state, namespace=identity)
                _flash("Restored the original auto-generated dashboard.", "success")
                st.rerun()

        saved = storage.list_dashboards()
        if saved:
            options = {f"{entry['name']} · {entry['updated_at'][:19]}": entry["path"] for entry in saved[:25]}
            restore_key = f"rm_restore_select_{identity}"
            if st.session_state.get(restore_key) not in options:
                st.session_state.pop(restore_key, None)
            restored = st.selectbox("Restore a saved dashboard", list(options), key=restore_key)
            confirm_restore = st.checkbox(
                "I understand this overwrites the current layout",
                key=f"rm_confirm_restore_{identity}",
            )
            if st.button(
                "Restore selected dashboard",
                key=f"rm_restore_{identity}",
                width="stretch",
                disabled=not confirm_restore,
            ):
                try:
                    loaded = storage.load_dashboard(options[restored])
                except (OSError, ValueError, json.JSONDecodeError) as error:
                    _flash(f"Could not load that dashboard: {error}", "error")
                    st.rerun()
                else:
                    missing = _missing_columns(loaded, schema)
                    if missing:
                        _flash(
                            "That saved dashboard references columns that are not in the current dataset: "
                            + ", ".join(missing),
                            "error",
                        )
                        st.rerun()
                    else:
                        loaded.dataset_id = identity
                        st.session_state[_config_key(identity)] = loaded
                        storage.clear_history(st.session_state, namespace=identity)
                        _flash(f"Restored the saved dashboard '{loaded.name}'.", "success")
                        st.rerun()
        else:
            st.caption("No saved dashboards yet. Use 'Save dashboard now' to create one.")
        st.caption("Autosave is on. Dashboards store layout definitions only, never the uploaded dataset.")


# ---------------------------------------------------------------------------
# AI panels
# ---------------------------------------------------------------------------
def _pending_action(action: AssistantAction) -> dict[str, Any]:
    return action.__dict__


def _apply_assistant_action(
    config: DashboardConfig,
    action: AssistantAction,
    schema: DatasetSchema,
    page_name: str,
    identity: str,
    frame: pd.DataFrame,
) -> None:
    """Apply one validated assistant action and always leave clear feedback."""
    if action.action == "reset_dashboard":
        original = st.session_state.get(_original_key(identity))
        if original:
            restored = DashboardConfig.from_json(original)
        else:
            restored = build_dashboard(
                frame, schema, config.dataset_name or config.name, identity, dashboard_name=config.name
            )
        restored.dataset_id = identity
        st.session_state[_config_key(identity)] = restored
        storage.clear_history(st.session_state, namespace=identity)
        _flash("Reset the dashboard to the generated layout.", "success")
        st.rerun()
        return
    before = config.to_json()
    new_config, message = apply_action(config, action, schema, active_page=page_name)
    if new_config.to_json() == before:
        _flash(message or "That command made no change.", "warning")
        st.rerun()
        return
    storage.push_undo(st.session_state, DashboardConfig.from_json(before), namespace=identity)
    _commit(new_config, message)


def _render_assistant(
    config: DashboardConfig,
    schema: DatasetSchema,
    page_name: str,
    identity: str,
    provider,
    frame: pd.DataFrame,
) -> None:
    st.caption(
        "Commands are converted into a strict allowlist of dashboard actions and validated against the "
        "uploaded columns before anything changes."
    )
    command = st.text_input(
        "Dashboard command",
        key=f"rm_assistant_command_{identity}",
        placeholder="e.g. Add a total profit KPI, create a sales bar chart, change the theme to light",
    )
    use_llm = st.checkbox(
        "Use the configured AI model to parse commands when rule-based parsing is unsure",
        value=False,
        key=f"rm_assistant_llm_{identity}",
        help="Only allowlisted actions are accepted. The model cannot invent columns.",
    )
    selected_component_id = st.session_state.get(f"rm_selected_id_{identity}")
    if st.button("Apply command", key=f"rm_assistant_apply_{identity}", width="stretch"):
        if not command.strip():
            st.warning("Enter a dashboard command.")
            return
        action = parse_command(command, config, schema, selected_component_id)
        if not action.valid and use_llm and provider is not None and provider.available:
            llm_action = parse_with_llm(command, config, schema, provider, selected_component_id)
            if llm_action is not None:
                action = llm_action
        if not action.valid:
            st.warning(action.error)
            if action.suggestions:
                st.caption("Try: " + " · ".join(action.suggestions))
            return
        if action.destructive:
            st.session_state[f"rm_pending_{identity}"] = _pending_action(action)
            st.warning(f"Confirmation required: {action.description}")
        else:
            _apply_assistant_action(config, action, schema, page_name, identity, frame)

    pending = st.session_state.get(f"rm_pending_{identity}")
    if pending:
        action = AssistantAction(**pending)
        st.info(f"Please confirm: {action.description}")
        confirm, cancel = st.columns(2)
        if confirm.button("Confirm action", key=f"rm_confirm_action_{identity}", type="primary", width="stretch"):
            st.session_state.pop(f"rm_pending_{identity}", None)
            _apply_assistant_action(config, action, schema, page_name, identity, frame)
        if cancel.button("Cancel", key=f"rm_cancel_action_{identity}", width="stretch"):
            st.session_state.pop(f"rm_pending_{identity}", None)
            _flash("Cancelled the pending dashboard command.", "info")
            st.rerun()
    st.caption("Examples: “Add a total profit KPI” · “Show the top 10 products by revenue” · “Create a customer analysis page” · “Change this bar chart into a pie chart”.")


def _render_chatbot(frame: pd.DataFrame, schema: DatasetSchema, identity: str, provider) -> None:
    st.caption(
        "Answers are computed with pandas on the active filtered data. The AI model, when configured, "
        "may only add a narrative around verified results."
    )
    messages = st.session_state.setdefault(f"rm_chat_{identity}", [])
    history_records = st.session_state.setdefault(f"rm_chat_history_{identity}", [])
    with st.form(f"rm_chat_form_{identity}", clear_on_submit=True):
        question = st.text_input("Ask a business question", key=f"rm_chat_question_{identity}")
        submitted = st.form_submit_button("Ask", width="stretch")
    if submitted and not question.strip():
        st.warning("Enter a business question before asking.")
    elif submitted:
        response = answer_question(question, frame, schema, history_records, provider)
        history_records.append(response.history_record())
        st.session_state[f"rm_chat_history_{identity}"] = history_records[-20:]
        messages.append(
            {
                "role": "user",
                "text": question.strip(),
            }
        )
        messages.append(
            {
                "role": "assistant",
                "text": response.text,
                "table": response.table,
                "chart": response.chart.to_dict() if response.chart else None,
                "verified": response.verified,
                "note": response.note,
                "followups": response.followups,
            }
        )
        st.session_state[f"rm_chat_{identity}"] = messages[-30:]

    if not messages:
        st.caption("Suggested questions: " + " · ".join(suggested_questions(schema)))
    for message in messages:
        if message["role"] == "user":
            st.markdown(
                f"<div class='rm-chat-user'>{html.escape(str(message['text']))}</div>",
                unsafe_allow_html=True,
            )
            continue
        st.markdown(
            f"<div class='rm-chat-assistant'>{html.escape(str(message['text']))}</div>",
            unsafe_allow_html=True,
        )
        table = message.get("table")
        if isinstance(table, pd.DataFrame) and not table.empty:
            st.dataframe(table, width="stretch", hide_index=True)
        chart = message.get("chart")
        if chart:
            try:
                component = Component.from_dict(chart)
                render_component(frame, component, schema, _current_theme(), dataset_id=identity, key_prefix="chat")
            except Exception:
                logger.exception("Could not render the chat chart")
        meta = "Verified pandas calculation" if message.get("verified", True) else "Unverified"
        if message.get("note"):
            meta += f" · {message['note']}"
        st.markdown(f"<div class='rm-chat-meta'>{html.escape(meta)}</div>", unsafe_allow_html=True)
        if message.get("followups"):
            st.caption("Try: " + " · ".join(message["followups"]))
    if messages and st.button("Clear conversation", key=f"rm_chat_clear_{identity}"):
        st.session_state[f"rm_chat_{identity}"] = []
        st.session_state[f"rm_chat_history_{identity}"] = []
        _flash("Cleared the chat conversation.", "success")
        st.rerun()


def _render_rag(identity: str, provider) -> None:
    st.caption(
        "Document answers are separate from dataset calculations. Sources are cited, and the system "
        "refuses to answer when the uploaded documents do not contain the information."
    )
    store: RAGStore = st.session_state.setdefault("rm_rag_store", RAGStore())
    uploads = st.file_uploader(
        "Upload business documents (PDF, TXT, Markdown, JSON, DOCX)",
        type=["pdf", "txt", "md", "markdown", "json", "docx"],
        accept_multiple_files=True,
        key="rm_docs_uploader",
    )
    if st.button("Index documents", key=f"rm_index_docs_{identity}", width="stretch"):
        if not uploads:
            st.warning("Choose at least one document to index.")
        else:
            with st.spinner("Extracting and indexing documents…"):
                for upload in uploads:
                    try:
                        count = store.add_document(upload.name, upload.getvalue(), provider)
                        st.success(f"Indexed '{upload.name}' into {count} chunk(s).")
                    except RAGError as error:
                        st.error(f"{upload.name}: {error}")
                    except Exception as error:
                        logger.exception("Document indexing failed")
                        st.error(f"{upload.name}: the document could not be indexed ({type(error).__name__}).")
            st.session_state["rm_rag_store"] = store
    if store.documents:
        st.caption("Indexed documents: " + ", ".join(f"{name} ({info['chunks']} chunks)" for name, info in store.documents.items()))
        confirm_clear = st.checkbox(
            "I understand this removes every indexed document",
            key=f"rm_confirm_clear_docs_{identity}",
        )
        if st.button(
            "Clear knowledge base",
            key=f"rm_clear_docs_{identity}",
            width="stretch",
            disabled=not confirm_clear,
        ):
            store.clear()
            st.session_state["rm_rag_store"] = store
            _flash("Cleared the knowledge base.", "success")
            st.rerun()
        with st.form(f"rm_rag_form_{identity}", clear_on_submit=True):
            question = st.text_input("Ask the documents", key=f"rm_rag_question_{identity}")
            asked = st.form_submit_button("Ask documents", width="stretch")
        if asked and not question.strip():
            st.warning("Enter a question about the indexed documents.")
        elif asked:
            with st.spinner("Retrieving relevant passages…"):
                answer = store.answer(question.strip(), provider)
            st.markdown(answer.text)
            if answer.note:
                st.caption(answer.note)
            if answer.sources:
                st.markdown("**Sources**")
                for source in answer.sources:
                    st.caption(f"- {source.label()}")
    else:
        st.info("No documents indexed yet. PDF support requires the optional `pypdf` package; DOCX requires `python-docx`.")


def render_ai_panels(config, schema, frame, page_name, identity, provider) -> None:
    st.subheader("AI workspace")
    status = provider.config.public_status()
    st.caption(status["message"])
    assistant_tab, chat_tab, rag_tab = st.tabs(["Dashboard assistant", "Business chatbot", "Knowledge documents"])
    with assistant_tab:
        _render_assistant(config, schema, page_name, identity, provider, frame)
    with chat_tab:
        _render_chatbot(frame, schema, identity, provider)
    with rag_tab:
        _render_rag(identity, provider)


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------
def _recommendations(insights) -> list[str]:
    """Rule-based next steps derived strictly from verified insight evidence."""
    recommendations: list[str] = []
    titles = {insight.title for insight in insights}
    if "Loss-making records" in titles:
        recommendations.append("Review the loss-making records before applying further discounts or cost changes.")
    if "Concentration risk" in titles:
        recommendations.append("Reduce concentration risk by reviewing the largest contributors and broadening the base.")
    if "Recent movement" in titles:
        recommendations.append("Investigate the latest period movement using the trend chart and the underlying filtered rows.")
    if "Margin watchlist" in titles:
        recommendations.append("Review pricing and discount policy for high-revenue, below-median-margin records.")
    if "Expense ratio" in titles:
        recommendations.append("Compare the expense ratio with budget and investigate the largest expense groups.")
    if "Data completeness" in titles:
        recommendations.append("Improve data completeness before relying on totals for these fields.")
    if not recommendations:
        recommendations.append("No action is implied by the current data; continue monitoring the verified KPIs.")
    return recommendations


def render_insights_panel(frame, schema, identity: str | None = None) -> list[Any]:
    insights = insights_for_frame(frame, schema, identity)
    with st.expander("AI business insights & recommendations", expanded=False):
        if not insights:
            st.info("Not enough data is available to generate verified insights.")
            return insights
        render_insights(frame, schema, key="insights_panel")
        st.markdown("**Suggested next steps**")
        for recommendation in _recommendations(insights):
            st.markdown(f"- {recommendation}")
        st.caption("Insights are deterministic calculations. Suggestions are not causal claims.")
    return insights


def insights_for_frame(frame: pd.DataFrame, schema: DatasetSchema, identity: str | None = None) -> list[Any]:
    """Cached deterministic insight generation (same frame ⇒ same insights)."""
    if frame is None or frame.empty:
        return []
    parts = [_frame_signature(frame)]
    if identity:
        parts.append(identity)
    return _cached_result(
        "rm_perf_insights_" + "_".join(parts),
        lambda: list(generate_insights(frame, schema)),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ui.setup_page()
    ui.inject_css(_current_theme())
    st.title("RetailMind AI")
    ui.render_brand()

    if "rm_accent" not in st.session_state:
        st.session_state["rm_accent"] = PALETTES["dark"][0]

    # The brand card already renders the product name, logo and tagline.
    # Do not repeat them as a second heading (avoids duplicate headers/space).
    _render_flash()

    provider = get_provider()
    config: DashboardConfig | None = None

    # A removal request must clear the uploader before the widget is created.
    if st.session_state.pop(CLEAR_UPLOAD_KEY, False):
        st.session_state.pop("data_upload_999", None)

    with st.sidebar:
        st.header("Upload CSV or Excel")
        upload = st.file_uploader(
            "Choose a CSV, XLSX, XLS, or XLSM file",
            key="data_upload_999",
            help="Android Chrome: select any file — the app validates the extension and contents after upload.",
        )
        if upload is None:
            st.info("Upload a file to generate the dashboard automatically, or open the AI workspace below once data is loaded.")
            st.markdown(
                "<div class='rm-muted' style='font-size:0.78rem'>Supported: CSV, Excel, multiple worksheets. "
                "Maximum size: 25 MB. Files are processed in memory.</div>",
                unsafe_allow_html=True,
            )
            if "rm_rag_store" not in st.session_state:
                st.session_state["rm_rag_store"] = RAGStore()
            return

        if upload.size == 0:
            st.error("The uploaded file is empty.")
            return
        if upload.size > MAX_UPLOAD_BYTES:
            st.error("Upload a file smaller than 25 MB.")
            return

        content, filename = upload.getvalue(), upload.name
        st.caption(f"**File:** {filename} · {upload.size / 1024:.1f} KB")

        # Validate file extension server-side.  Android Chrome may report
        # different MIME types or none at all; never reject based on MIME type
        # alone — always fall back to the filename extension.
        suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if suffix not in SUPPORTED_EXTENSIONS:
            st.error(
                f"Unsupported file type '{suffix or 'none'}'. "
                f"Please upload one of: {', '.join(SUPPORTED_EXTENSIONS)}."
            )
            return

        sheet_name = None
        try:
            if filename.lower().endswith((".xlsx", ".xls", ".xlsm")):
                sheets = inspect_excel_worksheets(content)
                names = [sheet["name"] for sheet in sheets]
                if not names:
                    st.error("The uploaded workbook contains no worksheets.")
                    return
                preferred = preferred_excel_worksheet(content)
                sheet_key = "upload_worksheet_" + hashlib.sha256(content).hexdigest()[:16]
                sheet_name = st.selectbox(
                    "Worksheet", names, index=names.index(preferred) if preferred in names else 0,
                    key=sheet_key,
                )
            duplicates = duplicate_source_columns(content, filename, sheet_name)
            if duplicates:
                st.error(
                    "Duplicate column name(s) detected: "
                    + ", ".join(duplicates)
                    + ". Rename the columns and upload the file again."
                )
                return
            source = _read_source(content, filename, sheet_name)
        except ValueError as error:
            st.error(str(error))
            return
        except Exception as error:  # defensive: never leak a traceback to the UI
            logger.exception("Failed to read uploaded file")
            st.error(f"Could not read '{filename}'. Check that it is a valid, readable file ({type(error).__name__}).")
            return

        if source.empty and not len(source.columns):
            st.error("The uploaded file has no readable columns.")
            return

        identity = _identity(content, filename, sheet_name)
        if st.button("Remove uploaded dataset", key="rm_remove_dataset", width="stretch"):
            for key in (
                _config_key(identity),
                _original_key(identity),
                f"rm_manual_schema_{identity}",
                f"rm_rebuild_{identity}",
                f"rm_selected_id_{identity}",
                f"rm_page_{identity}",
                f"rm_manage_page_{identity}",
                f"rm_pending_{identity}",
                f"rm_focus_{identity}",
                f"rm_clean_signature_{identity}",
                f"rm_confirm_delete_{identity}",
                f"rm_confirm_page_delete_{identity}",
                f"rm_confirm_reset_{identity}",
                f"rm_confirm_restore_{identity}",
            ):
                st.session_state.pop(key, None)
            _purge_dataset_cache(identity)
            storage.clear_history(st.session_state, namespace=identity)
            st.session_state[CLEAR_UPLOAD_KEY] = True
            _flash("Removed the uploaded dataset from this session.", "success")
            st.rerun()
        mapping = detect_column_mapping(source.columns)
        retail_compatible = bool(mapping.get("sales"))

        # Canonical preparation + schema + cleaning advice are computed once per
        # upload. They used to be recomputed on every Streamlit rerun, which made
        # every click on a page/filter cost a full parse of the dataset.
        analysis_key = f"rm_source_analysis_{identity}"
        cached_analysis = st.session_state.get(analysis_key)
        if cached_analysis is None:
            analysis_base = source
            legacy_summary: dict[str, Any] = {}
            if retail_compatible:
                try:
                    analysis_base, legacy_summary = clean_uploaded_data(source, mapping)
                except (ValueError, KeyError):
                    retail_compatible = False
                    analysis_base = source
                    legacy_summary = {}
            base_schema = infer_schema(analysis_base)
            suggestions = analyse_cleaning(analysis_base, base_schema)
            cached_analysis = (analysis_base, base_schema, suggestions, legacy_summary, retail_compatible)
            st.session_state[analysis_key] = cached_analysis
        analysis_base, base_schema, suggestions, legacy_summary, retail_compatible = cached_analysis

        options = _render_cleaning_controls(identity)
        clean_signature = _cleaning_signature(options)
        cached_prep_key = f"rm_prepared_{identity}_{clean_signature}"
        if cached_prep_key in st.session_state:
            cleaned, auto_schema, cleaning_report, retail_compatible = st.session_state[cached_prep_key]
        else:
            cleaned, auto_schema, cleaning_report, retail_compatible = _prepare_dataset(
                source,
                mapping,
                options,
                analysis_base=analysis_base,
                base_schema=base_schema,
                legacy_summary=legacy_summary,
            )
            st.session_state[cached_prep_key] = (cleaned, auto_schema, cleaning_report, retail_compatible)

        clean_signature_key = f"rm_clean_signature_{identity}"
        if st.session_state.get(clean_signature_key) != clean_signature:
            # Cleaning options changed for *this* dataset only. Other datasets
            # keep their own dashboards and history.
            st.session_state[clean_signature_key] = clean_signature
            st.session_state.pop(_config_key(identity), None)
            st.session_state.pop(_original_key(identity), None)
            st.session_state.pop(f"rm_manual_schema_{identity}", None)
            st.session_state.pop(f"rm_selected_id_{identity}", None)
            st.session_state.pop(f"rm_focus_{identity}", None)
            _purge_dataset_cache(identity)
            storage.clear_history(st.session_state, namespace=identity)

        _render_cleaning_suggestions(suggestions, identity)
        schema = st.session_state.get(f"rm_manual_schema_{identity}") or auto_schema
        _render_mapping_editor(schema, identity)
        if st.session_state.pop(f"rm_rebuild_{identity}", False):
            st.session_state.pop(_config_key(identity), None)
            st.session_state.pop(_original_key(identity), None)
            st.session_state.pop(f"rm_selected_id_{identity}", None)
            _purge_dataset_cache(identity)
            storage.clear_history(st.session_state, namespace=identity)
        schema = st.session_state.get(f"rm_manual_schema_{identity}") or auto_schema

        st.success("Upload validated. The universal dashboard was generated automatically.")

        # Build (or reuse) the dashboard configuration before rendering filters
        # so assistant-added filters can be shown in the same run.
        config_key = _config_key(identity)
        if config_key not in st.session_state:
            config = build_dashboard(cleaned, schema, filename, identity)
            st.session_state[config_key] = config
            st.session_state[_original_key(identity)] = config.to_json()
            st.session_state["rm_theme_preset"] = config.theme.preset
            st.session_state["rm_accent"] = config.theme.accent
            storage.clear_history(st.session_state, namespace=identity)
        config = st.session_state[config_key]
        config.dataset_id = identity
        extra_filter_columns = [filter_.column for filter_ in config.filters if filter_.column]

        filters: dict[str, Any] = {}
        if retail_compatible:
            filtered, start_date, end_date, categories, cities, products, legacy_identity = render_sidebar_filters(
                cleaned, mapping, filename, extra_columns=extra_filter_columns
            )
            filters = {
                "Categories": categories,
                "Cities": cities,
                "Products": products,
                "Date Range": f"{start_date} to {end_date}" if start_date else None,
            }
        else:
            filtered, filters, _filter_prefix = render_universal_filters(
                cleaned, schema, key_prefix=f"rm_filter_{identity[:8]}",
                extra_columns=extra_filter_columns,
            )

        st.caption(
            f"Detected domain: **{schema.domain_label}** · {len(schema.measures)} measure(s) · "
            f"{len(schema.dimensions)} dimension(s) · {len(cleaned):,} rows"
        )
        if schema.warnings:
            with st.expander(f"Schema notes ({len(schema.warnings)})", expanded=False):
                for warning in schema.warnings:
                    st.caption(f"⚠ {warning}")

        if "rm_theme_preset" not in st.session_state:
            st.session_state["rm_theme_preset"] = config.theme.preset
        if "rm_accent" not in st.session_state:
            st.session_state["rm_accent"] = config.theme.accent

    # Main canvas ---------------------------------------------------------
    ui.inject_css(Theme(preset=config.theme.preset, accent=config.theme.accent, palette=config.theme.palette))
    st.session_state["rm_theme_preset"] = config.theme.preset
    st.session_state["rm_accent"] = config.theme.accent

    ui.render_toolbar(filename, schema.domain_label, provider.available, config.theme.preset)
    mode_key = "rm_dashboard_mode"
    mode_signature_key = f"rm_mode_signature_{identity}"
    desired_mode = "Customize Dashboard" if config.mode == "custom" else "Auto Dashboard"
    if st.session_state.get(mode_signature_key) != config.mode:
        # Keep the mode selector in sync with restore/undo/assistant changes
        # without overriding an in-progress selection.
        st.session_state[mode_signature_key] = config.mode
        st.session_state[mode_key] = desired_mode
    mode = st.radio(
        "Dashboard mode",
        ["Auto Dashboard", "Customize Dashboard"],
        horizontal=True,
        key=mode_key,
        help="Auto uses the generated layout. Customize enables the visual builder.",
    )
    config.mode = "custom" if mode == "Customize Dashboard" else "auto"
    st.session_state[mode_signature_key] = config.mode

    page_names = config.page_names()
    page_key = f"rm_page_{identity}"
    if page_key not in st.session_state or st.session_state[page_key] not in page_names:
        st.session_state[page_key] = page_names[0]
    page_name = st.session_state[page_key]
    page = config.page(page_name) or config.pages[0]

    st.header("Overview")
    st.caption(f"{filename} · {len(filtered):,} matching records · {schema.domain_label}")

    alerts: list[Alert] = []
    if filtered.empty:
        st.warning("No records match the active filters. Adjust the filters to see the dashboard.")
    else:
        if mode == "Customize Dashboard":
            canvas, panel = st.columns([3, 1], gap="large")
            with canvas:
                render_page(
                    filtered, page, schema, config.theme, dataset_id=identity,
                    key_prefix=identity[:8], editable=True,
                    selected_id=st.session_state.get(f"rm_selected_id_{identity}"),
                    on_select=lambda component_id: (
                        st.session_state.__setitem__(f"rm_focus_{identity}", component_id),
                        st.session_state.__setitem__(f"rm_selected_id_{identity}", component_id),
                        st.rerun(),
                    )[-1],
                )
            with panel:
                _render_builder(config, schema, page_name, identity)
        else:
            render_page(filtered, page, schema, config.theme, dataset_id=identity, key_prefix=identity[:8])

        with st.expander("Filtered data preview", expanded=False):
            st.dataframe(filtered.head(MAX_PREVIEW_ROWS), width="stretch", hide_index=True)

        render_insights_panel(filtered, schema, identity)
        render_advanced_analytics(filtered, schema, identity)

        alerts = render_alerts_panel(filtered, schema, identity)
        render_intelligence_hub(filtered, schema, identity, filename, filters, alerts)

    # Bottom report page tabs --------------------------------------------
    if len(page_names) > 1:
        st.radio(
            "Report pages",
            page_names,
            horizontal=True,
            key=page_key,
            label_visibility="collapsed",
        )

    # Downloads, AI, quality ---------------------------------------------
    insights = insights_for_frame(filtered, schema, identity)
    render_downloads(filtered, schema, cleaning_report, filename, filters, insights, identity, alerts=alerts)

    render_ai_panels(config, schema, filtered, page_name, identity, provider)

    with st.expander("Data quality & cleaning report", expanded=False):
        st.dataframe(cleaning_summary(cleaning_report), width="stretch", hide_index=True)
        for warning in cleaning_report.warnings:
            st.warning(warning)
        st.caption(
            "The original upload is preserved. Invalid numerics remain missing unless you explicitly "
            "opted into zero-filling; rows are removed only when de-duplication is enabled."
        )
        before_after = st.columns(2)
        before_after[0].caption("Original preview")
        before_after[0].dataframe(source.head(10), width="stretch", hide_index=True)
        before_after[1].caption("Prepared preview")
        before_after[1].dataframe(cleaned.head(10), width="stretch", hide_index=True)

    with st.expander("AI provider status", expanded=False):
        status = provider.config.public_status()
        st.write({"provider": status["provider"], "model": status["model"], "available": status["available"]})
        st.caption(status["message"])
        if st.button("Test AI connection", key=f"rm_test_ai_{identity}", width="stretch"):
            if not provider.available:
                st.warning(
                    "No AI provider is configured. Dashboard analytics, the verified chatbot, "
                    "insights and document retrieval keep working with local deterministic fallbacks."
                )
            else:
                with st.spinner("Contacting the configured AI provider…"):
                    try:
                        reply = provider.chat(
                            [{"role": "user", "content": "Reply with the single word OK."}],
                            temperature=0,
                            max_tokens=5,
                        )
                    except AIProviderError as error:
                        st.error(f"The AI provider could not be reached: {error}")
                    except Exception as error:
                        st.error(f"The AI connection test failed ({type(error).__name__}): {error}")
                    else:
                        st.success(f"AI provider responded: {reply[:80]}")
        st.caption(
            "Configure AI with RETAILMIND_AI_PROVIDER, RETAILMIND_AI_API_KEY, RETAILMIND_AI_BASE_URL, "
            "RETAILMIND_AI_MODEL and RETAILMIND_AI_EMBEDDING_MODEL. Secrets are never rendered or logged."
        )

    ui.render_footer()


if __name__ == "__main__":
    main()
