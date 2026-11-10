"""Tests for the allowlisted, validated AI Dashboard Assistant."""

from __future__ import annotations

import unittest

import pandas as pd

from retailmind.ai.assistant import (
    AssistantAction,
    apply_action,
    parse_command,
    parse_with_llm,
)
from retailmind.engine import build_dashboard
from retailmind.models import Component, DashboardConfig
from retailmind.schema import infer_schema


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


class FakeProvider:
    """Duck-typed provider that returns a fixed JSON payload."""

    def __init__(self, payload, available: bool = True) -> None:
        self.payload = payload
        self.available = available
        self.calls = 0

    def json_chat(self, messages, *, max_tokens: int = 700):  # noqa: ANN001
        self.calls += 1
        return self.payload


class AssistantParseTests(unittest.TestCase):
    def setUp(self):
        self.frame = retail_frame()
        self.schema = infer_schema(self.frame)
        self.config = build_dashboard(self.frame, self.schema, "retail.csv", "ds-1")

    def _parse(self, command: str, selected: str | None = None) -> AssistantAction:
        return parse_command(command, self.config, self.schema, selected)

    def test_theme_and_accent_commands(self):
        theme = self._parse("change the dashboard theme to light")
        self.assertEqual(theme.action, "set_theme")
        self.assertEqual(theme.params["preset"], "light")
        self.assertTrue(theme.valid)

        accent = self._parse("set accent to #ff0000")
        self.assertEqual(accent.action, "set_accent")
        self.assertEqual(accent.params["accent"], "#ff0000")

        invalid_accent = self._parse("set accent to red")
        self.assertEqual(invalid_accent.action, "unknown")

    def test_add_kpi_is_matched_to_a_real_column(self):
        action = self._parse("add a total revenue KPI card")
        self.assertEqual(action.action, "add_kpi")
        self.assertEqual(action.params["role"], "revenue")
        self.assertEqual(action.params["measure"], "Sales")
        self.assertEqual(action.params["format"], "currency")

    def test_add_pie_chart_uses_real_dimension_and_measure(self):
        action = self._parse("show revenue by category as a pie chart")
        self.assertEqual(action.action, "add_chart")
        self.assertEqual(action.params["chart_type"], "pie")
        self.assertEqual(action.params["dimension"], "Product_Category")
        self.assertEqual(action.params["measure"], "Sales")

    def test_date_filter(self):
        action = self._parse("add a date filter")
        self.assertEqual(action.action, "add_filter")
        self.assertEqual(action.params["column"], "Order_Date")
        self.assertEqual(action.params["kind"], "date")

    def test_create_page(self):
        action = self._parse("create a customer page")
        self.assertEqual(action.action, "create_page")
        self.assertIn("Customer", action.params["name"])

    def test_destructive_actions_are_flagged(self):
        delete_page = self._parse("delete the Executive Overview page")
        self.assertEqual(delete_page.action, "delete_page")
        self.assertTrue(delete_page.destructive)
        self.assertEqual(delete_page.params["page"], "Executive Overview")

        chart = self.config.find_chart()
        delete_chart = self._parse("delete this chart", selected=chart.id)
        self.assertEqual(delete_chart.action, "delete_component")
        self.assertTrue(delete_chart.destructive)
        self.assertEqual(delete_chart.params["component_id"], chart.id)

        reset = self._parse("reset the dashboard layout")
        self.assertEqual(reset.action, "reset_dashboard")
        self.assertTrue(reset.destructive)

    def test_unknown_command_is_invalid_with_suggestions(self):
        action = self._parse("frobnicate the widget")
        self.assertEqual(action.action, "unknown")
        self.assertFalse(action.valid)
        self.assertTrue(action.suggestions)
        self.assertTrue(action.error)

    def test_empty_command_is_invalid(self):
        action = self._parse("   ")
        self.assertFalse(action.valid)
        self.assertIn("Enter", action.error)


class AssistantApplyTests(unittest.TestCase):
    def setUp(self):
        self.frame = retail_frame()
        self.schema = infer_schema(self.frame)
        self.config = build_dashboard(self.frame, self.schema, "retail.csv", "ds-1")
        self.page_name = self.config.pages[0].name

    def test_valid_add_chart_changes_the_dashboard(self):
        before = self.config.counts()["components"]
        action = AssistantAction(
            "add_chart",
            {"chart_type": "bar", "dimension": "Product_Category", "measure": "Sales", "title": "Sales by category"},
        )
        updated, message = apply_action(self.config, action, self.schema, self.page_name)
        self.assertEqual(updated.counts()["components"], before + 1)
        self.assertIn("Added", message)
        self.assertIsNotNone(updated.page(self.page_name).components[-1])

    def test_invalid_column_is_rejected_without_mutating_state(self):
        action = AssistantAction(
            "add_chart",
            {"chart_type": "bar", "dimension": "Ghost", "measure": "Sales"},
        )
        before = self.config.to_json()
        _updated, message = apply_action(self.config, action, self.schema, self.page_name)
        self.assertIn("not present", message)
        self.assertEqual(self.config.to_json(), before)

    def test_theme_change_updates_the_palette(self):
        action = AssistantAction("set_theme", {"preset": "light"})
        updated, message = apply_action(self.config, action, self.schema, self.page_name)
        self.assertEqual(updated.theme.preset, "light")
        self.assertTrue(updated.theme.palette)
        self.assertIn("light", message.lower())

    def test_change_move_duplicate_and_delete_component(self):
        target = self.config.find_chart()
        page = self.config.page(target.page)
        before = self.config.counts()["components"]

        moved, _ = apply_action(
            self.config,
            AssistantAction("move_component", {"component_id": target.id, "position": "top"}),
            self.schema,
            target.page,
        )
        self.assertEqual(page.components[0].id, target.id)

        duplicated, _ = apply_action(
            self.config,
            AssistantAction("duplicate_component", {"component_id": target.id}),
            self.schema,
            target.page,
        )
        self.assertEqual(duplicated.counts()["components"], before + 1)

        clone = page.components[-1]
        _deleted, message = apply_action(
            self.config,
            AssistantAction("delete_component", {"component_id": clone.id}),
            self.schema,
            target.page,
        )
        self.assertIn("Deleted", message)
        self.assertIsNone(self.config.component(clone.id))

        _changed,  message = apply_action(
            self.config,
            AssistantAction("change_chart_type", {"component_id": target.id, "chart_type": "pie"}),
            self.schema,
            target.page,
        )
        self.assertEqual(self.config.component(target.id).type, "pie")

    def test_create_page_only_uses_existing_columns(self):
        action = AssistantAction("create_page", {"name": "City Breakdown"})
        updated, message = apply_action(self.config, action, self.schema, self.page_name)
        page = updated.page("City Breakdown")
        self.assertIsNotNone(page)
        self.assertIn("Created", message)
        self.assertGreater(len(page.components), 0)
        for component in page.components:
            if component.measure:
                self.assertIn(component.measure, self.schema.columns)
            if component.dimension:
                self.assertIn(component.dimension, self.schema.columns)

    def test_final_page_cannot_be_deleted(self):
        config = DashboardConfig(name="Only page")
        config.add_page("Overview")
        _updated, message = apply_action(
            config, AssistantAction("delete_page", {"page": "Overview"}), self.schema, "Overview"
        )
        self.assertIn("at least one page", message.lower())
        self.assertEqual(len(config.pages), 1)

    def test_filter_is_added_once(self):
        action = AssistantAction("add_filter", {"column": "City", "kind": "category"})
        apply_action(self.config, action, self.schema, self.page_name)
        apply_action(self.config, action, self.schema, self.page_name)
        self.assertEqual(len([f for f in self.config.filters if f.column == "City"]), 1)

    def test_reset_requires_confirmation(self):
        _updated, message = apply_action(
            self.config, AssistantAction("reset_dashboard", {}, destructive=True), self.schema
        )
        self.assertIn("Confirmation", message)


class LLMValidationTests(unittest.TestCase):
    def setUp(self):
        self.frame = retail_frame()
        self.schema = infer_schema(self.frame)
        self.config = build_dashboard(self.frame, self.schema, "retail.csv", "ds-1")

    def test_allowlisted_llm_proposal_is_accepted(self):
        provider = FakeProvider(
            {
                "action": "add_chart",
                "params": {"chart_type": "line", "dimension": "Order_Date", "measure": "Sales"},
                "description": "Add a sales trend.",
            }
        )
        action = parse_with_llm("add a trend", self.config, self.schema, provider)
        self.assertIsNotNone(action)
        self.assertEqual(action.action, "add_chart")
        self.assertEqual(action.source, "llm")
        self.assertTrue(action.valid)
        self.assertEqual(provider.calls, 1)

    def test_non_allowlisted_llm_action_is_rejected(self):
        provider = FakeProvider({"action": "execute_python", "params": {"code": "print(1)"}})
        self.assertIsNone(parse_with_llm("run code", self.config, self.schema, provider))

    def test_invented_column_is_rejected(self):
        provider = FakeProvider(
            {
                "action": "add_chart",
                "params": {"chart_type": "bar", "dimension": "Ghost", "measure": "Sales"},
            }
        )
        self.assertIsNone(parse_with_llm("add ghost chart", self.config, self.schema, provider))

    def test_invented_component_id_is_rejected(self):
        provider = FakeProvider(
            {"action": "delete_component", "params": {"component_id": "does-not-exist"}}
        )
        self.assertIsNone(parse_with_llm("delete it", self.config, self.schema, provider))

    def test_destructive_llm_action_is_flagged(self):
        target = self.config.find_chart()
        provider = FakeProvider(
            {"action": "delete_component", "params": {"component_id": target.id}}
        )
        action = parse_with_llm("delete this chart", self.config, self.schema, provider)
        self.assertIsNotNone(action)
        self.assertTrue(action.destructive)

    def test_unavailable_provider_falls_back(self):
        provider = FakeProvider({"action": "add_chart"}, available=False)
        self.assertIsNone(parse_with_llm("add chart", self.config, self.schema, provider))
        self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
