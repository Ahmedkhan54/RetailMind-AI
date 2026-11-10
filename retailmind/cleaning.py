"""Transparent data cleaning and preparation.

Rules are explicit and reviewable.  The default policy preserves every source
row; de-duplication and row deletion are opt-in.  Invalid numeric values are
coerced to missing values rather than silently becoming zero unless the user
explicitly asks for zero-filling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from retailmind.schema import DatasetSchema
from retailmind.utils import parse_dates


@dataclass
class CleaningSuggestion:
    key: str
    column: str
    issue: str
    count: int
    action: str
    default: bool = True
    risk: str = "low"
    sample: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "column": self.column,
            "issue": self.issue,
            "count": self.count,
            "action": self.action,
            "default": self.default,
            "risk": self.risk,
            "sample": list(self.sample),
        }


@dataclass
class CleaningReport:
    rows_before: int = 0
    rows_after: int = 0
    suggestions: list[CleaningSuggestion] = field(default_factory=list)
    applied: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    original_preserved: bool = True

    @property
    def duplicates_removed(self) -> int:
        return max(0, self.rows_before - self.rows_after)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows_before": self.rows_before,
            "rows_after": self.rows_after,
            "duplicates_removed": self.duplicates_removed,
            "suggestions": [suggestion.to_dict() for suggestion in self.suggestions],
            "applied": dict(self.applied),
            "warnings": list(self.warnings),
            "original_preserved": self.original_preserved,
        }


DEFAULT_OPTIONS: dict[str, bool] = {
    "trim_whitespace": True,
    "normalise_categories": True,
    "parse_dates": True,
    "coerce_numerics": True,
    "drop_duplicate_rows": False,
    "drop_empty_rows": False,
    "fill_invalid_numeric_zero": False,
}


def _blank_mask(series: pd.Series) -> pd.Series:
    """Boolean mask of missing/blank cells without text work on numeric columns."""
    if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return series.isna()
    return series.isna() | series.astype("string").str.strip().eq("").fillna(False)


def _invalid_numeric(series: pd.Series) -> int:
    if pd.api.types.is_numeric_dtype(series):
        return 0
    present = ~_blank_mask(series)
    numeric = pd.to_numeric(series, errors="coerce")
    return int((present & numeric.isna()).sum())


def _whitespace_count(series: pd.Series) -> int:
    if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return 0
    values = series.dropna().astype("string")
    stripped = values.str.strip().str.replace(r"\s+", " ", regex=True)
    return int((values != stripped).sum())


def analyse_cleaning(frame: pd.DataFrame, schema: DatasetSchema) -> list[CleaningSuggestion]:
    """Return factual cleaning suggestions with counts and risk levels."""
    suggestions: list[CleaningSuggestion] = []
    for column in frame.columns:
        series = frame[column]
        blanks = int(_blank_mask(series).sum())
        if blanks:
            suggestions.append(
                CleaningSuggestion(
                    key=f"missing::{column}",
                    column=str(column),
                    issue="Missing or blank values",
                    count=blanks,
                    action="Keep rows; report the missingness (no silent fill).",
                    default=False,
                    risk="low",
                )
            )
        whitespace = _whitespace_count(series)
        if whitespace:
            suggestions.append(
                CleaningSuggestion(
                    key=f"whitespace::{column}",
                    column=str(column),
                    issue="Extra or repeated whitespace",
                    count=whitespace,
                    action="Trim leading/trailing spaces and collapse repeated spaces.",
                    default=True,
                    risk="low",
                )
            )

    for column in schema.dates:
        if column not in frame.columns:
            continue
        series = frame[column]
        present = ~_blank_mask(series)
        parsed = parse_dates(series)
        invalid = int((present & parsed.isna()).sum())
        if invalid:
            suggestions.append(
                CleaningSuggestion(
                    key=f"dates::{column}",
                    column=column,
                    issue="Unparseable date values",
                    count=invalid,
                    action="Convert valid values to datetime; leave invalid values as missing.",
                    default=True,
                    risk="medium",
                )
            )

    for column in schema.numeric:
        if column not in frame.columns:
            continue
        invalid = _invalid_numeric(frame[column])
        if invalid:
            suggestions.append(
                CleaningSuggestion(
                    key=f"numeric::{column}",
                    column=column,
                    issue="Non-numeric values in a numeric column",
                    count=invalid,
                    action="Coerce to numeric and keep invalid values as missing (not zero).",
                    default=True,
                    risk="medium",
                )
            )

    duplicate_rows = int(frame.duplicated().sum())
    if duplicate_rows:
        suggestions.append(
            CleaningSuggestion(
                key="duplicates::rows",
                column="(whole row)",
                issue="Exact duplicate records",
                count=duplicate_rows,
                action="Optionally remove exact duplicate rows.",
                default=False,
                risk="high",
            )
        )

    if len(frame.columns):
        empty_rows = int(frame.isna().all(axis=1).sum())
        if empty_rows:
            suggestions.append(
                CleaningSuggestion(
                    key="empty::rows",
                    column="(whole row)",
                    issue="Completely empty records",
                    count=empty_rows,
                    action="Optionally remove records where every column is empty.",
                    default=False,
                    risk="medium",
                )
            )

    for column in schema.categorical:
        if column not in frame.columns:
            continue
        values = frame[column].dropna().astype("string")
        if values.empty:
            continue
        canonical = values.str.strip().str.replace(r"\s+", " ", regex=True).str.lower()
        variants = int(values.nunique() - canonical.nunique())
        if variants > 0:
            suggestions.append(
                CleaningSuggestion(
                    key=f"categories::{column}",
                    column=column,
                    issue="Case/space variants of the same category",
                    count=variants,
                    action="Normalise to the most common spelling for each value.",
                    default=True,
                    risk="low",
                )
            )
    return suggestions


def _normalise_category(series: pd.Series) -> pd.Series:
    values = series.astype("string")
    cleaned = values.str.strip().str.replace(r"\s+", " ", regex=True)
    key = cleaned.str.lower()
    if key.dropna().empty:
        return series
    # Fast path: if there are no case variants, return cleaned directly
    if key.nunique() == cleaned.nunique():
        return cleaned.where(series.notna(), series)
    # Preserve the most frequent original spelling for each normalised key.
    counts = pd.DataFrame({"key": key, "value": cleaned}).dropna().value_counts().reset_index(name="n")
    if counts.empty:
        return series
    canonical = (
        counts.sort_values(["key", "n"], ascending=[True, False])
        .drop_duplicates("key")
        .set_index("key")["value"]
    )
    return key.map(canonical).where(key.notna(), values)


def apply_cleaning(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    options: dict[str, bool] | None = None,
) -> tuple[pd.DataFrame, CleaningReport]:
    """Apply selected cleaning rules and return a new frame plus a report."""
    chosen = {**DEFAULT_OPTIONS, **(options or {})}
    cleaned = frame.copy()
    report = CleaningReport(rows_before=len(frame), rows_after=len(frame))
    report.applied = {}
    report.warnings = []

    if chosen.get("trim_whitespace", True):
        changed = 0
        for column in cleaned.columns:
            series = cleaned[column]
            if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                values = series.astype("string")
                cleaned_values = values.str.strip().str.replace(r"\s+", " ", regex=True)
                changed += int((values.fillna("") != cleaned_values.fillna("")).sum())
                cleaned[column] = cleaned_values
        if changed:
            report.applied["whitespace_cells"] = changed

    if chosen.get("normalise_categories", True):
        changed = 0
        for column in schema.categorical:
            if column not in cleaned.columns:
                continue
            before = cleaned[column].astype("string").nunique(dropna=True)
            cleaned[column] = _normalise_category(cleaned[column])
            after = cleaned[column].astype("string").nunique(dropna=True)
            changed += max(0, before - after)
        if changed:
            report.applied["category_variants_normalised"] = changed

    if chosen.get("parse_dates", True):
        parsed_columns = 0
        for column in schema.dates:
            if column not in cleaned.columns:
                continue
            cleaned[column] = parse_dates(cleaned[column])
            parsed_columns += 1
        if parsed_columns:
            report.applied["date_columns_parsed"] = parsed_columns

    if chosen.get("coerce_numerics", True):
        coerced = 0
        for column in schema.numeric:
            if column not in cleaned.columns:
                continue
            before = pd.to_numeric(cleaned[column], errors="coerce")
            if chosen.get("fill_invalid_numeric_zero", False):
                before = before.fillna(0)
            cleaned[column] = before
            coerced += 1
        if coerced:
            report.applied["numeric_columns_coerced"] = coerced

    if chosen.get("drop_duplicate_rows", False):
        before = len(cleaned)
        cleaned = cleaned.drop_duplicates()
        removed = before - len(cleaned)
        if removed:
            report.applied["duplicate_rows_removed"] = removed

    if chosen.get("drop_empty_rows", False):
        before = len(cleaned)
        cleaned = cleaned.dropna(how="all")
        removed = before - len(cleaned)
        if removed:
            report.applied["empty_rows_removed"] = removed

    report.rows_after = len(cleaned)
    report.suggestions = analyse_cleaning(frame, schema)
    report.original_preserved = True
    if report.duplicates_removed:
        report.warnings.append(f"{report.duplicates_removed:,} row(s) were removed only because you explicitly enabled it.")
    if "fill_invalid_numeric_zero" in chosen and chosen["fill_invalid_numeric_zero"]:
        report.warnings.append("Invalid numeric values were replaced with zero by explicit choice; totals may be distorted.")
    return cleaned, report


def cleaning_summary(report: CleaningReport) -> pd.DataFrame:
    rows = [
        {"Metric": "Rows before", "Value": str(report.rows_before)},
        {"Metric": "Rows after", "Value": str(report.rows_after)},
        {"Metric": "Rows removed", "Value": str(report.duplicates_removed)},
        {"Metric": "Original data preserved", "Value": "Yes" if report.original_preserved else "No"},
    ]
    for key, value in report.applied.items():
        rows.append({"Metric": key.replace("_", " ").capitalize(), "Value": str(value)})
    return pd.DataFrame(rows)
