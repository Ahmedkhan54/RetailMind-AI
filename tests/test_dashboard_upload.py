"""Fixture-backed Streamlit tests for the upload-to-dashboard workflow.

These tests force the upload source through an explicit test environment
setting, so they never need MySQL or modify the configured database.
"""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
import unittest

import pandas as pd

from streamlit.testing.v1 import AppTest
from dashboard import parse_uploaded_dates


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_FIXTURE = (
    b"Order_ID,Order_Date,Customer_Name,City,Region,Product_Category,Product_Name,"
    b"Sales_Rep,Payment_Method,Sales,Profit\n"
    b"A,2025-01-01,Alice,Delhi,North,Office,Pen,Ravi,Card,100,20\n"
    b"B,2025-01-02,Bob,Pune,West,Tech,Phone,Sita,Cash,200,50\n"
    b"C,2025-01-03,Alice,Delhi,North,Office,Pad,Ravi,Card,150,30\n"
)


class DashboardUploadTests(unittest.TestCase):
    def test_excel_serial_dates_are_not_interpreted_as_1970_dates(self):
        dates = parse_uploaded_dates(pd.Series([45658, "2025-01-02"]))
        self.assertEqual(dates.iloc[0].date().isoformat(), "2025-01-01")
        self.assertEqual(dates.iloc[1].date().isoformat(), "2025-01-02")

    @classmethod
    def setUpClass(cls):
        cls._previous_source = os.environ.get("RETAIL_DASHBOARD_DEFAULT_SOURCE")
        os.environ["RETAIL_DASHBOARD_DEFAULT_SOURCE"] = "Upload CSV or Excel"
        os.environ["RETAIL_DASHBOARD_TEST_AUTH"] = "1"

    @classmethod
    def tearDownClass(cls):
        if cls._previous_source is None:
            os.environ.pop("RETAIL_DASHBOARD_DEFAULT_SOURCE", None)
        else:
            os.environ["RETAIL_DASHBOARD_DEFAULT_SOURCE"] = cls._previous_source
        os.environ.pop("RETAIL_DASHBOARD_TEST_AUTH", None)

    def app_with_upload_setup(self):
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10)
        app.run()
        self.assertFalse(app.exception)
        app.file_uploader(key="data_upload_999").set_value(("fixture.csv", CSV_FIXTURE, "text/csv")).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(header.value == "Overview" for header in app.header))
        self.assertFalse(any(button.label == "Generate dashboard" for button in app.button))
        self.assertFalse(any(widget.label == "Order Id" for widget in app.selectbox))
        return app

    def test_csv_upload_automatically_renders_kpis_charts_filters_and_preview(self):
        app = self.app_with_upload_setup()

        self.assertFalse(app.exception)
        self.assertTrue(any(header.value == "Overview" for header in app.header))
        self.assertGreaterEqual(len(app.metric), 1)
        self.assertTrue(any(element.type == "vega_lite_chart" for element in app))
        self.assertTrue(any(widget.label == "Category" for widget in app.multiselect))
        self.assertGreaterEqual(len(app.dataframe), 1)
        self.assertFalse(any(info.value == "Review the validation results and select Generate dashboard to analyse this uploaded data." for info in app.info))

    def test_csv_filter_changes_kpis_and_reset_restores_values(self):
        app = self.app_with_upload_setup()
        baseline_sales = next(metric.value for metric in app.metric if metric.label == "Total sales")

        app.multiselect(key=next(widget.key for widget in app.multiselect if widget.label == "City")).set_value(["Delhi"]).run()
        self.assertFalse(app.exception)
        self.assertNotEqual(next(metric.value for metric in app.metric if metric.label == "Total sales"), baseline_sales)

        app.button(key=next(button.key for button in app.button if button.label == "Reset filters")).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "Total sales"), baseline_sales)

    def test_excel_fixture_automatically_renders_dashboard(self):
        stream = BytesIO()
        pd.read_csv(BytesIO(CSV_FIXTURE)).to_excel(stream, index=False)
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10).run()
        self.assertFalse(app.exception)
        app.file_uploader(key="data_upload_999").set_value(("fixture.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")).run()
        self.assertFalse(app.exception)
        self.assertGreaterEqual(len(app.metric), 1)
        self.assertTrue(any(header.value == "Overview" for header in app.header))

    def test_invalid_or_empty_upload_does_not_render_dashboard(self):
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10).run()
        app.file_uploader(key="data_upload_999").set_value(("empty.csv", b"", "text/csv")).run()
        self.assertFalse(any(header.value == "Overview" for header in app.header))
        self.assertTrue(app.error)

    def test_unknown_schema_generates_generic_dashboard_without_sales_metrics(self):
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10).run()
        payload = b"Event Date,Segment,Amount\n2025-01-01,A,10\n2025-01-02,B,20\n"
        app.file_uploader(key="data_upload_999").set_value(("generic.csv", payload, "text/csv")).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(header.value == "Overview" for header in app.header))
        self.assertTrue(any(metric.label == "Total Amount" for metric in app.metric))
        self.assertFalse(any(metric.label == "Total sales" for metric in app.metric))

    def test_dashboard_starts_without_mysql_configuration(self):
        previous = {key: os.environ.pop(key, None) for key in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")}
        try:
            app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.file_uploader)
        finally:
            for key, value in previous.items():
                if value is not None:
                    os.environ[key] = value

        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10).run()
        app.file_uploader(key="data_upload_999").set_value(("missing-sales.csv", b"City\nDelhi\n", "text/csv")).run()
        self.assertTrue(any(header.value == "Overview" for header in app.header))
        self.assertFalse(app.error)

    def test_dashboard_opens_directly_without_login_or_signup(self):
        previous_auth = os.environ.pop("RETAIL_DASHBOARD_TEST_AUTH", None)
        try:
            app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("RetailMind AI" in title.value for title in app.title))
            self.assertTrue(app.file_uploader)
            self.assertFalse(any("Sign in" in tab.label for tab in app.tabs))
            self.assertFalse(any("Create account" in tab.label for tab in app.tabs))
            self.assertFalse(any(button.label in ("Sign in", "Create account") for button in app.button))
        finally:
            if previous_auth is not None:
                os.environ["RETAIL_DASHBOARD_TEST_AUTH"] = previous_auth

    def test_upload_only_full_pipeline_csv_and_excel_workflow(self):
        # 1. Test CSV complete pipeline
        app_csv = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10).run()
        self.assertFalse(app_csv.exception)
        app_csv.file_uploader(key="data_upload_999").set_value(("sales.csv", CSV_FIXTURE, "text/csv")).run()
        self.assertFalse(app_csv.exception)
        self.assertTrue(any(header.value == "Overview" for header in app_csv.header))

        # Check KPIs
        metric_labels = [m.label for m in app_csv.metric]
        self.assertIn("Total records", metric_labels)
        self.assertIn("Total sales", metric_labels)
        self.assertIn("Total profit", metric_labels)

        # Check Downloads
        download_labels = [btn.label for btn in app_csv.download_button]
        self.assertIn("Download cleaned CSV", download_labels)
        self.assertIn("Download cleaned Excel", download_labels)
        self.assertIn("Download executive summary (Markdown)", download_labels)
        self.assertIn("Download executive workbook (Excel)", download_labels)

        # 2. Test Excel complete pipeline
        stream = BytesIO()
        pd.read_csv(BytesIO(CSV_FIXTURE)).to_excel(stream, index=False)
        app_xlsx = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=10).run()
        self.assertFalse(app_xlsx.exception)
        app_xlsx.file_uploader(key="data_upload_999").set_value(
            ("sales.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        ).run()
        self.assertFalse(app_xlsx.exception)
        self.assertTrue(any(header.value == "Overview" for header in app_xlsx.header))
        xlsx_metrics = [m.label for m in app_xlsx.metric]
        self.assertIn("Total sales", xlsx_metrics)


if __name__ == "__main__":
    unittest.main()
