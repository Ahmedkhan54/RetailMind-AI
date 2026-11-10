import unittest
from io import BytesIO

import pandas as pd

from data_sources import (detect_column_mapping, extract_excel_chart_data, inspect_excel_worksheets,
                          inspect_excel_visuals, map_to_canonical, mapped_dimensions, preferred_excel_worksheet,
                          profile_data, profile_schema, read_uploaded_file, duplicate_source_columns)


class DataSourceTests(unittest.TestCase):
    def test_schema_profile_detects_dates_measures_dimensions_and_identifiers(self):
        frame = pd.DataFrame({
            "Event date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "Account code": [101, 102, 103],
            "Segment": ["A", "B", "A"],
            "Value": [10.5, 20.0, 30.0],
        })
        schema = profile_schema(frame)
        self.assertEqual(schema["date_columns"], ["Event date"])
        self.assertIn("Account code", schema["identifier_columns"])
        self.assertEqual(schema["measures"], ["Value"])
        self.assertEqual(schema["categorical_columns"], ["Segment"])

    def test_schema_profile_never_uses_high_cardinality_text_as_a_dimension(self):
        schema = profile_schema(pd.DataFrame({"Reference": ["a", "b", "c"], "Amount": [1, 2, 3]}))
        self.assertEqual(schema["categorical_columns"], [])
        self.assertEqual(schema["measures"], ["Amount"])

    def test_duplicate_csv_headers_are_detected_before_dataframe_parsing(self):
        self.assertEqual(
            duplicate_source_columns(b"Sales,Sales,City\n10,11,Delhi\n", "duplicate.csv"),
            ["Sales"],
        )

    def test_detects_common_csv_and_excel_headings(self):
        mapping = detect_column_mapping(["Invoice Number", "Transaction Date", "Department", "Item Name", "Town", "Revenue", "Net Profit"])
        self.assertEqual(mapping["order_id"], "Invoice Number")
        self.assertEqual(mapping["order_date"], "Transaction Date")
        self.assertEqual(mapping["product_name"], "Item Name")
        self.assertEqual(mapping["sales"], "Revenue")
        self.assertEqual(mapping["profit"], "Net Profit")

    def test_detects_dataset_specific_underscore_and_short_aliases(self):
        mapping = detect_column_mapping(["Order_ID", "Date", "Product_Category", "Product", "City", "Total_Sales", "Profit"])
        self.assertEqual(mapping, {
            "order_id": "Order_ID", "order_date": "Date", "category": "Product_Category",
            "product_name": "Product", "city": "City", "sales": "Total_Sales", "profit": "Profit",
            "region": None, "sales_rep": None, "payment_method": None, "quantity": None,
            "unit_price": None, "customer": None, "discount": None,
        })
        missing = detect_column_mapping(["Revenue", "Date"])
        self.assertIsNone(missing["city"])
        self.assertIsNone(missing["category"])
        self.assertIsNone(missing["product_name"])

    def test_detects_requested_semantic_source_columns_case_insensitively(self):
        mapping = detect_column_mapping([
            "ORDER_ID", "Order_Date", "Customer_Name", "City", "Region",
            "Product_Category", "Product_Name", "Sales_Rep", "Payment_Method",
            "Total_Sales", "Net_Profit",
        ])
        self.assertEqual(mapping["order_id"], "ORDER_ID")
        self.assertEqual(mapping["order_date"], "Order_Date")
        self.assertEqual(mapping["customer"], "Customer_Name")
        self.assertEqual(mapping["category"], "Product_Category")
        self.assertEqual(mapping["product_name"], "Product_Name")
        self.assertEqual(mapping["sales_rep"], "Sales_Rep")
        self.assertEqual(mapping["payment_method"], "Payment_Method")
        self.assertEqual(mapping["sales"], "Total_Sales")
        self.assertEqual(mapping["profit"], "Net_Profit")

    def test_mapping_keeps_source_read_only_and_supplies_optional_defaults(self):
        source = pd.DataFrame({"Revenue": [125], "Category": ["Office"]})
        original_columns = source.columns.tolist()
        mapping = detect_column_mapping(source.columns)
        result, defaults = map_to_canonical(source, mapping)
        self.assertEqual(original_columns, source.columns.tolist())
        self.assertEqual(result.loc[0, "sales"], 125)
        self.assertEqual(result.loc[0, "order_id"], "uploaded-1")
        self.assertIn("profit", defaults)
        self.assertEqual(mapped_dimensions(mapping), ["category"])

    def test_sales_mapping_is_required(self):
        with self.assertRaisesRegex(ValueError, "sales/revenue"):
            map_to_canonical(pd.DataFrame({"City": ["Delhi"]}), detect_column_mapping(["City"]))

    def test_profile_reports_clear_error_when_sales_cannot_be_detected(self):
        profile = profile_data(pd.DataFrame({"City": ["Delhi"]}), detect_column_mapping(["City"]))
        self.assertTrue(profile["errors"])
        self.assertIn("could not be detected", profile["errors"][0])

    def test_reads_csv_bytes(self):
        frame = read_uploaded_file(b"Revenue,City\n99,Delhi\n", "sample.csv")
        self.assertEqual(frame.to_dict("records"), [{"Revenue": 99, "City": "Delhi"}])

    def test_reads_excel_bytes(self):
        stream = BytesIO()
        pd.DataFrame({"Sales Amount": [145], "City": ["Pune"]}).to_excel(stream, index=False)
        frame = read_uploaded_file(stream.getvalue(), "sample.xlsx")
        self.assertEqual(frame.to_dict("records"), [{"Sales Amount": 145, "City": "Pune"}])

    def test_rejects_invalid_csv_and_excel_payloads_with_safe_errors(self):
        with self.assertRaisesRegex(ValueError, "Could not read"):
            read_uploaded_file(b"", "empty.csv")
        with self.assertRaisesRegex(ValueError, "Could not read the Excel workbook"):
            inspect_excel_worksheets(b"not-an-excel-workbook")

    def test_prefers_tabular_sales_sheet_over_formatted_dashboard_sheet(self):
        stream = BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            pd.DataFrame({"Unnamed: 0": ["Retail dashboard"], "Unnamed: 1": [None]}).to_excel(
                writer, sheet_name="Dashboard_Dark", index=False
            )
            pd.DataFrame({
                "Order_ID": ["A-100"], "Order_Date": ["2025-01-01"], "City": ["Delhi"],
                "Product_Category": ["Office"], "Product_Name": ["Notebook"], "Units_Sold": [2],
                "Total_Sales": [250], "Profit": [50],
            }).to_excel(writer, sheet_name="Sheet1", index=False)
            pd.DataFrame({"Calculation": [1]}).to_excel(writer, sheet_name="Calc", index=False)
        content = stream.getvalue()
        worksheets = inspect_excel_worksheets(content)
        self.assertEqual([sheet["name"] for sheet in worksheets], ["Dashboard_Dark", "Sheet1", "Calc"])
        self.assertEqual(preferred_excel_worksheet(content), "Sheet1")
        frame = read_uploaded_file(content, "Sales_Performance_Dashboard.xlsx", sheet_name="Sheet1")
        mapping = detect_column_mapping(frame.columns)
        self.assertEqual(mapping, {
            "order_id": "Order_ID", "order_date": "Order_Date", "category": "Product_Category",
            "product_name": "Product_Name", "city": "City", "sales": "Total_Sales", "profit": "Profit",
            "region": None, "sales_rep": None, "payment_method": None, "quantity": "Units_Sold",
            "unit_price": None, "customer": None, "discount": None,
        })

    def test_detects_extra_dimensions_and_numeric_fields(self):
        mapping = detect_column_mapping(["Region", "Sales_Rep", "Payment_Method", "Unit_Price", "Discount_%", "Total_Sales"])
        self.assertEqual(mapping["region"], "Region")
        self.assertEqual(mapping["sales_rep"], "Sales_Rep")
        self.assertEqual(mapping["payment_method"], "Payment_Method")
        self.assertEqual(mapping["unit_price"], "Unit_Price")
        self.assertEqual(mapping["discount"], "Discount_%")

    def test_mapped_dimensions_include_supported_identifier_dimensions(self):
        mapping = {
            "order_id": "Order_ID", "order_date": "Order_Date", "customer": "Customer_ID",
            "category": "Category", "product_name": "Product", "city": "City",
            "region": "Region", "sales_rep": "Sales_Rep", "payment_method": "Payment",
        }
        self.assertEqual(mapped_dimensions(mapping), [
            "order_id", "order_date", "category", "product_name", "city",
            "region", "sales_rep", "payment_method", "customer",
        ])

    def test_excel_visual_inspection_is_graceful_for_plain_workbooks(self):
        stream = BytesIO()
        pd.DataFrame({"Total_Sales": [100]}).to_excel(stream, sheet_name="Sales", index=False)
        visuals = inspect_excel_visuals(stream.getvalue(), "Sales")
        self.assertEqual(visuals["chart_count"], 0)
        self.assertEqual(visuals["image_count"], 0)

    def test_extracts_supported_excel_chart_ranges_for_preview(self):
        from openpyxl.chart import BarChart, Reference
        stream = BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            pd.DataFrame({"City": ["Delhi", "Pune"], "Sales": [100, 200]}).to_excel(
                writer, sheet_name="Sales", index=False
            )
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(stream.getvalue()))
        worksheet = workbook["Sales"]
        chart = BarChart()
        chart.add_data(Reference(worksheet, min_col=2, min_row=1, max_row=3), titles_from_data=True)
        chart.set_categories(Reference(worksheet, min_col=1, min_row=2, max_row=3))
        worksheet.add_chart(chart, "D2")
        output = BytesIO()
        workbook.save(output)
        charts = extract_excel_chart_data(output.getvalue(), "Sales")
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]["chart_type"], "bar")
        self.assertEqual(charts[0]["data"].to_dict("records"), [
            {"category": "Delhi", "Sales": 100}, {"category": "Pune", "Sales": 200}
        ])

    def test_profile_reports_data_quality_without_mutating_source(self):
        source = pd.DataFrame({
            "Order_ID": ["A", "A", ""], "Order_Date": ["2025-01-01", "not-a-date", None],
            "Total_Sales": [100, "bad", 0], "City": ["Rajkot", " ", None],
        })
        original = source.copy(deep=True)
        mapping = detect_column_mapping(source.columns)
        profile = profile_data(source, mapping)
        pd.testing.assert_frame_equal(source, original)
        self.assertEqual(profile["duplicate_order_ids"], 1)
        self.assertEqual(profile["invalid_dates"], 1)
        self.assertEqual(profile["conversion_failures"]["sales"], 1)
        self.assertEqual(profile["missing_or_blank"]["City"], 2)
        self.assertEqual(len(profile["errors"]), 1)
        self.assertIn("invalid numeric", profile["errors"][0])

    def test_profile_blocks_duplicate_mappings_and_invalid_optional_numbers(self):
        source = pd.DataFrame({"Revenue": [100], "Qty": ["not-a-number"]})
        profile = profile_data(source, {"sales": "Revenue", "quantity": "Qty"})
        self.assertTrue(any("invalid numeric" in error for error in profile["errors"]))

        duplicate = profile_data(source, {"sales": "Revenue", "profit": "Revenue"})
        self.assertTrue(any("Duplicate mapping" in error for error in duplicate["errors"]))


if __name__ == "__main__":
    unittest.main()
