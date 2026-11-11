"""Read-only data source adapters and schema mapping for the dashboard.

The adapters deliberately return DataFrames only: importing a CSV or Excel file
never writes to the configured MySQL database.
"""
from __future__ import annotations

from io import BytesIO
import csv
from difflib import SequenceMatcher
import logging
import re
import zipfile

import pandas as pd

from retailmind.utils import to_numeric_loose

logger = logging.getLogger(__name__)


CANONICAL_COLUMNS = ("order_id", "order_date", "category", "product_name", "city", "region", "sales_rep", "payment_method", "sales", "profit", "quantity", "unit_price", "customer", "discount")
REQUIRED_SOURCE_COLUMNS = ("sales",)
OPTIONAL_DEFAULTS = {
    "order_id": None,
    "order_date": pd.NaT,
    "category": "Not provided",
    "product_name": "Not provided",
    "city": "Not provided",
    "region": "Not provided",
    "sales_rep": "Not provided",
    "payment_method": "Not provided",
    "profit": 0.0,
    "quantity": pd.NA,
    "unit_price": pd.NA,
    "customer": pd.NA,
    "discount": pd.NA,
}
COLUMN_ALIASES = {
    "order_id": (
        "order id", "order number", "order no", "invoice id", "invoice number", "invoice no",
        "transaction id", "transaction number", "bill id", "bill number", "receipt id", "reference id",
    ),
    "order_date": (
        "order date", "date", "sales date", "transaction date", "invoice date", "purchase date",
        "created date", "created at", "order datetime", "date of sale",
    ),
    "category": ("category", "product category", "item category", "segment", "department", "product type", "sub category"),
    "product_name": ("product name", "product", "item", "item name", "sku name", "article", "goods", "service"),
    "city": ("city", "town", "location", "store city", "branch city", "city name"),
    "region": ("region", "area", "zone", "territory", "state", "province"),
    "sales_rep": ("sales rep", "sales representative", "representative", "salesperson", "account manager"),
    "payment_method": ("payment method", "payment type", "payment mode", "tender"),
    "sales": (
        "sales", "revenue", "sales amount", "total sales", "total revenue", "net sales", "gross sales",
        "gross revenue", "sales value", "sales total", "revenue amount", "total amount", "order amount",
        "order value", "order total", "billed amount", "bill amount", "invoice amount", "grand total",
        "net revenue", "turnover", "gmv", "amount inr", "amount rs", "sales inr",
    ),
    "profit": (
        "profit", "net profit", "gross profit", "margin amount", "profit amount", "profit value",
        "earnings", "net income", "operating profit", "profit inr",
    ),
    "quantity": ("quantity", "units sold", "units", "qty", "unit quantity", "volume", "pieces", "item count"),
    "unit_price": ("unit price", "price per unit", "price", "selling price", "rate", "mrp"),
    "customer": (
        "customer", "customer id", "customer name", "client", "client id", "client name",
        "buyer", "buyer id", "account id", "shopper", "shopper id",
    ),
    "discount": ("discount", "discount pct", "discount percent", "discount percentage", "discount rate", "markdown"),
}

# Weak aliases are generic accounting words.  They are only accepted when the
# file has other commercial signals, so a stray numeric "Amount" column is not
# silently treated as revenue.
WEAK_REVENUE_ALIASES = (
    "amount", "total", "value", "income", "billing", "cart value", "basket value",
    "total amount", "grand total", "total value", "net amount",
)


def normalise_name(value: object) -> str:
    """Return a comparison-friendly representation of a source column name."""
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def profile_schema(frame: pd.DataFrame) -> dict[str, list[str]]:
    """Infer safe dimensions and measures for arbitrary uploaded tabular data.

    It deliberately returns only primitive dataframe column names: chart labels
    are never derived from pandas indexes, interval objects, or nested values.

    Date and numeric detection is performed on a bounded sample (at most 5,000
    non-null values) so schema inference stays fast on large uploads, while the
    full column is still used for exact statistics elsewhere.
    """
    date_columns: list[str] = []
    numeric_columns: list[str] = []
    categorical_columns: list[str] = []
    identifier_columns: list[str] = []
    rows = max(len(frame), 1)
    for column in frame.columns:
        name = str(column)
        values = frame[column]
        normalised = normalise_name(name)
        non_null = values.dropna()
        if non_null.empty:
            continue
        sample = non_null.iloc[:5000] if len(non_null) > 5000 else non_null
        is_date_name = any(token in normalised for token in ("date", "time", "month", "year", "day"))
        if is_date_name and not pd.api.types.is_numeric_dtype(values):
            parsed = pd.to_datetime(sample.astype("string"), format="mixed", errors="coerce")
            if parsed.notna().mean() >= 0.75:
                date_columns.append(name)
                continue
        numeric = to_numeric_loose(sample)
        if numeric.notna().mean() >= 0.85 and not pd.api.types.is_bool_dtype(values):
            numeric_columns.append(name)
            if any(token in normalised for token in ("id", "code", "number", "reference")):
                identifier_columns.append(name)
            continue
        unique = int(sample.astype("string").nunique())
        unique_ratio = unique / max(len(sample), 1)
        if unique <= 50 and unique_ratio < 0.95:
            categorical_columns.append(name)
    measures = [column for column in numeric_columns if column not in identifier_columns]
    return {
        "date_columns": date_columns,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "identifier_columns": identifier_columns,
        "measures": measures,
        "dimensions": categorical_columns,
    }


def _alias_score(column: str, candidate: str) -> float:
    """Score how strongly a header matches one canonical alias.

    1.00 exact · 0.94 contains on token boundaries · 0.88 all tokens present ·
    0.72 close typo match.  Scoring (rather than a first-match dict lookup)
    handles ``Sales (₹)``, ``TOTAL_SALES``, ``Net Sales Value`` and similar
    real-world exports without mapping unrelated numeric columns.
    """
    if column == candidate:
        return 1.0
    if not column or not candidate:
        return 0.0
    column_tokens = set(column.split())
    candidate_tokens = set(candidate.split())
    if candidate_tokens and candidate_tokens.issubset(column_tokens):
        return 0.94
    if f" {candidate} " in f" {column} ":
        return 0.9
    if len(candidate) >= 5 and SequenceMatcher(None, column, candidate).ratio() >= 0.86:
        return 0.72
    return 0.0


def detect_column_mapping(columns) -> dict[str, str | None]:
    """Suggest canonical fields from common source-column spellings.

    Detection is deterministic and explainable.  Every source column may be
    assigned to at most one field, and weak aliases (``amount``, ``total``,
    ``value``) require commercial context such as an order, product, customer,
    quantity, or category column.
    """
    names = [str(column) for column in columns]
    normalised = {normalise_name(column): column for column in names}
    normalised_names = set(normalised)
    commercial_context = any(
        any(token in key for token in ("order", "product", "item", "sku", "customer", "client", "invoice", "quantity", "qty", "category", "sales", "revenue", "profit"))
        for key in normalised_names
    )
    mapping: dict[str, str | None] = {}
    used: set[str] = set()
    for canonical in CANONICAL_COLUMNS:
        aliases = (canonical.replace("_", " "),) + COLUMN_ALIASES[canonical]
        if canonical == "sales":
            aliases = aliases + WEAK_REVENUE_ALIASES
        scored: list[tuple[float, int, str]] = []
        for position, column in enumerate(names):
            if column in used:
                continue
            key = normalise_name(column)
            score = max((_alias_score(key, normalise_name(alias)) for alias in aliases), default=0.0)
            if score <= 0:
                continue
            # A generic revenue alias is only trusted with commercial context.
            if canonical == "sales" and not any(
                _alias_score(key, normalise_name(alias)) >= 0.9 for alias in aliases if alias not in WEAK_REVENUE_ALIASES
            ) and not commercial_context:
                continue
            scored.append((score, -position, column))
        scored.sort(reverse=True)
        if not scored:
            mapping[canonical] = None
            continue
        mapping[canonical] = scored[0][2]
        used.add(scored[0][2])
    return mapping


def _is_excel(filename: str) -> bool:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return suffix in {"xlsx", "xls", "xlsm"}


def duplicate_source_columns(content: bytes, filename: str, sheet_name: str | None = None) -> list[str]:
    """Return duplicate header names before pandas can silently disambiguate them."""
    try:
        if filename.lower().endswith(".csv"):
            header = next(csv.reader(BytesIO(content).read().decode("utf-8-sig").splitlines()), [])
        elif _is_excel(filename):
            from openpyxl import load_workbook
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
            worksheet = workbook[sheet_name or workbook.sheetnames[0]]
            header = [cell for cell in next(worksheet.iter_rows(values_only=True), ())]
        else:
            return []
    except (UnicodeDecodeError, OSError, ValueError, zipfile.BadZipFile):
        return []
    names = [str(value).strip() for value in header if value is not None and str(value).strip()]
    return sorted({name for name in names if names.count(name) > 1})


def inspect_excel_worksheets(content: bytes) -> list[dict[str, object]]:
    """Return read-only worksheet metadata and a score for likely tabular data."""
    try:
        workbook = pd.ExcelFile(BytesIO(content))
        sheets: list[dict[str, object]] = []
        for position, sheet_name in enumerate(workbook.sheet_names):
            preview = pd.read_excel(workbook, sheet_name=sheet_name, nrows=25)
            mapping = detect_column_mapping(preview.columns)
            matched_fields = sum(value is not None for value in mapping.values())
            named_columns = sum(not normalise_name(column).startswith("unnamed") for column in preview.columns)
            usable_rows = len(preview.dropna(how="all"))
            name = sheet_name.lower()
            name_penalty = 20 if "dashboard" in name else 8 if any(token in name for token in ("calc", "helper")) else 0
            score = matched_fields * 20 + named_columns * 2 + min(usable_rows, 25) - name_penalty
            sheets.append({
                "name": sheet_name,
                "position": position,
                "score": score,
                "mapping": mapping,
                "usable_rows": usable_rows,
            })
        return sheets
    except (ValueError, OSError, ImportError, UnicodeError, pd.errors.ParserError,
            pd.errors.EmptyDataError, zipfile.BadZipFile) as error:
        logger.exception("Failed to inspect uploaded workbook")
        raise ValueError("Could not read the Excel workbook. Check that it is valid and readable.") from error


def preferred_excel_worksheet(content: bytes) -> str:
    """Choose the strongest tabular sheet, retaining workbook order as a tie-breaker."""
    sheets = inspect_excel_worksheets(content)
    if not sheets:
        raise ValueError("The uploaded workbook contains no worksheets.")
    return max(sheets, key=lambda sheet: (sheet["score"], -sheet["position"]))["name"]  # type: ignore[return-value]


def read_uploaded_file(content: bytes, filename: str, sheet_name: str | None = None) -> pd.DataFrame:
    """Load CSV or Excel bytes without persisting or modifying the uploaded file."""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    stream = BytesIO(content)
    try:
        if suffix == "csv":
            frame = pd.read_csv(stream)
        elif _is_excel(filename):
            frame = pd.read_excel(stream, sheet_name=0 if sheet_name is None else sheet_name)
        else:
            raise ValueError("Upload a CSV, XLS, XLSX, or XLSM file.")
    except ValueError as error:
        if isinstance(error, pd.errors.EmptyDataError):
            logger.exception("Uploaded tabular file is empty name=%s", filename)
            raise ValueError(f"Could not read {filename}. The file is empty.") from error
        raise
    except (OSError, ImportError, UnicodeError, pd.errors.ParserError,
            pd.errors.EmptyDataError, zipfile.BadZipFile) as error:
        logger.exception("Failed to read uploaded file name=%s", filename)
        raise ValueError(f"Could not read {filename}. Check that it is a valid, readable file.") from error
    logger.info("Read uploaded file name=%s rows=%s columns=%s sheet=%s", filename, len(frame), len(frame.columns), sheet_name)
    return frame


def map_to_canonical(frame: pd.DataFrame, mapping: dict[str, str | None]) -> tuple[pd.DataFrame, list[str]]:
    """Create the dashboard schema and report non-fatal fields supplied as defaults."""
    unavailable = [field for field in REQUIRED_SOURCE_COLUMNS if not mapping.get(field)]
    if unavailable:
        raise ValueError("A sales/revenue column is required. Map one source column to Sales.")
    result = pd.DataFrame(index=frame.index)
    defaults_used: list[str] = []
    for field in CANONICAL_COLUMNS:
        source = mapping.get(field)
        if source and source in frame.columns:
            result[field] = frame[source]
        elif field in {"quantity", "unit_price", "customer", "discount"}:
            defaults_used.append(field)
            continue
        elif field == "order_id":
            result[field] = [f"uploaded-{position + 1}" for position in range(len(frame))]
            defaults_used.append(field)
        else:
            result[field] = OPTIONAL_DEFAULTS[field]
            defaults_used.append(field)
    return result, defaults_used


def profile_data(frame: pd.DataFrame, mapping: dict[str, str | None]) -> dict[str, object]:
    """Profile a source frame without modifying it; errors block dashboard generation."""
    missing_or_blank = {}
    for column in frame.columns:
        values = frame[column]
        blanks = values.astype("string").str.strip().eq("").fillna(False)
        missing_or_blank[str(column)] = int(values.isna().sum() + blanks.sum())

    conversion_failures: dict[str, int] = {}
    suspicious_values: dict[str, dict[str, int]] = {}
    for field in ("sales", "profit", "quantity", "unit_price", "discount"):
        source = mapping.get(field)
        if not source or source not in frame.columns:
            continue
        values = frame[source]
        present = values.notna() & values.astype("string").str.strip().ne("")
        numeric = to_numeric_loose(values)
        conversion_failures[field] = int((present & numeric.isna()).sum())
        suspicious_values[field] = {
            "negative": int((numeric < 0).sum()),
            "zero": int((numeric == 0).sum()),
        }

    invalid_dates = 0
    date_source = mapping.get("order_date")
    if date_source and date_source in frame.columns:
        values = frame[date_source]
        present = values.notna() & values.astype("string").str.strip().ne("")
        invalid_dates = int((present & pd.to_datetime(values, errors="coerce").isna()).sum())

    order_duplicates = 0
    order_source = mapping.get("order_id")
    if order_source and order_source in frame.columns:
        identifiers = frame[order_source].astype("string").str.strip().replace("", pd.NA).dropna()
        order_duplicates = int(identifiers.duplicated().sum())

    errors = []
    selected_sources = [source for source in mapping.values() if source]
    duplicate_mappings = sorted({source for source in selected_sources if selected_sources.count(source) > 1})
    if duplicate_mappings:
        errors.append(
            "Map each selected source column to only one dashboard field. "
            "Duplicate mapping(s): " + ", ".join(duplicate_mappings) + "."
        )
    sales_source = mapping.get("sales")
    if not sales_source:
        errors.append("A supported sales or revenue column could not be detected. Add a Sales or Revenue column and upload the file again.")
    elif conversion_failures.get("sales", 0) == len(frame) and len(frame):
        errors.append("The mapped sales column has no usable numeric values.")
    for field, failures in conversion_failures.items():
        if failures:
            errors.append(
                f"The mapped {field.replace('_', ' ')} column contains {failures:,} invalid numeric value(s). "
                "Correct the source values and upload the file again."
            )
    warnings = []
    if frame.empty:
        errors.append("The selected dataset contains no rows.")
    if invalid_dates:
        warnings.append(f"{invalid_dates:,} date value(s) cannot be used in date-based analysis.")
    if order_duplicates:
        warnings.append(f"{order_duplicates:,} repeated order identifier(s) found; they may be valid line items.")
    return {
        "rows": len(frame), "columns": len(frame.columns), "missing_or_blank": missing_or_blank,
        "duplicate_rows": int(frame.duplicated().sum()), "duplicate_order_ids": order_duplicates,
        "invalid_dates": invalid_dates, "conversion_failures": conversion_failures,
        "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        "distinct_values": {str(column): int(frame[column].nunique(dropna=True)) for column in frame.columns},
        "suspicious_values": suspicious_values, "errors": errors, "warnings": warnings,
    }


def mapped_dimensions(mapping: dict[str, str | None]) -> list[str]:
    """Dimensions genuinely supplied by a source, for dynamic filters/charts."""
    return [
        field for field in (
            "order_id", "order_date", "category", "product_name", "city",
            "region", "sales_rep", "payment_method", "customer",
        ) if mapping.get(field)
    ]


def inspect_excel_visuals(content: bytes, sheet_name: str) -> dict[str, object]:
    """Report embedded Excel visuals without treating them as source data.

    Excel chart rendering is not portable to Streamlit; the dashboard recreates
    analytics from the selected worksheet instead. Images can be surfaced when
    openpyxl can safely read them.
    """
    try:
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(content), read_only=False, data_only=True)
        worksheet = workbook[sheet_name]
        chart_types = sorted({type(chart).__name__ for chart in worksheet._charts})
        with zipfile.ZipFile(BytesIO(content)) as archive:
            map_like = any(
                (name.startswith("xl/charts/") and b"geo" in archive.read(name).lower())
                for name in archive.namelist()
            )
        return {"chart_count": len(worksheet._charts), "chart_types": chart_types,
                "image_count": len(worksheet._images), "map_like": map_like}
    except Exception as error:  # Unsupported legacy/third-party drawings are informational only.
        return {"chart_count": 0, "chart_types": [], "image_count": 0, "map_like": False,
                "notice": f"Embedded visual inspection is unavailable: {error}"}


def _read_chart_reference(workbook, formula: str | None) -> list[object]:
    """Read a simple Excel chart range referenced by an openpyxl formula."""
    if not formula or "!" not in formula:
        return []
    match = re.search(r"(?:'([^']+)'|([^!]+))!\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)", formula)
    if not match:
        single = re.search(r"(?:'([^']+)'|([^!]+))!\$?([A-Z]+)\$?(\d+)$", formula)
        if not single:
            return []
        sheet_name = single.group(1) or single.group(2)
        if sheet_name not in workbook.sheetnames:
            return []
        from openpyxl.utils.cell import column_index_from_string
        return [workbook[sheet_name].cell(
            row=int(single.group(4)), column=column_index_from_string(single.group(3))
        ).value]
    sheet_name = match.group(1) or match.group(2)
    if sheet_name not in workbook.sheetnames:
        return []
    sheet = workbook[sheet_name]
    from openpyxl.utils.cell import range_boundaries
    first_col, first_row, last_col, last_row = range_boundaries(
        f"{match.group(3)}{match.group(4)}:{match.group(5)}{match.group(6)}"
    )
    return [sheet.cell(row=row, column=first_col).value for row in range(first_row, last_row + 1)]


def extract_excel_chart_data(content: bytes, sheet_name: str) -> list[dict[str, object]]:
    """Extract data for common native Excel charts for a safe Streamlit preview.

    This supports charts whose series use direct worksheet ranges. Pivot charts,
    unsupported chart objects, and map charts are reported as unavailable rather
    than being treated as ordinary tabular data.
    """
    try:
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(content), read_only=False, data_only=True)
        worksheet = workbook[sheet_name]
        supported = {
            "BarChart": "bar", "LineChart": "line", "AreaChart": "area",
            "PieChart": "pie", "DoughnutChart": "doughnut",
        }
        charts: list[dict[str, object]] = []
        for chart in worksheet._charts:
            chart_type = supported.get(type(chart).__name__)
            if not chart_type:
                continue
            series_data: dict[str, list[object]] = {}
            categories: list[object] = []
            for position, series in enumerate(chart.series):
                values_ref = getattr(getattr(series, "val", None), "numRef", None)
                if values_ref is None:
                    values_ref = getattr(getattr(series, "yVal", None), "numRef", None)
                values = _read_chart_reference(workbook, getattr(values_ref, "f", None))
                category_ref = getattr(getattr(series, "cat", None), "numRef", None)
                if category_ref is None:
                    category_ref = getattr(getattr(series, "cat", None), "strRef", None)
                if not categories:
                    categories = _read_chart_reference(workbook, getattr(category_ref, "f", None))
                title_ref = getattr(getattr(series, "tx", None), "strRef", None)
                title_values = _read_chart_reference(workbook, getattr(title_ref, "f", None))
                title = str(title_values[0]) if title_values and title_values[0] is not None else f"Series {position + 1}"
                if values:
                    series_data[title] = values
            if not categories or not series_data:
                continue
            row_count = min(len(categories), *(len(values) for values in series_data.values()))
            frame = pd.DataFrame({"category": categories[:row_count]})
            for title, values in series_data.items():
                frame[title] = values[:row_count]
            charts.append({"chart_type": chart_type, "data": frame})
        return charts
    except Exception:
        return []
