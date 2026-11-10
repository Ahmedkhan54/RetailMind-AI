"""Tests for NLP parsing and verified pandas-backed chatbot answers."""

from __future__ import annotations

import unittest

import pandas as pd

from retailmind.ai.chat import answer_question, suggested_questions
from retailmind.ai.nlp import parse_period, parse_question
from retailmind.schema import apply_manual_mapping, infer_schema
from retailmind.utils import money


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


class NLPTests(unittest.TestCase):
    def setUp(self):
        self.frame = retail_frame()
        self.schema = infer_schema(self.frame)

    def test_total_question(self):
        intent = parse_question("What is the total revenue?", self.schema, self.frame)
        self.assertEqual(intent.kind, "total")
        self.assertEqual(intent.metric_role, "revenue")
        self.assertEqual(intent.metric_column, "Sales")
        self.assertTrue(intent.is_actionable)

    def test_top_question_extracts_dimension_and_top_n(self):
        intent = parse_question("Which product has the highest revenue?", self.schema, self.frame)
        self.assertEqual(intent.kind, "top")
        self.assertEqual(intent.dimension_column, "Product_Name")
        self.assertEqual(intent.metric_column, "Sales")
        self.assertEqual(intent.top_n, 10)

        explicit = parse_question("Show the top 2 products by revenue", self.schema, self.frame)
        self.assertEqual(explicit.top_n, 2)
        self.assertEqual(explicit.kind, "top")

    def test_month_trend_uses_the_real_date_column(self):
        intent = parse_question("Show revenue by month", self.schema, self.frame)
        self.assertEqual(intent.dimension_column, "Order_Date")
        self.assertEqual(intent.metric_column, "Sales")

    def test_special_metrics(self):
        aov = parse_question("What is the average order value?", self.schema, self.frame)
        self.assertEqual(aov.special, "aov")
        margin = parse_question("What is the profit margin?", self.schema, self.frame)
        self.assertEqual(margin.special, "margin")

    def test_compare_and_distribution_intents(self):
        compare = parse_question("Compare sales with the previous period", self.schema, self.frame)
        self.assertEqual(compare.kind, "compare")
        self.assertEqual(compare.metric_column, "Sales")
        distribution = parse_question("Show the distribution of profit", self.schema, self.frame)
        self.assertEqual(distribution.kind, "distribution")
        self.assertEqual(distribution.metric_column, "Profit")

    def test_unknown_question_is_not_actionable(self):
        intent = parse_question("Tell me a joke about penguins", self.schema, self.frame)
        self.assertEqual(intent.kind, "unknown")
        self.assertFalse(intent.is_actionable)

    def test_period_parsing_is_relative_to_the_dataset(self):
        reference = pd.Timestamp("2024-01-04")
        month = parse_period("sales in january 2024", reference)
        self.assertEqual(month.start, pd.Timestamp("2024-01-01"))
        self.assertEqual(month.end, pd.Timestamp("2024-01-31"))

        last_days = parse_period("last 30 days", reference)
        self.assertEqual(last_days.start, pd.Timestamp("2023-12-06"))
        self.assertEqual(last_days.end, pd.Timestamp("2024-01-04"))

        quarter = parse_period("q1 2024", reference)
        self.assertEqual(quarter.start, pd.Timestamp("2024-01-01"))
        self.assertEqual(quarter.end, pd.Timestamp("2024-03-31"))


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.frame = retail_frame()
        self.schema = infer_schema(self.frame)

    def test_total_revenue_matches_pandas(self):
        expected = self.frame["Sales"].sum()
        response = answer_question("What is the total revenue?", self.frame, self.schema)
        self.assertTrue(response.verified)
        self.assertIn(money(expected), response.text)
        self.assertFalse(response.used_llm)

    def test_total_profit_matches_pandas(self):
        expected = self.frame["Profit"].sum()
        response = answer_question("What is the total profit?", self.frame, self.schema)
        self.assertIn(money(expected), response.text)

    def test_average_uses_pandas_mean(self):
        expected = self.frame["Sales"].mean()
        response = answer_question("What is the average revenue?", self.frame, self.schema)
        self.assertIn(money(expected), response.text)

    def test_order_count_uses_distinct_order_ids(self):
        expected = self.frame["Order_ID"].nunique()
        response = answer_question("How many orders are there?", self.frame, self.schema)
        self.assertIn(str(expected), response.text)

    def test_top_ranking_matches_pandas(self):
        expected_top = (
            self.frame.groupby("Product_Name")["Sales"].sum().sort_values(ascending=False).index[0]
        )
        response = answer_question("Show the top 2 products by revenue", self.frame, self.schema)
        self.assertIsNotNone(response.table)
        self.assertEqual(len(response.table), 2)
        self.assertIn(expected_top, response.text)
        self.assertEqual(response.table.iloc[0]["Product"], expected_top)

    def test_aov_matches_pandas(self):
        expected = self.frame["Sales"].sum() / self.frame["Order_ID"].nunique()
        response = answer_question("What is the average order value?", self.frame, self.schema)
        self.assertIn(money(expected), response.text)

    def test_margin_matches_pandas(self):
        expected = self.frame["Profit"].sum() / self.frame["Sales"].sum()
        response = answer_question("What is the profit margin?", self.frame, self.schema)
        self.assertIn(f"{expected:.1%}", response.text)

    def test_period_filter_is_applied(self):
        response = answer_question("What was the revenue in the last 2 days?", self.frame, self.schema)
        expected = self.frame[self.frame["Order_Date"] >= pd.Timestamp("2024-01-03")]["Sales"].sum()
        self.assertTrue(response.verified)
        self.assertEqual(response.intent.period.label, "Last 2 days")
        self.assertIn(money(expected), response.text)

    def test_compare_returns_real_period_values(self):
        response = answer_question(
            "Compare sales with the previous period", self.frame, self.schema
        )
        self.assertTrue(response.verified)
        self.assertIn(money(self.frame["Sales"].sum()), response.text)
        self.assertIsNotNone(response.table)

    def test_distribution_returns_real_statistics(self):
        response = answer_question("Show the distribution of profit", self.frame, self.schema)
        self.assertIsNotNone(response.table)
        values = dict(zip(response.table["Statistic"], response.table["Value"]))
        self.assertEqual(values["Count"], len(self.frame))
        self.assertAlmostEqual(float(values["Mean"]), self.frame["Profit"].mean())

    def test_unknown_question_never_invents_numbers(self):
        response = answer_question("Tell me a joke about penguins", self.frame, self.schema)
        self.assertEqual(response.intent.kind, "unknown")
        self.assertIn("never invent a number", response.text)
        self.assertTrue(response.followups)

    def test_unmapped_metric_fails_gracefully(self):
        schema = apply_manual_mapping(self.schema, {"revenue": None})
        response = answer_question("What is the total revenue?", self.frame, schema)
        self.assertEqual(response.intent.kind, "unknown")
        self.assertIn("never invent a number", response.text)
        self.assertTrue(response.followups)

    def test_suggested_questions_only_use_available_roles(self):
        questions = suggested_questions(self.schema)
        self.assertTrue(any("revenue" in question.lower() for question in questions))
        limited = infer_schema(pd.DataFrame({"Note": ["a", "b"]}))
        limited_questions = suggested_questions(limited)
        self.assertTrue(limited_questions)
        self.assertTrue(any("records" in question.lower() for question in limited_questions))


if __name__ == "__main__":
    unittest.main()
