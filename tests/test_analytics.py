import unittest
import pandas as pd
from analytics import (apply_filters, build_summary_report, calculate_kpis,
                       answer_data_question, build_insights, dataframe_to_csv, growth_metric_delta, prepare_data,
                       dataset_fingerprint, filter_defaults, initialise_filter_state,
                       kpi_availability, previous_period_kpis, products_for_categories,
                       retain_valid_products, scoped_filter_keys, upload_generation_identity)


def sample_data():
    return prepare_data(pd.DataFrame({
        "order_id": ["A", "A", "B", "C"], "order_date": ["2025-01-01", "2025-01-01", "2025-01-02", "2024-12-31"],
        "category": ["X", "X", "Y", "Y"], "product_name": ["P", "Q", "P", "R"], "city": ["Delhi", "Delhi", "Pune", "Pune"],
        "sales": [100, 50, 200, 100], "profit": [20, 10, 40, 10]}))


class AnalyticsTests(unittest.TestCase):
    def test_kpis_use_distinct_orders_and_order_level_aov(self):
        kpis = calculate_kpis(sample_data())
        self.assertEqual(kpis["order_count"], 3)
        self.assertEqual(kpis["total_sales"], 450)
        self.assertEqual(kpis["average_order_value"], 150)
        self.assertAlmostEqual(kpis["profit_margin"], 80 / 450)

    def test_filters_are_inclusive_and_empty_selection_is_empty(self):
        data = sample_data()
        result = apply_filters(data, "2025-01-01", "2025-01-01", ["X"], ["Delhi"], ["P", "Q"])
        self.assertEqual(len(result), 2)
        self.assertTrue(apply_filters(data, "2025-01-01", "2025-01-02", [], ["Delhi"], ["P"]).empty)

    def test_previous_period_and_exports(self):
        data = sample_data()
        comparison = previous_period_kpis(data, "2025-01-01", "2025-01-02", ["X", "Y"], ["Delhi", "Pune"], ["P", "Q", "R"])
        self.assertEqual(comparison["previous_sales"], 100)
        self.assertEqual(comparison["sales_change"], 2.5)
        report = build_summary_report(data, {"Date range": "test"}, calculate_kpis(data), ["Test insight"])
        self.assertIn("Total sales: ₹450.00", report)
        self.assertIn(b"order_id", dataframe_to_csv(data))

    def test_empty_kpis_are_safe(self):
        kpis = calculate_kpis(sample_data().iloc[0:0])
        self.assertEqual(kpis["order_count"], 0)
        self.assertIsNone(kpis["profit_margin"])

    def test_category_product_options_and_selection_reconciliation(self):
        data = prepare_data(pd.DataFrame({
            "order_id": ["1", "2", "3", "4"], "order_date": ["2025-01-01"] * 4,
            "category": ["Accessories", "Accessories", "Electronics", "Electronics"],
            "product_name": ["Bag", "Shared", "Phone", "Shared"],
            "city": ["Delhi"] * 4, "sales": [1] * 4, "profit": [1] * 4,
        }))
        self.assertEqual(products_for_categories(data, ["Accessories"]), ["Bag", "Shared"])
        self.assertEqual(products_for_categories(data, ["Accessories", "Electronics"]), ["Bag", "Phone", "Shared"])
        self.assertEqual(products_for_categories(data, []), [])
        self.assertEqual(retain_valid_products(["Bag", "Phone", "Shared"], ["Bag", "Shared"]), ["Bag", "Shared"])
        self.assertEqual(retain_valid_products(["Shared"], products_for_categories(data, ["Electronics"])), ["Shared"])
        self.assertEqual(retain_valid_products(["Bag"], []), [])

    def test_growth_delta_is_neutral_only_when_exactly_zero(self):
        self.assertEqual(growth_metric_delta(0), 0)
        self.assertEqual(growth_metric_delta(0.125), "12.50%")
        self.assertEqual(growth_metric_delta(-0.125), "-12.50%")
        self.assertIsNone(growth_metric_delta(None))

    def test_optional_filter_dimensions_and_dynamic_kpi_availability(self):
        data = sample_data()
        self.assertEqual(len(apply_filters(data, None, None, None, None, None)), len(data))
        self.assertEqual(kpi_availability({"order_id": "Order ID", "profit": None, "order_date": None}),
                         {"orders": True, "profit": False, "date": False, "quantity": False, "discount": False})
        insights = build_insights(data, {"sales_change": None}, {"city"}, include_profit=False)
        self.assertFalse(any("category" in insight.lower() or "product" in insight.lower() for insight in insights))

    def test_current_dataset_options_ignore_blanks_and_do_not_leak_between_datasets(self):
        mapping = {"category": "Category", "city": "City", "product_name": "Product", "order_date": "Date"}
        dataset_a = prepare_data(pd.DataFrame({
            "order_id": ["1", "2", "3"], "order_date": ["2025-01-01", "2025-01-02", ""],
            "category": ["Office", "Office", " "], "product_name": ["Pen", "Pad", None],
            "city": ["Rajkot", " Ahmedabad ", ""], "sales": [1, 2, 3], "profit": [1, 1, 1],
        }))
        dataset_b = prepare_data(pd.DataFrame({
            "order_id": ["4", "5"], "order_date": ["2025-02-01", "2025-02-02"],
            "category": ["Tech", "Tech"], "product_name": ["Phone", "Cable"],
            "city": ["Mumbai", "Pune"], "sales": [4, 5], "profit": [1, 1],
        }))
        defaults_a, defaults_b = filter_defaults(dataset_a, mapping), filter_defaults(dataset_b, mapping)
        self.assertEqual(defaults_a["city_filter"], ["Ahmedabad", "Rajkot"])
        self.assertEqual(defaults_b["city_filter"], ["Mumbai", "Pune"])
        identity_a = dataset_fingerprint(dataset_a, mapping, "upload:a")
        identity_b = dataset_fingerprint(dataset_b, mapping, "upload:b")
        self.assertNotEqual(identity_a, identity_b)
        keys_a, keys_b = scoped_filter_keys(identity_a), scoped_filter_keys(identity_b)
        state = {}
        initialise_filter_state(state, identity_a, {keys_a[name]: value for name, value in defaults_a.items()})
        state[keys_a["city_filter"]] = ["Rajkot"]
        initialise_filter_state(state, identity_b, {keys_b[name]: value for name, value in defaults_b.items()})
        self.assertEqual(state[keys_b["city_filter"]], ["Mumbai", "Pune"])
        self.assertNotIn("Rajkot", state[keys_b["city_filter"]])

    def test_upload_generation_identity_is_stable_and_mapping_specific(self):
        mapping = {"sales": "Total_Sales", "city": "City"}
        first = upload_generation_identity("upload:abc:Sales", mapping)
        self.assertEqual(first, upload_generation_identity("upload:abc:Sales", mapping))
        self.assertNotEqual(first, upload_generation_identity("upload:abc:Returns", mapping))
        self.assertNotEqual(first, upload_generation_identity("upload:abc:Sales", {"sales": "Total_Sales", "city": None}))

    def test_filter_state_switch_does_not_clear_explicit_upload_generation(self):
        state = {"generated_dataset_identity": "approved-upload"}
        initialise_filter_state(state, "new-dataset", {})
        self.assertEqual(state["generated_dataset_identity"], "approved-upload")

    def test_dataset_reset_defaults_and_dependent_products(self):
        data = prepare_data(pd.DataFrame({
            "order_id": ["1", "2", "3"], "order_date": ["2025-01-01"] * 3,
            "category": ["Office", "Office", "Tech"], "product_name": ["Pen", "Pad", "Phone"],
            "city": ["Rajkot"] * 3, "sales": [1, 1, 1], "profit": [1, 1, 1],
        }))
        self.assertEqual(products_for_categories(data, ["Office"]), ["Pad", "Pen"])
        self.assertEqual(retain_valid_products(["Pen", "Phone"], products_for_categories(data, ["Office"])), ["Pen"])
        defaults = filter_defaults(data, {"category": "Category", "product_name": "Product", "city": "City", "order_date": "Date"})
        keys = scoped_filter_keys("new-dataset")
        state = {keys["category_filter"]: ["Tech"], keys["product_filter"]: ["Phone"]}
        initialise_filter_state(state, "new-dataset", {keys[name]: value for name, value in defaults.items()})
        self.assertEqual(state[keys["category_filter"]], defaults["category_filter"])
        self.assertEqual(state[keys["product_filter"]], defaults["product_filter"])

    def test_missing_dimensions_and_empty_dataset_are_safe(self):
        empty = prepare_data(pd.DataFrame(columns=["order_id", "order_date", "category", "product_name", "city", "sales", "profit"]))
        defaults = filter_defaults(empty, {"city": None, "category": None, "product_name": None, "order_date": None})
        self.assertEqual(defaults, {})
        self.assertEqual(products_for_categories(sample_data(), None), ["P", "Q", "R"])

    def test_deterministic_questions_use_only_active_data(self):
        data = sample_data()
        mapping = {"product_name": "Product", "category": "Category", "city": "City", "profit": "Profit"}
        self.assertIn("₹450.00", answer_data_question("What were total sales?", data, mapping, {}))
        self.assertIn("P", answer_data_question("Which product has the highest sales?", data, mapping, {}))
        self.assertIn("unavailable", answer_data_question("How did sales compare with previous period?", data, mapping, {}))

    def test_ask_your_data_supports_top_five_and_sales_profit_totals(self):
        data = prepare_data(pd.DataFrame({
            "order_id": ["1", "2", "3", "4", "5", "6"], "order_date": ["2025-01-01"] * 6,
            "category": ["X"] * 6, "product_name": ["A", "B", "C", "D", "E", "F"],
            "city": ["Delhi"] * 6, "sales": [60, 50, 40, 30, 20, 10], "profit": [6, 5, 4, 3, 2, 1],
        }))
        mapping = {"product_name": "Product", "profit": "Profit"}
        answer = answer_data_question("What are the top five products by sales?", data, mapping, {})
        self.assertIn("Top 5 products", answer)
        self.assertIn("1. A", answer)
        self.assertIn("5. E", answer)
        totals = answer_data_question("What are total sales and profit?", data, mapping, {})
        self.assertIn("₹210.00", totals)
        self.assertIn("₹21.00", totals)

    def test_quantity_is_only_calculated_when_present(self):
        data = sample_data().assign(quantity=[2, 3, 4, 5])
        self.assertEqual(calculate_kpis(data)["quantity_sold"], 14)
        self.assertIsNone(calculate_kpis(sample_data())["quantity_sold"])

    def test_extra_category_and_numeric_filters_use_active_dataset_values(self):
        data = sample_data().assign(region=["West", "West", "North", "North"], unit_price=[10, 20, 30, 40])
        filtered = apply_filters(data, None, None, None, None, None,
                                 {"region": ["West"]}, {"unit_price": (15, 25)})
        self.assertEqual(filtered["order_id"].tolist(), ["A"])
        defaults = filter_defaults(data, {"region": "Region", "unit_price": "Unit Price"})
        self.assertEqual(defaults["region_filter"], ["North", "West"])
        self.assertEqual(defaults["unit_price_range"], (10.0, 40.0))
        customer_data = sample_data().assign(customer=["C1", "C2", "C3", "C4"])
        customer_defaults = filter_defaults(customer_data, {"customer": "Customer ID"})
        self.assertEqual(customer_defaults["customer_filter"], ["C1", "C2", "C3", "C4"])

    def test_every_mapped_filter_uses_its_own_active_column_and_changes_kpis(self):
        data = prepare_data(pd.DataFrame({
            "order_id": ["O1", "O2", "O3"],
            "order_date": ["2025-01-01", "2025-01-02", "2025-01-03"],
            "category": ["Office", "Tech", "Office"],
            "product_name": ["Pen", "Phone", "Pad"],
            "city": ["Delhi", "Pune", "Delhi"],
            "region": ["North", "West", "North"],
            "sales_rep": ["Asha", "Bala", "Asha"],
            "payment_method": ["Card", "Cash", "Card"],
            "customer": ["Alice", "Bob", "Cara"],
            "sales": [100, 250, 50], "profit": [10, 25, 5],
        }))
        mapping = {field: field for field in (
            "order_id", "order_date", "category", "product_name", "city", "region",
            "sales_rep", "payment_method", "customer",
        )}
        defaults = filter_defaults(data, mapping)
        self.assertEqual(defaults["order_id_filter"], ["O1", "O2", "O3"])
        self.assertEqual(defaults["customer_filter"], ["Alice", "Bob", "Cara"])
        self.assertEqual(defaults["region_filter"], ["North", "West"])
        self.assertEqual(defaults["payment_method_filter"], ["Card", "Cash"])
        selected = apply_filters(data, None, None, ["Tech"], ["Pune"], ["Phone"], {
            "order_id": ["O2"], "region": ["West"], "sales_rep": ["Bala"],
            "payment_method": ["Cash"], "customer": ["Bob"],
        })
        self.assertEqual(len(selected), 1)
        self.assertEqual(calculate_kpis(selected)["total_sales"], 250)
        self.assertNotEqual(calculate_kpis(data)["total_sales"], calculate_kpis(selected)["total_sales"])

    def test_previous_period_comparison_honors_extra_and_numeric_filters(self):
        data = prepare_data(pd.DataFrame({
            "order_id": ["old", "new-west", "new-east"],
            "order_date": ["2025-01-01", "2025-01-02", "2025-01-02"],
            "category": ["X", "X", "X"], "product_name": ["P", "P", "P"],
            "city": ["Delhi", "Delhi", "Delhi"], "sales": [100, 150, 300],
            "profit": [10, 15, 30], "region": ["West", "West", "East"],
            "unit_price": [10, 20, 30],
        }))
        comparison = previous_period_kpis(
            data, "2025-01-02", "2025-01-02", ["X"], ["Delhi"], ["P"],
            {"region": ["West"]}, {"unit_price": (10, 20)},
        )
        self.assertEqual(comparison["previous_sales"], 100)
        self.assertEqual(comparison["sales_change"], 0.5)


if __name__ == "__main__":
    unittest.main()
