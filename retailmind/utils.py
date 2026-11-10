"""Shared, dependency-light helpers used across RetailMind AI."""

from __future__ import annotations

from io import BytesIO
import hashlib
import math
import re
from typing import Any

import pandas as pd


CURRENCY = "₹"


def parse_dates(values: pd.Series) -> pd.Series:
    """Parse text dates and Excel serial dates without a Unix fallback.

    Excel serial day 1 is 1899-12-31; using origin 1899-12-30 matches Excel's
    leap-year compatibility behaviour.  A naive ``unit="s"`` parse would turn
    serial values into 1970 dates, which is deliberately avoided.
    """
    parsed = pd.to_datetime(values.astype("string"), format="mixed", errors="coerce")
    numeric = pd.to_numeric(values, errors="coerce")
    excel_serial = parsed.isna() & numeric.between(1, 100_000)
    if excel_serial.any():
        parsed.loc[excel_serial] = pd.to_datetime(
            numeric.loc[excel_serial], unit="D", origin="1899-12-30", errors="coerce"
        )
    return parsed


def money(value: float | int | None, currency: str = CURRENCY) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "N/A"
    return f"{currency}{value:,.2f}"


def compact_number(value: float | int | None) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "N/A"
    value = float(value)
    for suffix, size in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if abs(value) >= size:
            return f"{value / size:,.2f}{suffix}"
    return f"{value:,.2f}"


def safe_percent(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    return f"{value:.1%}"


def dataframe_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def excel_bytes(frame: pd.DataFrame, sheet_name: str = "Data") -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet_name[:31] or "Data", index=False)
    return output.getvalue()


def to_python(value: Any) -> Any:
    """Convert numpy/pandas scalars to JSON-safe Python values."""
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): to_python(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_python(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return to_python(value.item())
        except Exception:
            pass
    return str(value)


def slugify(value: str, fallback: str = "dashboard") -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or fallback


def hash_bytes(*parts: bytes) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    return digest.hexdigest()


def format_number(value: Any, fmt: str | None = None) -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return "N/A"
    if fmt == "currency":
        return money(numeric)
    if fmt == "percent":
        return safe_percent(numeric)
    if abs(numeric) >= 1_000_000:
        return f"{numeric / 1_000_000:,.2f}M"
    if float(numeric).is_integer():
        return f"{int(numeric):,}"
    if abs(numeric) >= 10_000:
        return f"{numeric:,.0f}"
    if abs(numeric) >= 1:
        return f"{numeric:,.2f}"
    return f"{numeric:,.4f}"


def safe_divide(numerator: float | int | None, denominator: float | int | None) -> float | None:
    try:
        if denominator in (None, 0):
            return None
        return float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
