"""Universal interactive filters for arbitrary datasets."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from retailmind.schema import DatasetSchema


DIMENSION_PRIORITY = ("category", "product", "city", "region", "department", "course", "customer", "store", "sales_rep", "payment_method", "gender", "attendance")


def _options(frame: pd.DataFrame, column: str) -> list[str]:
    values = frame[column].dropna().astype("string")
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _search_columns(schema: DatasetSchema) -> list[str]:
    columns = [column for column in schema.categorical if column in schema.columns]
    return columns[:4]


def apply_filters(frame: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    """Apply a plain filter dictionary (used by tests and the chatbot)."""
    if frame.empty:
        return frame
    mask = pd.Series(True, index=frame.index)
    for column, spec in filters.items():
        if not isinstance(spec, dict):
            continue
        kind = spec.get("kind")
        selected = spec.get("selected")
        if kind == "search":
            needle = str(selected or "").strip().lower()
            if needle:
                columns = [item for item in (spec.get("columns") or []) if item in frame.columns]
                if columns:
                    text = frame[columns].astype("string").fillna("").agg(" ".join, axis=1).str.lower()
                    mask &= text.str.contains(needle, regex=False)
            continue
        if column not in frame.columns:
            continue
        if kind == "date" and selected:
            start, end = selected
            parsed = pd.to_datetime(frame[column], format="mixed", errors="coerce")
            mask &= parsed.between(pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1))
        elif kind == "category" and selected is not None:
            if selected:
                mask &= frame[column].astype("string").isin([str(item) for item in selected])
            else:
                mask &= False
        elif kind == "numeric" and selected:
            low, high = selected
            numeric = pd.to_numeric(frame[column], errors="coerce")
            mask &= numeric.between(low, high)
    return frame.loc[mask].copy()


def render_universal_filters(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    key_prefix: str = "rm",
    extra_columns: list[str] | tuple[str, ...] = (),
) -> tuple[pd.DataFrame, dict[str, Any], str]:
    """Render filters in the current container and return filtered data.

    The active filter dictionary is intentionally JSON-friendly so it can be
    stored with a dashboard configuration.  ``extra_columns`` lets the AI
    assistant add a filter for a column that is not in the default top-three
    dimensions.
    """
    st.header("Filters")
    filters: dict[str, Any] = {}

    date_column = schema.role_column("date")
    if date_column and len(frame):
        parsed = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
        valid = parsed.dropna()
        if not valid.empty:
            key = f"{key_prefix}_filter_date"
            default = (valid.min().date(), valid.max().date())
            if key not in st.session_state:
                st.session_state[key] = default
            selected = st.date_input("Date range", key=key)
            if isinstance(selected, tuple) and len(selected) == 2:
                filters[date_column] = {"kind": "date", "selected": [str(selected[0]), str(selected[1])]}

    dimensions: list[str] = []
    for role in DIMENSION_PRIORITY:
        column = schema.role_column(role)
        if column and column not in dimensions:
            dimensions.append(column)
    for column in schema.categorical:
        if column not in dimensions:
            dimensions.append(column)
    visible = dimensions[:3]
    for column in extra_columns:
        if column in frame.columns and column not in visible:
            visible.append(column)
    for column in visible:
        if column not in frame.columns:
            continue
        options = _options(frame, column)
        if not options or len(options) > 250:
            continue
        key = f"{key_prefix}_filter_{column}"
        if key not in st.session_state:
            st.session_state[key] = options
        selected = st.multiselect(schema.label_for(column), options, key=key)
        filters[column] = {"kind": "category", "selected": selected}

    search_columns = _search_columns(schema)
    if search_columns:
        search_key = f"{key_prefix}_filter_search"
        search = st.text_input("Search records", key=search_key, placeholder="Type text to search…")
        if search.strip():
            filters["__search__"] = {"kind": "search", "selected": search.strip(), "columns": search_columns}

    reset_key = f"{key_prefix}_filter_reset"
    if st.button("Reset filters", key=reset_key, width="stretch"):
        for key in list(st.session_state):
            if key.startswith(f"{key_prefix}_filter_"):
                del st.session_state[key]
        st.rerun()

    return apply_filters(frame, filters), filters, key_prefix


def filter_summary(filters: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for column, spec in filters.items():
        if column == "__search__":
            rows.append({"Filter": "Search", "Value": str(spec.get("selected"))})
            continue
        selected = spec.get("selected")
        if isinstance(selected, list):
            value = ", ".join(map(str, selected[:4])) + ("…" if len(selected) > 4 else "") if selected else "(none)"
        else:
            value = str(selected)
        rows.append({"Filter": column, "Value": value})
    return pd.DataFrame(rows, columns=["Filter", "Value"])


def active_filter_count(filters: dict[str, Any]) -> int:
    return sum(1 for spec in filters.values() if spec.get("selected"))
