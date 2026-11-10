"""Read-only Streamlit integration tests for dashboard filter state."""
import logging
import os
from io import BytesIO
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DashboardFilterTests(unittest.TestCase):
    CSV_FIXTURE = (b"Order_ID,Order_Date,Customer_Name,City,Product_Category,Product_Name,Sales,Profit\n"
                   b"A,2025-01-01,Alice,Delhi,Office,Pen,100,20\n"
                   b"B,2025-01-02,Bob,Pune,Tech,Phone,200,50\n"
                   b"C,2025-01-03,Alice,Delhi,Office,Pad,150,30\n")
    @classmethod
    def setUpClass(cls):
        cls.previous = os.environ.get("RETAIL_DASHBOARD_DEFAULT_SOURCE")
        os.environ["RETAIL_DASHBOARD_DEFAULT_SOURCE"] = "Upload CSV or Excel"
        os.environ["RETAIL_DASHBOARD_TEST_AUTH"] = "1"

    @classmethod
    def tearDownClass(cls):
        if cls.previous is None: os.environ.pop("RETAIL_DASHBOARD_DEFAULT_SOURCE", None)
        else: os.environ["RETAIL_DASHBOARD_DEFAULT_SOURCE"] = cls.previous
        os.environ.pop("RETAIL_DASHBOARD_TEST_AUTH", None)

    def new_app(self):
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py")
        app.run(timeout=30)
        self.assertFalse(app.exception)
        app.file_uploader(key="data_upload_999").set_value(("fixture.csv", self.CSV_FIXTURE, "text/csv")).run(timeout=30)
        self.assertFalse(app.exception)
        return app

    def test_category_product_dependency_and_reset_state(self):
        app = self.new_app()
        category_widget = next(widget for widget in app.multiselect if widget.label == "Category")
        product_widget = next(widget for widget in app.multiselect if widget.label == "Product")
        categories = list(category_widget.options)
        self.assertGreaterEqual(len(categories), 2)
        self.assertEqual(set(product_widget.value), set(product_widget.options))

        product_options_by_category = {}
        for category in categories[:2]:
            category_app = self.new_app()
            next(widget for widget in category_app.multiselect if widget.label == "Category").set_value([category]).run(timeout=30)
            self.assertFalse(category_app.exception)
            filtered_product_widget = next(widget for widget in category_app.multiselect if widget.label == "Product")
            product_options_by_category[category] = set(filtered_product_widget.options)
            self.assertEqual(set(filtered_product_widget.value), product_options_by_category[category])

        selected_categories = categories[:2]
        category_widget.set_value([selected_categories[0]]).run(timeout=30)
        category_widget = next(widget for widget in app.multiselect if widget.label == "Category")
        category_widget.set_value(selected_categories).run(timeout=30)
        expected_union = product_options_by_category[selected_categories[0]] | product_options_by_category[selected_categories[1]]
        product_widget = next(widget for widget in app.multiselect if widget.label == "Product")
        self.assertEqual(set(product_widget.options), expected_union)

        retained_product = next(iter(product_options_by_category[selected_categories[0]] - product_options_by_category[selected_categories[1]]))
        product_widget.set_value([retained_product])
        category_widget.set_value([selected_categories[1]]).run(timeout=30)
        product_widget = next(widget for widget in app.multiselect if widget.label == "Product")
        self.assertEqual(product_widget.value, [])

        category_widget = next(widget for widget in app.multiselect if widget.label == "Category")
        category_widget.set_value([]).run(timeout=30)
        product_widget = next(widget for widget in app.multiselect if widget.label == "Product")
        self.assertEqual(product_widget.options, [])
        self.assertEqual(product_widget.value, [])

        with self.assertNoLogs("streamlit.elements.lib.policies", level=logging.WARNING):
            next(button for button in app.button if button.label == "Reset filters").click().run(timeout=30)
        self.assertFalse(app.exception)
        category_widget = next(widget for widget in app.multiselect if widget.label == "Category")
        product_widget = next(widget for widget in app.multiselect if widget.label == "Product")
        self.assertEqual(set(category_widget.value), set(categories))
        self.assertEqual(set(product_widget.value), set(product_widget.options))


if __name__ == "__main__":
    unittest.main()
