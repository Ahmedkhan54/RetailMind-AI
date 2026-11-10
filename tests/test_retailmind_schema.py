"""Tests for universal schema profiling and semantic role detection."""

from __future__ import annotations

import unittest

import pandas as pd

from retailmind.schema import (
    DatasetSchema,
    apply_manual_mapping,
    infer_schema,
    profile_report,
)


def retail_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Order_ID": ["A", "B", "C", "D"],
            "Order_Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
            "Customer_Name": ["Alice", "Bob", "Alice", "Carol"],
            "City": ["Delhi", "Pune", "Delhi", "Mumbai"],
            "Product_Category": ["Office", "Tech", "Office", "Tech"],
            "Product_Name": ["Pen", "Phone", "Pad", "Laptop"],
            "Quantity": [2, 1, 3, 1],
            "Sales": [100.0, 200.0, 150.0, 250.0],
            "Profit": [20.0, 50.0, 30.0, 70.0],
        }
    )


def hr_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Employee_ID": ["E1", "E2", "E3"],
            "Employee_Name": ["Asha", "Ravi", "Meera"],
            "Department": ["Sales", "HR", "Sales"],
            "Salary": [50000, 60000, 55000],
            "Attendance_Status": ["Present", "Absent", "Present"],
            "Joining_Date": ["2020-01-01", "2021-02-01", "2019-05-01"],
        }
    )


def education_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Student_ID": ["S1", "S2", "S3"],
            "Student_Name": ["Aarav", "Diya", "Kabir"],
            "Course": ["Math", "Science", "Math"],
            "Marks": [88, 72, 95],
            "Gender": ["F", "M", "F"],
        }
    )


def expense_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Department": ["Ops", "Sales", "HR"],
            "Expense_Date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "Expenses": [1000.0, 2000.0, 1500.0],
        }
    )


class SchemaDetectionTests(unittest.TestCase):
    def test_retail_roles_are_detected_with_confidence_and_candidates(self):
        schema = infer_schema(retail_frame())
        self.assertEqual(schema.role_column("revenue"), "Sales")
        self.assertEqual(schema.role_column("profit"), "Profit")
        self.assertEqual(schema.role_column("quantity"), "Quantity")
        self.assertEqual(schema.role_column("product"), "Product_Name")
        self.assertEqual(schema.role_column("category"), "Product_Category")
        self.assertEqual(schema.role_column("customer"), "Customer_Name")
        self.assertEqual(schema.role_column("city"), "City")
        self.assertEqual(schema.role_column("date"), "Order_Date")
        self.assertEqual(schema.role_column("order_id"), "Order_ID")
        self.assertEqual(schema.domain, "retail")
        for role in ("revenue", "profit", "product"):
            self.assertIn(role, schema.confidence)
            self.assertGreater(schema.confidence[role], 0.5)
            self.assertIn(schema.roles[role], schema.candidates[role])

    def test_text_columns_can_be_dimensions_even_when_unique(self):
        # Regression: a product name that is unique in a tiny dataset must still
        # be detected as a product dimension rather than only a free-text column.
        schema = infer_schema(retail_frame())
        self.assertIn("Product_Name", schema.columns)
        self.assertEqual(schema.role_column("product"), "Product_Name")

    def test_hr_dataset_roles_and_domain(self):
        schema = infer_schema(hr_frame())
        self.assertEqual(schema.role_column("employee_id"), "Employee_ID")
        self.assertEqual(schema.role_column("employee_name"), "Employee_Name")
        self.assertEqual(schema.role_column("department"), "Department")
        self.assertEqual(schema.role_column("salary"), "Salary")
        self.assertEqual(schema.role_column("attendance"), "Attendance_Status")
        self.assertEqual(schema.domain, "hr")
        self.assertIn("Salary", schema.measures)
        self.assertIn("Department", schema.dimensions)

    def test_education_dataset_roles_and_domain(self):
        schema = infer_schema(education_frame())
        self.assertEqual(schema.role_column("student_id"), "Student_ID")
        self.assertEqual(schema.role_column("course"), "Course")
        self.assertEqual(schema.role_column("grade"), "Marks")
        self.assertEqual(schema.role_column("gender"), "Gender")
        self.assertEqual(schema.domain, "education")

    def test_expense_dataset_uses_cost_role_and_does_not_invent_revenue(self):
        schema = infer_schema(expense_frame())
        self.assertEqual(schema.role_column("cost"), "Expenses")
        self.assertFalse(schema.has("revenue"))
        self.assertFalse(schema.has("profit"))
        # Expenses is a measure, not a dimension.
        self.assertIn("Expenses", schema.measures)
        self.assertNotIn("Expenses", schema.dimensions)

    def test_manual_mapping_overrides_and_clears_roles(self):
        schema = infer_schema(retail_frame())
        updated = apply_manual_mapping(schema, {"profit": None, "revenue": "Profit"})
        self.assertNotIn("profit", updated.roles)
        self.assertNotIn("profit", updated.confidence)
        self.assertEqual(updated.role_column("revenue"), "Profit")
        self.assertEqual(updated.confidence["revenue"], 1.0)
        # The original schema is not mutated.
        self.assertEqual(schema.role_column("revenue"), "Sales")

    def test_schema_round_trip(self):
        schema = infer_schema(retail_frame())
        restored = DatasetSchema.from_dict(schema.to_dict())
        self.assertEqual(restored.roles, schema.roles)
        self.assertEqual(restored.columns, schema.columns)
        self.assertEqual(restored.domain, schema.domain)
        self.assertEqual(restored.domain_label, schema.domain_label)

    def test_profile_report_is_factual(self):
        frame = retail_frame()
        schema = infer_schema(frame)
        report = profile_report(frame, schema)
        self.assertEqual(report["total_records"], 4)
        self.assertEqual(report["total_columns"], 9)
        self.assertEqual(report["duplicate_records"], 0)
        self.assertEqual(report["missing_total"], 0)
        self.assertEqual(report["numeric_summary"]["Sales"]["sum"], 700.0)
        self.assertEqual(report["date_ranges"]["Order_Date"]["min"], "2024-01-01")
        self.assertEqual(report["date_ranges"]["Order_Date"]["max"], "2024-01-04")

    def test_profile_report_counts_missing_and_duplicates(self):
        frame = pd.DataFrame({"Sales": [10.0, None, 10.0, None], "Note": ["a", "a", "a", "a"]})
        schema = infer_schema(frame)
        report = profile_report(frame, schema)
        self.assertEqual(report["missing_values"]["Sales"], 2)
        self.assertEqual(report["duplicate_records"], 2)


if __name__ == "__main__":
    unittest.main()
