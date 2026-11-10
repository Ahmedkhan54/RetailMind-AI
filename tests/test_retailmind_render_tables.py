"""Regression tests for the table/matrix rendering helpers.

These cover the ``NameError: name '_measure_label' is not defined`` defect that
broke the Product Performance table and every auto dashboard page containing a
table.  The helper is pure pandas so it can be asserted without Streamlit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from retailmind.models import Component
from retailmind.render import table_frame
from retailmind.schema import infer_schema


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Product": ["A", "A", "B", "C"],
            "Revenue": [10.0, 20.0, np.nan, np.nan],
            "Profit": [2.0, 4.0, 6.0, np.nan],
            "Quantity": [1, 2, 3, 4],
        }
    )


def test_table_sums_measure_and_extras():
    table = table_frame(frame(), Component(type="table", dimension="Product", measure="Revenue"), infer_schema(frame()))
    assert list(table["Product"]) == ["A", "B", "C"]
    assert table.loc[table["Product"] == "A", "Revenue"].iloc[0] == 30.0
    # An all-missing group stays missing instead of becoming a fabricated zero.
    assert np.isnan(table.loc[table["Product"] == "B", "Revenue"].iloc[0])
    assert table.loc[table["Product"] == "C", "Quantity"].iloc[0] == 4


def test_matrix_shows_sum_and_mean():
    table = table_frame(frame(), Component(type="matrix", dimension="Product", measure="Revenue"), infer_schema(frame()))
    assert "Revenue (Sum)" in table.columns
    assert "Revenue (Mean)" in table.columns
    assert table.loc[table["Product"] == "A", "Revenue (Sum)"].iloc[0] == 30.0
    assert table.loc[table["Product"] == "A", "Revenue (Mean)"].iloc[0] == 15.0


def test_explicit_average_aggregation():
    table = table_frame(
        frame(),
        Component(type="table", dimension="Product", measure="Revenue", aggregation="average"),
        infer_schema(frame()),
    )
    assert "Revenue (Mean)" in table.columns
    assert table.loc[table["Product"] == "A", "Revenue (Mean)"].iloc[0] == 15.0


def test_table_without_measure_summarises_role_columns():
    table = table_frame(frame(), Component(type="table", dimension="Product", measure=None), infer_schema(frame()))
    # Profit/quantity come from schema roles even without an explicit measure.
    assert list(table.columns) == ["Product", "Profit", "Quantity"]
    assert table.loc[table["Product"] == "A", "Quantity"].iloc[0] == 3


def test_table_missing_dimension_falls_back_to_rows():
    table = table_frame(frame(), Component(type="table", dimension=None, measure="Revenue"), infer_schema(frame()))
    assert len(table) == len(frame())


def test_table_missing_values_are_preserved():
    table = table_frame(frame(), Component(type="table", dimension="Product", measure="Profit"), infer_schema(frame()))
    assert np.isnan(table.loc[table["Product"] == "C", "Profit"].iloc[0])
