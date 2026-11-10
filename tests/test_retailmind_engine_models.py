"""Tests for dashboard generation, models and persistence."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

import pandas as pd

from retailmind.engine import build_dashboard, plan_summary, primary_measure
from retailmind.models import Component, DashboardConfig, Page
from retailmind.schema import infer_schema
from retailmind import storage


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


def expense_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Department": ["Ops", "Sales", "HR"],
            "Expense_Date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "Expenses": [1000.0, 2000.0, 1500.0],
        }
    )


class EngineTests(unittest.TestCase):
    def test_auto_dashboard_only_references_existing_columns(self):
        frame = retail_frame()
        schema = infer_schema(frame)
        config = build_dashboard(frame, schema, "retail.csv", "dataset-1")
        self.assertGreater(len(config.pages), 1)
        self.assertGreater(config.counts()["kpis"], 0)
        self.assertGreater(config.counts()["charts"], 0)
        derived_roles = {
            "records", "margin", "orders", "customers", "aov", "growth",
            "avg_salary", "employees", "attendance_rate", "measure_sum",
        }
        for page in config.pages:
            for component in page.components:
                for column in (component.dimension, component.measure, component.measure_y):
                    if column is not None:
                        self.assertIn(column, schema.columns, msg=f"{component.title} uses {column}")
                if component.kpi_role:
                    self.assertIn(component.kpi_role, derived_roles | set(schema.roles))
        self.assertEqual(config.domain, "retail")
        self.assertEqual(config.dataset_name, "retail.csv")

    def test_plan_summary_matches_generated_dashboard(self):
        frame = retail_frame()
        schema = infer_schema(frame)
        config = build_dashboard(frame, schema, "retail.csv", "dataset-1")
        plan = plan_summary(config)
        self.assertEqual(plan.pages, len(config.pages))
        self.assertEqual(plan.kpis, config.counts()["kpis"])
        self.assertEqual(plan.charts, config.counts()["charts"])
        self.assertEqual(plan.domain, "retail")

    def test_dashboard_without_profit_does_not_fabricate_profit_pages(self):
        frame = expense_frame()
        schema = infer_schema(frame)
        self.assertFalse(schema.has("profit"))
        config = build_dashboard(frame, schema, "expenses.csv", "dataset-2")
        titles = [component.title.lower() for page in config.pages for component in page.components]
        self.assertFalse(any("profit" in title for title in titles))
        self.assertFalse(any(page.name == "Profit" for page in config.pages))
        for page in config.pages:
            for component in page.components:
                if component.measure:
                    self.assertIn(component.measure, schema.columns)

    def test_dashboard_survives_dataset_without_measures(self):
        frame = pd.DataFrame({"Note": ["alpha", "beta", "gamma"]})
        schema = infer_schema(frame)
        config = build_dashboard(frame, schema, "notes.csv", "dataset-3")
        self.assertIsNone(primary_measure(schema))
        self.assertGreaterEqual(len(config.pages), 1)
        for page in config.pages:
            for component in page.components:
                if component.measure is not None:
                    self.assertIn(component.measure, schema.columns)


class ModelTests(unittest.TestCase):
    def test_component_and_dashboard_json_round_trip(self):
        config = DashboardConfig(name="Test dashboard")
        page = config.add_page("Overview")
        component = page.add(
            Component(type="bar", title="Revenue by city", dimension="City", measure="Sales")
        )
        restored = DashboardConfig.from_json(config.to_json())
        self.assertEqual(restored.name, "Test dashboard")
        self.assertEqual(restored.pages[0].name, "Overview")
        found = restored.component(component.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.dimension, "City")
        self.assertEqual(found.measure, "Sales")

    def test_page_management(self):
        config = DashboardConfig()
        config.add_page("Overview")
        config.add_page("Sales")
        config.add_page("Profit")
        self.assertTrue(config.rename_page("Profit", "Margins"))
        self.assertEqual(config.page_names(), ["Overview", "Sales", "Margins"])
        self.assertTrue(config.move_page("Margins", -1))
        self.assertEqual(config.page_names(), ["Overview", "Margins", "Sales"])
        duplicate = config.duplicate_page("Sales")
        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate.name, "Sales copy")
        self.assertTrue(config.remove_page("Sales copy"))
        # The final page cannot be removed.
        while len(config.pages) > 1:
            config.remove_page(config.page_names()[-1])
        self.assertFalse(config.remove_page(config.page_names()[0]))

    def test_component_operations(self):
        config = DashboardConfig()
        page = config.add_page("Overview")
        first = page.add(Component(type="bar", title="First"))
        second = page.add(Component(type="pie", title="Second"))
        self.assertTrue(page.move_to_top(second.id))
        self.assertEqual(page.components[0].id, second.id)
        clone = page.duplicate(first.id)
        self.assertIsNotNone(clone)
        self.assertIn("copy", clone.title)
        self.assertNotEqual(clone.id, first.id)
        self.assertTrue(page.remove(clone.id))
        self.assertIsNone(config.component("missing"))
        self.assertEqual(page.components[-1].order, len(page.components) - 1)

    def test_unknown_fields_are_ignored_when_loading(self):
        component = Component.from_dict({"type": "line", "title": "T", "unknown": "x"})
        self.assertEqual(component.title, "T")
        self.assertEqual(component.type, "line")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.dict(os.environ, {"RETAILMIND_STATE_DIR": self._tmp.name})
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _config(self) -> DashboardConfig:
        config = DashboardConfig(name="Persisted", dataset_id="ds-1", dataset_name="data.csv")
        config.add_page("Overview").add(Component(type="kpi", title="Revenue", kpi_role="revenue"))
        return config

    def test_save_load_list_and_delete(self):
        config = self._config()
        path = storage.save_dashboard(config)
        self.assertTrue(path.exists())
        loaded = storage.load_dashboard(path)
        self.assertEqual(loaded.name, "Persisted")
        self.assertEqual(loaded.dataset_name, "data.csv")
        entries = [entry for entry in storage.list_dashboards() if entry["id"] == config.id]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["pages"], 1)
        self.assertTrue(storage.delete_dashboard(path))
        self.assertFalse(path.exists())

    def test_autosave_uses_dataset_identity_and_never_embeds_data(self):
        config = self._config()
        path = storage.autosave(config)
        payload = path.read_text(encoding="utf-8")
        self.assertIn("Persisted", payload)
        self.assertNotIn("Alice", payload)
        self.assertIn("autosave-ds-1.json", path.name)

    def test_undo_redo_round_trip(self):
        state: dict[str, object] = {}
        original = self._config()
        storage.push_undo(state, original)
        self.assertTrue(storage.can_undo(state))

        changed = original.clone()
        changed.name = "Changed"
        restored = storage.undo(state, changed)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.name, "Persisted")
        self.assertTrue(storage.can_redo(state))

        redone = storage.redo(state, restored)
        self.assertIsNotNone(redone)
        self.assertEqual(redone.name, "Changed")
        self.assertFalse(storage.can_redo(state))

        storage.clear_history(state)
        self.assertFalse(storage.can_undo(state))
        self.assertFalse(storage.can_redo(state))


if __name__ == "__main__":
    unittest.main()
