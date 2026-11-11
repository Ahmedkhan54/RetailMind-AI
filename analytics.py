"""Reusable calculations for the Retail Sales Profitability dashboard.

These functions operate only on a supplied DataFrame.  They make the business
rules easy to test and ensure dashboard components use the same aggregations.
"""
from __future__ import annotations

import hashlib
import math

import pandas as pd

from retailmind.utils import to_numeric_loose


REQUIRED_COLUMNS = {"order_id", "order_date", "category", "product_name", "city", "sales", "profit"}


def prepare_data(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a safe display/analysis copy using the dashboard's known schema."""
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(sorted(missing)))
    data = frame.copy()
    data["sales"] = to_numeric_loose(data["sales"]).fillna(0.0)
    data["profit"] = to_numeric_loose(data["profit"]).fillna(0.0)
    data["order_date"] = pd.to_datetime(data["order_date"], errors="coerce")
    for column in ("order_id", "category", "product_name", "city", "region", "sales_rep", "payment_method", "customer"):
        if column not in data.columns:
            continue
        data[column] = data[column].astype("string").str.strip().replace("", pd.NA)
    for column in ("quantity", "unit_price", "discount"):
        if column in data.columns:
            data[column] = to_numeric_loose(data[column])
    return data


def apply_filters(frame: pd.DataFrame, start_date, end_date, categories, cities, products, extra_filters=None, numeric_ranges=None) -> pd.DataFrame:
    """Filter prepared data inclusively by date and selected dimension values."""
    if frame.empty or categories == [] or cities == [] or products == []:
        return frame.iloc[0:0].copy()
    mask = pd.Series(True, index=frame.index)
    if start_date is not None and end_date is not None:
        start = pd.Timestamp(start_date)
        # Include an entire end day even if a source datetime is present.
        end = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        mask &= frame["order_date"].between(start, end)
    if categories is not None:
        mask &= frame["category"].isin(categories)
    if cities is not None:
        mask &= frame["city"].isin(cities)
    if products is not None:
        mask &= frame["product_name"].isin(products)
    for field, values in (extra_filters or {}).items():
        if field in frame and values is not None:
            if values == []:
                return frame.iloc[0:0].copy()
            mask &= frame[field].isin(values)
    for field, bounds in (numeric_ranges or {}).items():
        if field in frame and bounds is not None:
            mask &= pd.to_numeric(frame[field], errors="coerce").between(bounds[0], bounds[1])
    return frame.loc[mask].copy()


def products_for_categories(frame: pd.DataFrame, categories) -> list[str]:
    """Return the sorted union of products available in selected categories."""
    if categories == []:
        return []
    products = frame["product_name"] if categories is None else frame.loc[
        frame["category"].isin(categories), "product_name"
    ]
    return clean_dimension_options(products)


def retain_valid_products(selected_products, product_options) -> list[str]:
    """Keep selected products only while they remain valid options."""
    valid = set(product_options)
    return [product for product in selected_products if product in valid]


def clean_dimension_options(values: pd.Series) -> list[str]:
    """Return unique, sorted non-blank dimension values for a filter widget."""
    cleaned = values.dropna().astype(str).str.strip()
    return sorted(value for value in cleaned.unique().tolist() if value)


def filter_defaults(frame: pd.DataFrame, mapping: dict[str, object]) -> dict[str, object]:
    """Build valid filter defaults from only the dimensions mapped in this dataset."""
    defaults: dict[str, object] = {}
    if mapping.get("category") and "category" in frame.columns:
        defaults["category_filter"] = clean_dimension_options(frame["category"])
    if mapping.get("city") and "city" in frame.columns:
        defaults["city_filter"] = clean_dimension_options(frame["city"])
    if mapping.get("product_name") and "product_name" in frame.columns:
        defaults["product_filter"] = clean_dimension_options(frame["product_name"])
    for field in ("region", "customer", "sales_rep", "payment_method", "order_id"):
        if mapping.get(field) and field in frame.columns:
            defaults[f"{field}_filter"] = clean_dimension_options(frame[field])
    for field in ("quantity", "unit_price", "discount"):
        if mapping.get(field) and field in frame:
            values = pd.to_numeric(frame[field], errors="coerce").dropna()
            if not values.empty:
                defaults[f"{field}_range"] = (float(values.min()), float(values.max()))
    if mapping.get("order_date"):
        dates = frame["order_date"].dropna()
        if not dates.empty:
            defaults["date_range_filter"] = (dates.min().date(), dates.max().date())
    return defaults


def dataset_fingerprint(frame: pd.DataFrame, mapping: dict[str, object], source_identity: str) -> str:
    """Create a stable per-dataset identity for session-scoped widget state."""
    digest = hashlib.sha256()
    digest.update(source_identity.encode("utf-8"))
    digest.update(repr(sorted(mapping.items())).encode("utf-8"))
    digest.update("|".join(map(str, frame.columns)).encode("utf-8"))
    digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    return digest.hexdigest()[:16]


def upload_generation_identity(source_identity: str, mapping: dict[str, object]) -> str:
    """Return the stable identity used to approve an uploaded dashboard."""
    digest = hashlib.sha256()
    digest.update(source_identity.encode("utf-8"))
    digest.update(repr(sorted(mapping.items())).encode("utf-8"))
    return digest.hexdigest()[:16]


def scoped_filter_keys(dataset_identity: str, *, mysql_source: bool = False) -> dict[str, str]:
    """Return filter keys isolated by dataset while retaining legacy MySQL keys."""
    names = ("date_range_filter", "category_filter", "city_filter", "product_filter", "chart_dimension", "chart_metric", "chart_top_n", "chart_view", "data_question")
    return {name: name if mysql_source else f"{name}_{dataset_identity}" for name in names}


def initialise_filter_state(state: dict, dataset_identity: str, defaults: dict[str, object]) -> bool:
    """Set current-dataset defaults before widget construction; report a dataset switch."""
    changed = state.get("_active_dataset_identity") != dataset_identity
    if changed:
        state["_active_dataset_identity"] = dataset_identity
    for key, value in defaults.items():
        if changed or key not in state:
            state[key] = list(value) if isinstance(value, list) else value
    return changed


def safe_ratio(numerator: float, denominator: float) -> float | None:
    """Return a ratio, or None where dividing would be misleading."""
    return None if not denominator else numerator / denominator


def growth_metric_delta(value: float | None) -> float | str | None:
    """Return a Streamlit metric delta with a neutral numeric zero when flat."""
    if value is None or not math.isfinite(value):
        return None
    if value == 0:
        return 0
    return f"{value:.2%}"


def calculate_kpis(frame: pd.DataFrame) -> dict[str, float | int | None]:
    """Calculate filter-aware KPIs. Average order value aggregates each order first."""
    if frame.empty:
        return {"total_sales": 0.0, "total_profit": 0.0, "order_count": 0,
                "average_order_value": None, "profit_margin": None, "average_sales_per_row": None,
                "quantity_sold": None}
    total_sales = float(frame["sales"].sum())
    total_profit = float(frame["profit"].sum())
    order_sales = frame.groupby("order_id", dropna=True)["sales"].sum()
    quantity = None
    if "quantity" in frame.columns:
        valid_quantity = pd.to_numeric(frame["quantity"], errors="coerce").dropna()
        quantity = float(valid_quantity.sum()) if not valid_quantity.empty else None
    return {
        "total_sales": total_sales,
        "total_profit": total_profit,
        "order_count": int(order_sales.index.nunique()),
        "average_order_value": float(order_sales.mean()) if not order_sales.empty else None,
        "profit_margin": safe_ratio(total_profit, total_sales),
        "average_sales_per_row": float(frame["sales"].mean()),
        "quantity_sold": quantity,
    }


def monthly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    valid = frame.dropna(subset=["order_date"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=["month", "sales", "profit"])
    valid["month"] = valid["order_date"].dt.to_period("M").dt.to_timestamp()
    return valid.groupby("month", as_index=False)[["sales", "profit"]].sum().sort_values("month")


def previous_period_kpis(frame: pd.DataFrame, start_date, end_date, categories, cities, products,
                         extra_filters=None, numeric_ranges=None) -> dict[str, float | None]:
    """Compare the selected date span to the immediately preceding equal-length span."""
    if start_date is None or end_date is None:
        return {"sales_change": None, "profit_change": None, "previous_sales": None, "previous_profit": None}
    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
    days = (end.normalize() - start.normalize()).days + 1
    if days <= 0:
        return {"sales_change": None, "profit_change": None, "previous_sales": None, "previous_profit": None}
    previous = apply_filters(frame, start - pd.Timedelta(days=days), start - pd.Timedelta(days=1), categories, cities, products, extra_filters, numeric_ranges)
    current = apply_filters(frame, start, end, categories, cities, products, extra_filters, numeric_ranges)
    current_kpis, old_kpis = calculate_kpis(current), calculate_kpis(previous)
    return {
        "sales_change": safe_ratio(current_kpis["total_sales"] - old_kpis["total_sales"], old_kpis["total_sales"]),
        "profit_change": safe_ratio(current_kpis["total_profit"] - old_kpis["total_profit"], abs(old_kpis["total_profit"])),
        "previous_sales": old_kpis["total_sales"], "previous_profit": old_kpis["total_profit"],
    }


def kpi_availability(mapping: dict[str, object]) -> dict[str, bool]:
    """Describe which KPIs are meaningful for a mapped source schema."""
    return {
        "orders": bool(mapping.get("order_id")),
        "profit": bool(mapping.get("profit")),
        "date": bool(mapping.get("order_date")),
        "quantity": bool(mapping.get("quantity")),
        "discount": bool(mapping.get("discount")),
    }


def grouped_performance(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Sales, profit, and profit margin by an available dimension."""
    measures = ["sales", "profit"] + (["quantity"] if "quantity" in frame.columns else [])
    columns = [dimension, *measures, "margin"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    result = frame.groupby(dimension, dropna=False)[measures].sum().reset_index()
    result["margin"] = result.apply(lambda row: safe_ratio(row["profit"], row["sales"]), axis=1)
    return result.sort_values("sales", ascending=False, kind="stable")


def build_insights(frame: pd.DataFrame, previous: dict[str, float | None],
                   dimensions: set[str] | None = None, include_profit: bool = True) -> list[str]:
    """Generate factual, rule-based observations; no causal claims are made."""
    if frame.empty:
        return ["Insufficient data: no records match the active filters."]
    insights: list[str] = []
    dimensions = {"category", "product_name"} if dimensions is None else dimensions
    categories = grouped_performance(frame, "category") if "category" in dimensions else pd.DataFrame()
    products = grouped_performance(frame, "product_name") if "product_name" in dimensions else pd.DataFrame()
    if not categories.empty:
        best = categories.iloc[0]
        suffix = f"; {best['margin']:.1%} margin" if include_profit else ""
        insights.append(f"Top category by sales: {best['category']} (₹{best['sales']:,.0f} sales{suffix}).")
    if not products.empty:
        best_product = products.iloc[0]
        insights.append(f"Top product by sales: {best_product['product_name']} (₹{best_product['sales']:,.0f}).")
        low_margin = products[(products["sales"] >= products["sales"].median()) & (products["margin"] < products["margin"].median())] if include_profit else pd.DataFrame()
        if not low_margin.empty:
            item = low_margin.sort_values("sales", ascending=False).iloc[0]
            insights.append(f"Review {item['product_name']}: above-median sales (₹{item['sales']:,.0f}) with below-median margin ({item['margin']:.1%}).")
    if previous.get("sales_change") is not None:
        direction = "increased" if previous["sales_change"] >= 0 else "decreased"
        insights.append(f"Sales {direction} by {abs(previous['sales_change']):.1%} versus the immediately preceding equal-length period.")
    else:
        insights.append("Previous-period comparison is unavailable because the preceding equal-length period has no sales.")
    return insights


def answer_data_question(question: str, frame: pd.DataFrame, mapping: dict[str, object],
                         previous: dict[str, float | None]) -> str:
    """Answer a small explicit set of questions using only active filtered data."""
    text = question.strip().lower()
    if not text:
        return "Ask about total sales, a top product/category/city, or prior-period sales comparison."
    if "total sales" in text:
        if "profit" in text:
            if not mapping.get("profit"):
                return "Total sales are available, but a mapped profit column is required to report total profit."
            return (f"Total sales for the active filters are ₹{frame['sales'].sum():,.2f}; "
                    f"total profit is ₹{frame['profit'].sum():,.2f}.")
        return f"Total sales for the active filters are ₹{frame['sales'].sum():,.2f}."
    if "previous" in text or "compare" in text or "growth" in text:
        change = previous.get("sales_change")
        return ("Previous-period sales comparison is unavailable for the active date range."
                if change is None else f"Sales changed by {change:.1%} versus the preceding equal-length period.")
    if "product" in text and ("top five" in text or "top 5" in text):
        if not mapping.get("product_name"):
            return "A mapped product column is required for that answer."
        summary = grouped_performance(frame, "product_name")
        if summary.empty:
            return "No records match the active filters."
        ranked = summary.sort_values("sales", ascending=False, kind="stable").head(5)
        values = "; ".join(
            f"{index + 1}. {row['product_name']} (₹{row['sales']:,.2f})"
            for index, (_, row) in enumerate(ranked.iterrows())
        )
        return f"Top {len(ranked)} products by sales for the active filters: {values}."
    for label, field, measure in (("product", "product_name", "sales"), ("category", "category", "profit"), ("city", "city", "sales")):
        if label in text and ("highest" in text or "best" in text or "top" in text):
            if not mapping.get(field):
                return f"A mapped {label} column is required for that answer."
            if measure == "profit" and not mapping.get("profit"):
                return "A mapped profit column is required for that answer."
            summary = grouped_performance(frame, field)
            if summary.empty:
                return "No records match the active filters."
            winner = summary.sort_values(measure, ascending=False, kind="stable").iloc[0]
            return f"Top {label} by {measure} is {winner[field]} (₹{winner[measure]:,.2f}) for the active filters."
    return "I can answer total sales, top product by sales, top category by profit, top city by sales, and prior-period sales comparison."


def build_summary_report(frame: pd.DataFrame, filters: dict[str, object], kpis: dict[str, object], insights: list[str]) -> str:
    """Create a portable, plain-text business summary for download."""
    lines = ["RetailMind AI Business Summary", "=" * 32, "", "Active filters:"]
    lines.extend(f"- {key}: {value}" for key, value in filters.items())
    lines.extend(["", "KPIs:", f"- Total sales: ₹{kpis['total_sales']:,.2f}", f"- Total profit: ₹{kpis['total_profit']:,.2f}", f"- Distinct orders: {kpis['order_count']:,}"])
    aov = kpis["average_order_value"]
    margin = kpis["profit_margin"]
    lines.extend([f"- Average order value: {'N/A' if aov is None else f'₹{aov:,.2f}'}", f"- Profit margin: {'N/A' if margin is None else f'{margin:.2%}'}", "", "Rule-based insights:"])
    lines.extend(f"- {insight}" for insight in insights)
    return "\n".join(lines) + "\n"


def dataframe_to_csv(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


def detect_outliers_iqr(series: pd.Series, factor: float = 1.5) -> dict[str, object]:
    """Calculate IQR bounds and flag outliers in a numerical series."""
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    total_count = len(series)
    valid_count = len(valid)
    if valid_count < 4:
        return {
            "method": "iqr",
            "factor": factor,
            "total_count": total_count,
            "valid_count": valid_count,
            "q1": 0.0,
            "q3": 0.0,
            "iqr": 0.0,
            "lower_bound": 0.0,
            "upper_bound": 0.0,
            "outlier_count": 0,
            "outlier_percentage": 0.0,
            "mask": pd.Series(False, index=series.index),
        }
    q1 = float(valid.quantile(0.25))
    q3 = float(valid.quantile(0.75))
    iqr = q3 - q1
    lower_bound = q1 - factor * iqr
    upper_bound = q3 + factor * iqr
    mask = (numeric < lower_bound) | (numeric > upper_bound)
    mask = mask.fillna(False)
    outlier_count = int(mask.sum())
    percentage = (outlier_count / total_count * 100.0) if total_count > 0 else 0.0
    return {
        "method": "iqr",
        "factor": factor,
        "total_count": total_count,
        "valid_count": valid_count,
        "q1": round(q1, 3),
        "q3": round(q3, 3),
        "iqr": round(iqr, 3),
        "lower_bound": round(lower_bound, 3),
        "upper_bound": round(upper_bound, 3),
        "outlier_count": outlier_count,
        "outlier_percentage": round(percentage, 2),
        "mask": mask,
    }


def detect_outliers_zscore(series: pd.Series, threshold: float = 3.0) -> dict[str, object]:
    """Calculate Z-scores and flag values exceeding standard deviation threshold."""
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    total_count = len(series)
    valid_count = len(valid)
    if valid_count < 3:
        return {
            "method": "zscore",
            "threshold": threshold,
            "total_count": total_count,
            "valid_count": valid_count,
            "mean": 0.0,
            "std": 0.0,
            "outlier_count": 0,
            "outlier_percentage": 0.0,
            "mask": pd.Series(False, index=series.index),
        }
    mean = float(valid.mean())
    std = float(valid.std())
    if std == 0 or math.isnan(std):
        mask = pd.Series(False, index=series.index)
        outlier_count = 0
    else:
        z_scores = (numeric - mean).abs() / std
        mask = (z_scores > threshold).fillna(False)
        outlier_count = int(mask.sum())
    percentage = (outlier_count / total_count * 100.0) if total_count > 0 else 0.0
    return {
        "method": "zscore",
        "threshold": threshold,
        "total_count": total_count,
        "valid_count": valid_count,
        "mean": round(mean, 3),
        "std": round(std, 3),
        "outlier_count": outlier_count,
        "outlier_percentage": round(percentage, 2),
        "mask": mask,
    }


def flag_dataset_outliers(frame: pd.DataFrame, column: str, method: str = "iqr", threshold: float = 1.5) -> tuple[pd.DataFrame, dict[str, object]]:
    """Flag rows containing outliers in the specified column without modifying the original data."""
    if column not in frame.columns:
        raise ValueError(f"Column '{column}' is not present in the dataset.")
    if method == "zscore":
        summary = detect_outliers_zscore(frame[column], threshold=threshold)
    else:
        summary = detect_outliers_iqr(frame[column], factor=threshold)
    flagged = frame.loc[summary["mask"]].copy()
    flagged["outlier_column"] = column
    flagged["outlier_value"] = frame.loc[summary["mask"], column]
    flagged["outlier_method"] = summary["method"]
    return flagged, summary


def calculate_correlation_matrix(frame: pd.DataFrame, method: str = "pearson", min_periods: int = 2) -> pd.DataFrame:
    """Compute correlation matrix for numerical columns, safely handling constants and nulls."""
    if frame.empty:
        return pd.DataFrame()
    numeric_frame = frame.select_dtypes(include="number")
    usable_columns = []
    for col in numeric_frame.columns:
        series = numeric_frame[col].dropna()
        if len(series) >= min_periods and series.nunique() > 1 and float(series.std()) > 0:
            usable_columns.append(col)
    if len(usable_columns) < 2:
        return pd.DataFrame()
    corr = numeric_frame[usable_columns].corr(method=method, min_periods=min_periods)
    return corr.round(3)

