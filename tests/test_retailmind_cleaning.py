"""Tests for transparent, non-destructive data cleaning."""

from __future__ import annotations

import unittest

import pandas as pd

from retailmind.cleaning import (
    DEFAULT_OPTIONS,
    analyse_cleaning,
    apply_cleaning,
    cleaning_summary,
)
from retailmind.schema import infer_schema


def messy_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Order_ID": ["A", "A", "B", "C", "D", "E", "F", "G", "H", "I"],
            "Order_Date": [
                "2024-01-01", "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04",
                "2024-01-05", "2024-01-06", "2024-01-07", "2024-01-08", "not a date",
            ],
            "Category": [
                "office", "office", "Office", "Tech", "Tech",
                "Tech", "Tech", "Office", "Tech", "Tech",
            ],
            "Sales": ["100", "100", "200", "300", "400", "500", "600", "700", "800", "oops"],
            "Profit": [10.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0],
        }
    )


class CleaningTests(unittest.TestCase):
    def test_default_cleaning_preserves_every_row_and_the_original_frame(self):
        frame = messy_frame()
        original = frame.copy(deep=True)
        schema = infer_schema(frame)
        cleaned, report = apply_cleaning(frame, schema, DEFAULT_OPTIONS)

        self.assertTrue(report.original_preserved)
        self.assertEqual(report.rows_before, 10)
        self.assertEqual(report.rows_after, 10)
        self.assertEqual(len(cleaned), 10)
        self.assertEqual(report.duplicates_removed, 0)
        # The caller's DataFrame is never mutated.
        pd.testing.assert_frame_equal(frame, original)
        # Duplicate removal is opt-in and therefore never applied silently.
        duplicate_suggestion = next(s for s in report.suggestions if s.key == "duplicates::rows")
        self.assertFalse(duplicate_suggestion.default)
        self.assertEqual(duplicate_suggestion.risk, "high")

    def test_invalid_numeric_becomes_missing_not_zero(self):
        frame = messy_frame()
        schema = infer_schema(frame)
        cleaned, _report = apply_cleaning(frame, schema, DEFAULT_OPTIONS)
        self.assertTrue(pd.isna(cleaned.loc[9, "Sales"]))

    def test_zero_filling_requires_explicit_option_and_adds_a_warning(self):
        frame = messy_frame()
        schema = infer_schema(frame)
        cleaned, report = apply_cleaning(
            frame, schema, {"fill_invalid_numeric_zero": True}
        )
        self.assertEqual(cleaned.loc[9, "Sales"], 0)
        self.assertTrue(any("zero" in warning.lower() for warning in report.warnings))

    def test_duplicate_removal_is_explicit_and_reported(self):
        frame = messy_frame()
        schema = infer_schema(frame)
        cleaned, report = apply_cleaning(frame, schema, {"drop_duplicate_rows": True})
        self.assertEqual(len(cleaned), 9)
        self.assertEqual(report.duplicates_removed, 1)
        self.assertEqual(report.applied["duplicate_rows_removed"], 1)
        self.assertTrue(report.warnings)

    def test_category_variants_are_normalised_without_deleting_rows(self):
        frame = messy_frame()
        schema = infer_schema(frame)
        cleaned, report = apply_cleaning(frame, schema, DEFAULT_OPTIONS)
        self.assertEqual(len(cleaned), 10)
        categories = cleaned["Category"].dropna().astype(str)
        self.assertEqual(categories.nunique(), 2)
        self.assertFalse(categories.str.startswith(" ").any())
        self.assertIn("category_variants_normalised", report.applied)

    def test_invalid_dates_become_missing_and_are_flagged(self):
        frame = messy_frame()
        schema = infer_schema(frame)
        cleaned, report = apply_cleaning(frame, schema, DEFAULT_OPTIONS)
        self.assertTrue(pd.isna(cleaned.loc[9, "Order_Date"]))
        self.assertTrue(any(s.key == "dates::Order_Date" for s in report.suggestions))

    def test_suggestions_are_factual_and_include_counts(self):
        frame = messy_frame()
        schema = infer_schema(frame)
        suggestions = analyse_cleaning(frame, schema)
        keys = {suggestion.key for suggestion in suggestions}
        self.assertIn("duplicates::rows", keys)
        self.assertIn("numeric::Sales", keys)
        self.assertIn("dates::Order_Date", keys)
        duplicate = next(s for s in suggestions if s.key == "duplicates::rows")
        self.assertEqual(duplicate.count, 1)
        # Every suggestion serialises safely for the UI.
        payload = duplicate.to_dict()
        self.assertEqual(payload["key"], "duplicates::rows")
        self.assertIn("sample", payload)

    def test_cleaning_summary_is_string_safe_for_arrow(self):
        frame = messy_frame()
        schema = infer_schema(frame)
        _cleaned, report = apply_cleaning(frame, schema, DEFAULT_OPTIONS)
        summary = cleaning_summary(report)
        self.assertFalse(summary.empty)
        self.assertTrue(all(isinstance(value, str) for value in summary["Value"]))


if __name__ == "__main__":
    unittest.main()
