"""Backwards-compatible helpers retained from the original dashboard.

The original public functions are kept so existing imports and tests continue
to work.  New code should prefer the ``retailmind`` package modules.
"""

from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from analytics import (
    apply_filters,
    clean_dimension_options,
    dataset_fingerprint,
    filter_defaults,
    initialise_filter_state,
    products_for_categories,
    retain_valid_products,
    scoped_filter_keys,
)
from data_sources import detect_column_mapping, map_to_canonical, profile_data, profile_schema, read_uploaded_file
from retailmind.utils import excel_bytes, money, parse_dates


# Explicit re-export with the original name used by tests and older callers.
def parse_uploaded_dates(values: pd.Series) -> pd.Series:
    return parse_dates(values)


def compact_number(value: float | int) -> str:
    from retailmind.utils import compact_number as _compact

    return _compact(value)


def clean_uploaded_data(frame: pd.DataFrame, mapping: dict[str, str | None]) -> tuple[pd.DataFrame, dict[str, int]]:
    """Original conservative canonical cleaning (kept for compatibility)."""
    cleaned, _ = map_to_canonical(frame, mapping)
    summary = {"invalid_dates": 0, "numeric_values_coerced": 0}
    if mapping.get("order_date"):
        original = cleaned["order_date"]
        parsed = parse_uploaded_dates(original)
        summary["invalid_dates"] = int(original.notna().sum() - parsed.notna().sum())
        cleaned["order_date"] = parsed
    for column in ("sales", "profit", "quantity", "unit_price", "discount"):
        if column in cleaned:
            original = cleaned[column]
            numeric = pd.to_numeric(original, errors="coerce")
            summary["numeric_values_coerced"] += int(original.notna().sum() - numeric.notna().sum())
            cleaned[column] = numeric
    # Invalid numeric values intentionally stay missing.  Zero-filling is an
    # explicit cleaning option in ``retailmind.cleaning``, never a silent
    # side-effect of canonical preparation.
    return cleaned, summary


def process_uploaded_source(content: bytes, filename: str, sheet_name: str | None = None):
    """Original read/detect/profile/clean pipeline (kept for compatibility)."""
    source = read_uploaded_file(content, filename, sheet_name)
    mapping = detect_column_mapping(source.columns)
    profile = profile_data(source, mapping)
    schema = profile_schema(source)
    non_sales_errors = [error for error in profile["errors"] if "sales or revenue column" not in error]
    if not mapping.get("sales"):
        profile["errors"] = non_sales_errors
        cleaned = source.copy()
        for column in schema["date_columns"]:
            cleaned[column] = parse_uploaded_dates(cleaned[column])
        return source, mapping, profile, cleaned, {"invalid_dates": 0, "numeric_values_coerced": 0}, schema
    if profile["errors"]:
        return source, mapping, profile, None, {"invalid_dates": 0, "numeric_values_coerced": 0}, schema
    cleaned, cleaning = clean_uploaded_data(source, mapping)
    return source, mapping, profile, cleaned, cleaning, schema


def render_sidebar_filters(raw, mapping, filename: str, extra_columns=()):
    """Original retail filter UI, including category -> product dependency.

    ``extra_columns`` lets the AI assistant add filters for additional
    dimensions.  They participate in the same reset behaviour as the legacy
    filters.
    """
    defaults = filter_defaults(raw, mapping)
    extra_columns = [
        column for column in dict.fromkeys(extra_columns or ())
        if column in raw.columns and column not in {"category", "city", "product_name", "order_date"}
    ]
    for column in extra_columns:
        defaults[f"extra_filter_{column}"] = clean_dimension_options(raw[column])
    digest = hashlib.sha256(filename.encode() + raw.to_csv(index=False).encode()).hexdigest()
    identity = dataset_fingerprint(raw, mapping, digest)
    keys = scoped_filter_keys(identity)
    keyed_defaults = {keys.get(name, f"{name}_{identity}"): value for name, value in defaults.items()}
    initialise_filter_state(st.session_state, identity, keyed_defaults)
    st.divider()
    st.header("Filters")
    if "date_range_filter" in defaults:
        dates = st.date_input("Date range", key=keys["date_range_filter"])
        start_date, end_date = dates if isinstance(dates, tuple) and len(dates) == 2 else (None, None)
    else:
        start_date = end_date = None
    categories = st.multiselect("Category", defaults.get("category_filter", []), key=keys["category_filter"]) if "category_filter" in defaults else None
    cities = st.multiselect("City", defaults.get("city_filter", []), key=keys["city_filter"]) if "city_filter" in defaults else None
    product_options = products_for_categories(raw, categories) if "product_filter" in defaults else []
    product_key = keys["product_filter"]
    if product_key in st.session_state:
        st.session_state[product_key] = retain_valid_products(st.session_state[product_key], product_options)
    products = st.multiselect("Product", product_options, key=product_key) if "product_filter" in defaults else None
    extra_filters: dict[str, list[str]] = {}
    for column in extra_columns:
        key = f"extra_filter_{column}_{identity}"
        selected = st.multiselect(
            column.replace("_", " ").title(),
            defaults.get(f"extra_filter_{column}", []),
            key=key,
        )
        extra_filters[column] = selected
    st.button("Reset filters", key="rm_legacy_reset_filters", width="stretch", on_click=_reset_filters, args=(keyed_defaults,))
    filtered = apply_filters(raw, start_date, end_date, categories, cities, products, extra_filters=extra_filters)
    return filtered, start_date, end_date, categories, cities, products, identity


def _reset_filters(defaults: dict[str, object]) -> None:
    for key, value in defaults.items():
        st.session_state[key] = list(value) if isinstance(value, list) else value
