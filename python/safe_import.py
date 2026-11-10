"""Non-destructive validation and staged-import primitives.

This module does not connect to MySQL on import and never executes SQL by
itself.  The optional merge helper is deliberately confirmation-gated and is
intended for a separately reviewed operational command, not the dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import logging
import re
from typing import Any, Iterable

import pandas as pd

logger = logging.getLogger(__name__)

SALES_COLUMNS = (
    "order_id", "order_date", "customer_id", "product_name", "category",
    "city", "region", "quantity", "unit_price", "discount_pct", "sales",
    "profit", "payment_method",
)
REQUIRED_TEXT_LENGTHS = {
    "order_id": 20, "product_name": 100, "category": 50, "city": 80,
    "region": 30, "payment_method": 40,
}
DECIMAL_SPECS = {
    "unit_price": (12, 2),
    "discount_pct": (5, 2),
    "sales": (14, 2),
    "profit": (14, 2),
}
INT_RANGE = (-2147483648, 2147483647)
MYSQL_DATE_RANGE = (pd.Timestamp("1000-01-01"), pd.Timestamp("9999-12-31"))
CONFIRMATION_PHRASE = "MERGE STAGING INTO SALES"


@dataclass(frozen=True)
class ImportValidation:
    """Read-only validation and reconciliation result for one candidate batch."""

    valid: bool
    row_count: int
    columns: tuple[str, ...]
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    duplicate_order_ids: tuple[str, ...] = ()
    existing_order_ids: tuple[str, ...] = ()
    totals: dict[str, float] = field(default_factory=dict)
    preview: pd.DataFrame = field(default_factory=pd.DataFrame)


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce")


def _decimal_issues(values: pd.Series, column: str) -> list[str]:
    precision, scale = DECIMAL_SPECS[column]
    integer_digits = precision - scale
    issues: list[str] = []
    for position, value in values.items():
        if pd.isna(value):
            continue
        try:
            decimal_value = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            continue
        if not decimal_value.is_finite():
            continue
        exponent = decimal_value.as_tuple().exponent
        actual_scale = max(0, -exponent)
        actual_integer_digits = max(0, len(decimal_value.as_tuple().digits) - actual_scale)
        if actual_scale > scale or actual_integer_digits > integer_digits:
            issues.append(f"{column} value at row {position} exceeds DECIMAL({precision},{scale}).")
    return issues


def validate_import_frame(frame: pd.DataFrame, *, expected_totals: dict[str, float] | None = None,
                          existing_order_ids: Iterable[object] | None = None,
                          preview_rows: int = 10) -> ImportValidation:
    """Validate a candidate batch without changing it or contacting MySQL."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Import data must be a pandas DataFrame.")
    if preview_rows < 0:
        raise ValueError("preview_rows must be non-negative")

    errors: list[str] = []
    warnings: list[str] = []
    missing = [column for column in SALES_COLUMNS if column not in frame.columns]
    extra = [str(column) for column in frame.columns if column not in SALES_COLUMNS]
    if missing:
        errors.append("Missing required column(s): " + ", ".join(missing) + ".")
    if extra:
        warnings.append("Ignored extra column(s): " + ", ".join(extra) + ".")
    if frame.empty:
        errors.append("The import contains no rows.")

    duplicate_ids: tuple[str, ...] = ()
    existing_ids: tuple[str, ...] = ()
    if "order_id" in frame.columns:
        identifiers = frame["order_id"].astype("string").str.strip()
        if identifiers.isna().any() or identifiers.eq("").any():
            errors.append("order_id contains null or blank values.")
        duplicates = identifiers[identifiers.duplicated(keep=False)].dropna().unique().tolist()
        duplicate_ids = tuple(sorted(str(value) for value in duplicates))
        if duplicate_ids:
            errors.append("Duplicate order_id value(s): " + ", ".join(duplicate_ids) + ".")
        for column, limit in REQUIRED_TEXT_LENGTHS.items():
            if column in frame.columns:
                text_values = identifiers if column == "order_id" else frame[column].astype("string").str.strip()
                if text_values.isna().any() or text_values.eq("").any():
                    errors.append(f"{column} contains null or blank values.")
                too_long = text_values.str.len().gt(limit)
                if too_long.fillna(False).any():
                    errors.append(f"{column} contains value(s) longer than the schema limit ({limit}).")
        if existing_order_ids is not None:
            existing = {str(value).strip() for value in existing_order_ids if not pd.isna(value) and str(value).strip()}
            existing_ids = tuple(sorted(set(identifiers.dropna()) & existing))
            if existing_ids:
                errors.append("order_id value(s) already exist in sales: " + ", ".join(existing_ids) + ".")

    for column in ("order_date", "customer_id", "quantity", "unit_price", "discount_pct", "sales", "profit"):
        if column not in frame.columns:
            continue
        values = frame[column]
        if values.isna().any():
            errors.append(f"{column} contains null values.")
        if column == "order_date":
            parsed = pd.to_datetime(values, errors="coerce", format="mixed")
            if parsed.isna().any():
                errors.append("order_date contains invalid date value(s).")
            elif ((parsed < MYSQL_DATE_RANGE[0]) | (parsed > MYSQL_DATE_RANGE[1])).any():
                errors.append("order_date contains values outside MySQL DATE range (1000-01-01 through 9999-12-31).")
        else:
            numeric = _numeric_series(frame, column)
            if numeric.isna().any():
                errors.append(f"{column} contains non-numeric value(s).")
            if column in {"customer_id", "quantity"} and not numeric.dropna().mod(1).eq(0).all():
                errors.append(f"{column} must contain integer value(s).")
            if column in {"customer_id", "quantity"} and ((numeric < INT_RANGE[0]) | (numeric > INT_RANGE[1])).any():
                errors.append(f"{column} contains value(s) outside MySQL INT range.")
            if column == "quantity" and (numeric <= 0).any():
                errors.append("quantity must be greater than zero.")
            if column == "unit_price" and (numeric < 0).any():
                errors.append("unit_price cannot be negative.")
            if column == "discount_pct" and ((numeric < 0) | (numeric > 1)).any():
                errors.append("discount_pct must be between 0 and 1.")
            if column in DECIMAL_SPECS:
                errors.extend(_decimal_issues(values, column))

    totals = {}
    for column in ("sales", "profit", "quantity"):
        if column in frame.columns:
            totals[column] = float(_numeric_series(frame, column).sum())
    if expected_totals:
        for column, expected in expected_totals.items():
            actual = totals.get(column)
            if actual is None or abs(actual - float(expected)) > 1e-6:
                errors.append(f"Reconciliation mismatch for {column}: expected {expected}, got {actual}.")

    logger.info("Validated import candidate rows=%s valid=%s errors=%s", len(frame), not errors, len(errors))
    return ImportValidation(
        valid=not errors,
        row_count=len(frame),
        columns=tuple(str(column) for column in frame.columns),
        errors=tuple(errors),
        warnings=tuple(warnings),
        duplicate_order_ids=duplicate_ids,
        existing_order_ids=existing_ids,
        totals=totals,
        preview=frame.head(preview_rows).copy(deep=True),
    )


def build_preview_report(validation: ImportValidation) -> str:
    """Create a safe operator-facing preview/reconciliation report."""
    lines = [
        "Retail sales import preview",
        "=" * 28,
        f"Rows: {validation.row_count:,}",
        f"Columns: {', '.join(validation.columns)}",
        f"Validation: {'PASS' if validation.valid else 'FAIL'}",
        "",
        "Totals:",
    ]
    lines.extend(f"- {key}: {value:,.2f}" for key, value in validation.totals.items())
    if validation.errors:
        lines.extend(["", "Errors:"])
        lines.extend(f"- {error}" for error in validation.errors)
    if validation.warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in validation.warnings)
    lines.extend(["", "Production merge: NOT EXECUTED; explicit operator approval is required."])
    return "\n".join(lines) + "\n"


def staging_table_ddl(table_name: str = "sales_staging") -> str:
    """Return reviewed DDL text; this function never sends it to a database."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError("table_name must be a simple SQL identifier")
    return f"""CREATE TABLE IF NOT EXISTS `{table_name}` (
    order_id VARCHAR(20) NOT NULL,
    order_date DATE NOT NULL,
    customer_id INT NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    city VARCHAR(80) NOT NULL,
    region VARCHAR(30) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    discount_pct DECIMAL(5,2) NOT NULL,
    sales DECIMAL(14,2) NOT NULL,
    profit DECIMAL(14,2) NOT NULL,
    payment_method VARCHAR(40) NOT NULL,
    import_batch_id CHAR(36) NOT NULL,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_{table_name}_batch (import_batch_id),
    INDEX ix_{table_name}_order (order_id)
) ENGINE=InnoDB;"""


def stage_import_frame(connection: Any, frame: pd.DataFrame, validation: ImportValidation, *, import_batch_id: str,
                       staging_table: str = "sales_staging") -> int:
    """Atomically stage a validated batch using bound values, never string SQL values.

    The caller owns connection creation.  Any constraint or duplicate failure rolls
    the entire staging operation back, allowing integration tests to prove InnoDB
    atomicity before an operator authorizes the separate merge step.
    """
    if not validation.valid:
        raise ValueError("Cannot stage an invalid import candidate.")
    if not isinstance(import_batch_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", import_batch_id):
        raise ValueError("import_batch_id must be a 36-character batch identifier.")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", staging_table):
        raise ValueError("staging_table must be a simple SQL identifier")
    columns = ", ".join(SALES_COLUMNS) + ", import_batch_id"
    placeholders = ", ".join(["%s"] * (len(SALES_COLUMNS) + 1))
    cursor = connection.cursor()
    try:
        connection.start_transaction()
        if len(frame) != validation.row_count:
            raise ValueError("The staged frame does not match the validated row count.")
        rows = [tuple(row[column] for column in SALES_COLUMNS) + (import_batch_id,)
                for _, row in frame.loc[:, SALES_COLUMNS].iterrows()]
        cursor.executemany(f"INSERT INTO `{staging_table}` ({columns}) VALUES ({placeholders})", rows)
        connection.commit()
        return len(rows)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def merge_staging_into_sales(connection: Any, validation: ImportValidation, *,
                             confirmation: str, import_batch_id: str | None = None,
                             staging_table: str = "sales_staging") -> None:
    """Guarded insert-only merge primitive for a separately reviewed command.

    This is intentionally not called by the dashboard or tests against a real
    database.  It inserts only new order IDs, uses a transaction, and rolls
    back on any exception.  Existing rows are never deleted or updated.
    """
    if confirmation != CONFIRMATION_PHRASE:
        raise PermissionError(f"Type exactly {CONFIRMATION_PHRASE!r} to authorize a merge.")
    if not validation.valid:
        raise ValueError("Cannot merge an invalid import candidate.")
    if not isinstance(import_batch_id, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", import_batch_id):
        raise ValueError("import_batch_id must be a 36-character batch identifier.")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", staging_table):
        raise ValueError("staging_table must be a simple SQL identifier")
    cursor = connection.cursor()
    try:
        connection.start_transaction()
        cursor.execute(
            f"""INSERT INTO sales ({', '.join(SALES_COLUMNS)})
SELECT {', '.join(SALES_COLUMNS)} FROM `{staging_table}` staged
WHERE staged.import_batch_id = %s
  AND NOT EXISTS (SELECT 1 FROM sales current WHERE current.order_id = staged.order_id)""",
            (import_batch_id,),
        )
        connection.commit()
    except Exception:
        try:
            connection.rollback()
        except Exception as rollback_error:
            logger.exception("Staged sales merge failed and rollback also failed")
            raise RuntimeError("Staged sales merge failed and rollback failed; manual recovery review is required.") from rollback_error
        logger.exception("Staged sales merge rolled back")
        raise
    finally:
        cursor.close()

