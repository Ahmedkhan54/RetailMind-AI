"""Interaction audit tests for every dashboard control.

These tests drive the real Streamlit app with ``AppTest`` and assert that the
controls actually change the dashboard configuration, preserve the uploaded
dataset and give feedback.  File-generation tests write the download payloads
to disk and re-open them to prove the bytes are valid.
"""
from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path
import unittest

import pandas as pd

from streamlit.testing.v1 import AppTest

import dashboard as app_module
from retailmind.ai.insights import generate_insights
from retailmind.cleaning import analyse_cleaning
from retailmind.schema import infer_schema
from retailmind.utils import dataframe_to_csv_bytes, excel_bytes


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV_FIXTURE = (
    b"Order_ID,Order_Date,Customer_Name,City,Region,Product_Category,Product_Name,"
    b"Sales_Rep,Payment_Method,Sales,Profit\n"
    b"A,2025-01-01,Alice,Delhi,North,Office,Pen,Ravi,Card,100,20\n"
    b"B,2025-01-02,Bob,Pune,West,Tech,Phone,Sita,Cash,200,50\n"
    b"C,2025-01-03,Alice,Delhi,North,Office,Pad,Ravi,Card,150,30\n"
)
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ButtonAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous = {
            key: os.environ.get(key)
            for key in ("RETAIL_DASHBOARD_TEST_AUTH", "RETAIL_DASHBOARD_DEFAULT_SOURCE", "RETAILMIND_STATE_DIR")
        }
        os.environ["RETAIL_DASHBOARD_TEST_AUTH"] = "1"
        os.environ["RETAIL_DASHBOARD_DEFAULT_SOURCE"] = "Upload CSV or Excel"

    @classmethod
    def tearDownClass(cls):
        for key, value in cls._previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self):
        self.state_dir = tempfile.mkdtemp(prefix="rm_audit_state_")
        os.environ["RETAILMIND_STATE_DIR"] = self.state_dir

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _app(self) -> AppTest:
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=30).run()
        self.assertFalse(app.exception)
        return app

    def _identity(self, app: AppTest) -> str:
        key = next(
            widget.key
            for widget in app.selectbox
            if widget.key and widget.key.startswith("rm_map_") and widget.key.endswith("_revenue")
        )
        return key[len("rm_map_"):-len("_revenue")]

    def _upload(self, app: AppTest, payload: bytes = CSV_FIXTURE, name: str = "fixture.csv", mime: str = "text/csv"):
        app.file_uploader(key="data_upload_999").set_value((name, payload, mime)).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(header.value == "Overview" for header in app.header))
        return app, self._identity(app)

    def _customize(self, app: AppTest):
        app.radio(key="rm_dashboard_mode").set_value("Customize Dashboard").run()
        self.assertFalse(app.exception)
        return app

    def _click(self, app: AppTest, key: str):
        app.button(key=key).click()
        app.run()
        self.assertFalse(app.exception)
        return app

    def _config(self, app: AppTest, identity: str):
        return app.session_state[f"rm_config_{identity}"]

    def _component_count(self, app: AppTest, identity: str) -> int:
        return len(self._config(app, identity).pages[0].components)

    # ------------------------------------------------------------------
    # upload / filters / rerun persistence
    # ------------------------------------------------------------------
    def test_upload_renders_dashboard_and_survives_reruns(self):
        app = self._app()
        app, identity = self._upload(app)
        self.assertGreaterEqual(len(app.metric), 3)
        self.assertTrue(any(widget.label == "Category" for widget in app.multiselect))
        download_labels = {button.label for button in app.download_button}
        self.assertIn("Download cleaned CSV", download_labels)
        self.assertIn("Download executive workbook (Excel)", download_labels)

        # A plain rerun must keep the uploaded file and the dashboard.
        app.run()
        self.assertFalse(app.exception)
        self.assertIsNotNone(app.file_uploader(key="data_upload_999").value)
        self.assertTrue(any(header.value == "Overview" for header in app.header))
        config = self._config(app, identity)
        self.assertEqual(
            sum(len(page.components) for page in config.pages),
            config.counts()["components"],
        )

    def test_filters_change_values_and_reset_restores_them(self):
        app = self._app()
        app, _ = self._upload(app)
        baseline = next(metric.value for metric in app.metric if metric.label == "Total sales")

        city_key = next(widget.key for widget in app.multiselect if widget.label == "City")
        app.multiselect(key=city_key).set_value(["Delhi"]).run()
        self.assertFalse(app.exception)
        self.assertNotEqual(next(metric.value for metric in app.metric if metric.label == "Total sales"), baseline)

        app.button(key="rm_legacy_reset_filters").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "Total sales"), baseline)

    def test_worksheet_selection_switches_the_loaded_sheet(self):
        first = pd.DataFrame(
            {"Order_ID": ["A"], "Order_Date": ["2025-01-01"], "City": ["Delhi"],
             "Product_Category": ["Office"], "Sales": [100], "Profit": [20]}
        )
        second = pd.DataFrame(
            {"Order_ID": ["B"], "Order_Date": ["2025-02-01"], "City": ["Pune"],
             "Product_Category": ["Tech"], "Sales": [999], "Profit": [111]}
        )
        stream = BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            first.to_excel(writer, sheet_name="First", index=False)
            second.to_excel(writer, sheet_name="Second", index=False)

        app = self._app()
        app, _ = self._upload(app, stream.getvalue(), "book.xlsx", XLSX_MIME)
        sheet_key = next(widget.key for widget in app.selectbox if widget.key.startswith("upload_worksheet_"))
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "Total sales"), "₹100.00")
        app.selectbox(key=sheet_key).set_value("Second").run()
        self.assertFalse(app.exception)
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "Total sales"), "₹999.00")

    def test_cleaning_toggle_rebuilds_the_dashboard(self):
        payload = (
            b"Order_ID,Order_Date,City,Product_Category,Sales,Profit\n"
            b"A,2025-01-01,Delhi,Office,100,20\n"
            b"A,2025-01-01,Delhi,Office,100,20\n"
            b"B,2025-01-02,Pune,Tech,200,50\n"
        )
        app = self._app()
        app, identity = self._upload(app, payload)
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "Total records"), "3")
        app.checkbox(key=f"rm_clean_dupes_{identity}").set_value(True).run()
        self.assertFalse(app.exception)
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "Total records"), "2")
        self.assertIn(f"rm_config_{identity}", app.session_state)

    def test_manual_column_mapping_rebuilds_roles(self):
        payload = b"Event Date,Segment,Amount\n2025-01-01,A,10\n2025-01-02,B,20\n"
        app = self._app()
        app, identity = self._upload(app, payload, "generic.csv")
        self.assertEqual(
            [widget.options for widget in app.selectbox if widget.key == f"rm_map_{identity}_revenue"],
            [["(not mapped)", "Amount"]],
        )
        app.selectbox(key=f"rm_map_{identity}_revenue").set_value("Amount")
        app.button(key=f"FormSubmitter:rm_mapping_form_{identity}-Apply column mapping").click()
        app.run()
        self.assertFalse(app.exception)
        schema = app.session_state[f"rm_manual_schema_{identity}"]
        self.assertEqual(schema.roles.get("revenue"), "Amount")
        self.assertTrue(any("Column mapping applied" in message.value for message in app.success))

    def test_universal_search_filters_records_and_reset_restores(self):
        payload = (
            b"Event Date,Segment,Amount,Channel\n"
            b"2025-01-01,Alpha,10,Web\n"
            b"2025-01-02,Beta,20,Store\n"
            b"2025-01-03,Alpha,30,Web\n"
        )
        app = self._app()
        app, _ = self._upload(app, payload, "generic.csv")
        search_key = next(widget.key for widget in app.text_input if widget.label == "Search records")
        before = next(metric.value for metric in app.metric if metric.label == "Total records")
        app.text_input(key=search_key).set_value("Alpha").run()
        self.assertFalse(app.exception)
        self.assertNotEqual(next(metric.value for metric in app.metric if metric.label == "Total records"), before)

        reset_key = next(button.key for button in app.button if button.key and button.key.endswith("_filter_reset"))
        app.button(key=reset_key).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(next(metric.value for metric in app.metric if metric.label == "Total records"), before)

    def test_dataset_removal_clears_the_upload(self):
        app = self._app()
        app, _ = self._upload(app)
        app.button(key="rm_remove_dataset").click().run()
        self.assertFalse(app.exception)
        self.assertFalse(any(header.value == "Overview" for header in app.header))
        self.assertIsNone(app.file_uploader(key="data_upload_999").value)
        self.assertTrue(any("Removed the uploaded dataset" in message.value for message in app.success))

    # ------------------------------------------------------------------
    # builder: visuals
    # ------------------------------------------------------------------
    def test_add_edit_duplicate_move_delete_and_undo_redo(self):
        app = self._app()
        app, identity = self._upload(app)
        app = self._customize(app)
        original_count = self._component_count(app, identity)

        # Add a KPI.
        app.selectbox(key=f"rm_add_measure_{identity}").set_value("sales")
        app.button(key=f"FormSubmitter:rm_add_visual_{identity}-Add visual").click()
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count + 1)
        self.assertTrue(any("Added" in message.value for message in app.success))

        # Edit the first visual.
        component = self._config(app, identity).pages[0].components[0]
        app.text_input(key=f"rm_edit_title_{identity}_{component.id}").set_value("Revenue KPI")
        app.selectbox(key=f"rm_edit_type_{identity}_{component.id}").set_value("bar")
        app.selectbox(key=f"rm_edit_dim_{identity}_{component.id}").set_value("product_name")
        app.selectbox(key=f"rm_edit_measure_{identity}_{component.id}").set_value("sales")
        app.slider(key=f"rm_edit_width_{identity}_{component.id}").set_value(8)
        app.slider(key=f"rm_edit_height_{identity}_{component.id}").set_value(400)
        app.color_picker(key=f"rm_edit_colour_{identity}_{component.id}").set_value("#ff8800")
        app.button(key=f"FormSubmitter:rm_edit_visual_{identity}-Save visual").click()
        app.run()
        self.assertFalse(app.exception)
        edited = self._config(app, identity).pages[0].components[0]
        self.assertEqual((edited.title, edited.type, edited.dimension, edited.measure), ("Revenue KPI", "bar", "product_name", "sales"))
        self.assertEqual((edited.width, edited.height, edited.color), (8, 400, "#ff8800"))

        # Duplicate and delete the clone.
        app.button(key=f"rm_duplicate_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count + 2)
        duplicate_label = next(
            option
            for option in app.selectbox(key=f"rm_selected_{identity}_Executive Overview").options
            if "(copy)" in option
        )
        app.selectbox(key=f"rm_selected_{identity}_Executive Overview").set_value(duplicate_label).run()
        app.checkbox(key=f"rm_confirm_delete_{identity}").set_value(True).run()
        app.button(key=f"rm_delete_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count + 1)

        # Undo / redo the delete.
        app.button(key=f"rm_undo_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count + 2)
        app.button(key=f"rm_redo_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count + 1)

        # Boundary feedback: moving the first visual up is reported, not silent.
        first_label = app.selectbox(key=f"rm_selected_{identity}_Executive Overview").options[0]
        app.selectbox(key=f"rm_selected_{identity}_Executive Overview").set_value(first_label).run()
        app.button(key=f"rm_move_up_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("already first" in message.value for message in app.warning))

    # ------------------------------------------------------------------
    # builder: pages
    # ------------------------------------------------------------------
    def test_page_add_rename_duplicate_and_delete(self):
        app = self._app()
        app, identity = self._upload(app)
        app = self._customize(app)

        app.text_input(key=f"rm_new_page_name_{identity}").set_value("Test Page")
        app.button(key=f"FormSubmitter:rm_add_page_{identity}-Add page").click().run()
        self.assertFalse(app.exception)
        self.assertIn("Test Page", self._config(app, identity).page_names())
        self.assertEqual(app.session_state[f"rm_page_{identity}"], "Test Page")

        app.selectbox(key=f"rm_manage_page_{identity}").set_value("Test Page").run()
        app.text_input(key=f"rm_rename_page_name_{identity}_Test Page").set_value("Renamed Page")
        app.button(key=f"FormSubmitter:rm_rename_page_{identity}-Rename page").click().run()
        self.assertFalse(app.exception)
        self.assertIn("Renamed Page", self._config(app, identity).page_names())
        self.assertNotIn("Test Page", self._config(app, identity).page_names())
        self.assertEqual(app.session_state[f"rm_page_{identity}"], "Renamed Page")

        app.selectbox(key=f"rm_manage_page_{identity}").set_value("Renamed Page").run()
        app.button(key=f"rm_page_duplicate_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertIn("Renamed Page copy", self._config(app, identity).page_names())

        app.selectbox(key=f"rm_manage_page_{identity}").set_value("Renamed Page copy").run()
        app.checkbox(key=f"rm_confirm_page_delete_{identity}").set_value(True).run()
        app.button(key=f"rm_page_delete_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertNotIn("Renamed Page copy", self._config(app, identity).page_names())

    def test_last_page_cannot_be_deleted(self):
        from retailmind.models import DashboardConfig

        config = DashboardConfig()
        config.pages = []
        self.assertFalse(config.remove_page("Overview"))
        config.add_page("Overview")
        self.assertFalse(config.remove_page("Overview"))

    # ------------------------------------------------------------------
    # builder: save, restore, reset
    # ------------------------------------------------------------------
    def test_save_autosave_restore_and_reset(self):
        app = self._app()
        app, identity = self._upload(app)
        app = self._customize(app)
        original_count = self._component_count(app, identity)

        app.button(key=f"rm_save_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Saved" in message.value for message in app.success))
        app.button(key=f"rm_autosave_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Autosave written" in message.value for message in app.success))

        app.selectbox(key=f"rm_add_measure_{identity}").set_value("sales")
        app.button(key=f"FormSubmitter:rm_add_visual_{identity}-Add visual").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count + 1)

        restore_key = f"rm_restore_select_{identity}"
        self.assertTrue(app.selectbox(key=restore_key).options)
        app.checkbox(key=f"rm_confirm_restore_{identity}").set_value(True).run()
        app.button(key=f"rm_restore_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count)

        app.checkbox(key=f"rm_confirm_reset_{identity}").set_value(True).run()
        app.button(key=f"rm_reset_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("original auto-generated dashboard" in message.value for message in app.success))

    # ------------------------------------------------------------------
    # AI workspace
    # ------------------------------------------------------------------
    def test_assistant_adds_kpi_filter_and_confirms_reset(self):
        app = self._app()
        app, identity = self._upload(app)
        original_count = self._component_count(app, identity)

        app.text_input(key=f"rm_assistant_command_{identity}").set_value("add a total profit kpi")
        app.button(key=f"rm_assistant_apply_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count + 1)

        app.text_input(key=f"rm_assistant_command_{identity}").set_value("add a region filter")
        app.button(key=f"rm_assistant_apply_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(filter_.column == "region" for filter_ in self._config(app, identity).filters))
        self.assertTrue(any(widget.label == "Region" for widget in app.multiselect))

        app.text_input(key=f"rm_assistant_command_{identity}").set_value("reset the dashboard")
        app.button(key=f"rm_assistant_apply_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Confirmation required" in message.value for message in app.warning))
        app.button(key=f"rm_confirm_action_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._component_count(app, identity), original_count)

    def test_assistant_rejects_unknown_command_without_changing_layout(self):
        app = self._app()
        app, identity = self._upload(app)
        before = self._config(app, identity).to_json()
        app.text_input(key=f"rm_assistant_command_{identity}").set_value("xyzzy plugh")
        app.button(key=f"rm_assistant_apply_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self._config(app, identity).to_json(), before)
        self.assertTrue(app.warning)

    def test_chatbot_answers_clears_and_warns_on_empty_question(self):
        app = self._app()
        app, identity = self._upload(app)
        app.text_input(key=f"rm_chat_question_{identity}").set_value("What is total revenue?")
        app.button(key=f"FormSubmitter:rm_chat_form_{identity}-Ask").click().run()
        self.assertFalse(app.exception)
        messages = app.session_state[f"rm_chat_{identity}"]
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[-1]["role"], "assistant")
        self.assertTrue(messages[-1]["verified"])

        app.button(key=f"rm_chat_clear_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state[f"rm_chat_{identity}"], [])
        self.assertTrue(any("Cleared the chat conversation" in message.value for message in app.success))

        app.button(key=f"FormSubmitter:rm_chat_form_{identity}-Ask").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Enter a business question" in message.value for message in app.warning))

    def test_knowledge_documents_index_ask_and_clear(self):
        app = self._app()
        app, identity = self._upload(app)
        document = b"Refund policy: customers may return items within 30 days. Support: help@example.com."
        app.file_uploader(key="rm_docs_uploader").set_value([("policy.txt", document, "text/plain")]).run()
        app.button(key=f"rm_index_docs_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertIn("policy.txt", app.session_state["rm_rag_store"].documents)

        app.text_input(key=f"rm_rag_question_{identity}").set_value("How long do customers have to return items?")
        app.button(key=f"FormSubmitter:rm_rag_form_{identity}-Ask documents").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("policy.txt" in caption.value for caption in app.caption))

        app.checkbox(key=f"rm_confirm_clear_docs_{identity}").set_value(True).run()
        app.button(key=f"rm_clear_docs_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["rm_rag_store"].documents, {})
        self.assertTrue(any("Cleared the knowledge base" in message.value for message in app.success))

    def test_ai_connection_test_explains_local_fallback(self):
        app = self._app()
        app, identity = self._upload(app)
        app.button(key=f"rm_test_ai_{identity}").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(
            any("No AI provider is configured" in message.value for message in app.warning)
            or any("AI provider responded" in message.value for message in app.success)
        )

    # ------------------------------------------------------------------
    # downloads: actual generated files
    # ------------------------------------------------------------------
    def test_download_payloads_are_valid_files(self):
        frame = pd.DataFrame(
            {
                "order_id": ["A", "B"],
                "order_date": pd.to_datetime(["2025-01-01", "2025-01-02"]),
                "city": ["Delhi", "Pune"],
                "category": ["Office", "Tech"],
                "product_name": ["Pen", "Phone"],
                "sales": [100.0, 200.0],
                "profit": [20.0, 50.0],
            }
        )
        schema = infer_schema(frame)
        report = analyse_cleaning(frame, schema)
        insights = generate_insights(frame, schema)
        categories = app_module._dimension_summary(frame, schema, "category", "revenue")
        products = app_module._dimension_summary(frame, schema, "product", "revenue")
        markdown = app_module._executive_markdown(frame, schema, "fixture.csv", {}, insights, categories, products)
        workbook = app_module._executive_workbook(
            frame, schema, report, "fixture.csv", {}, insights, categories, products,
            app_module.profile_report(frame, schema),
        )

        target = Path(self.state_dir)
        (target / "cleaned.csv").write_bytes(dataframe_to_csv_bytes(frame))
        (target / "cleaned.xlsx").write_bytes(excel_bytes(frame))
        (target / "summary.md").write_text(markdown, encoding="utf-8")
        (target / "workbook.xlsx").write_bytes(workbook)

        self.assertEqual(len(pd.read_csv(target / "cleaned.csv")), 2)
        self.assertEqual(pd.ExcelFile(target / "cleaned.xlsx").sheet_names, ["Data"])
        summary = (target / "summary.md").read_text(encoding="utf-8")
        self.assertIn("fixture.csv", summary)
        self.assertIn("Total Revenue / Sales", summary)
        workbook_sheets = pd.ExcelFile(target / "workbook.xlsx").sheet_names
        self.assertIn("Summary", workbook_sheets)
        self.assertIn("Sales Data", workbook_sheets)
        summary_row = pd.read_excel(target / "workbook.xlsx", sheet_name="Summary").to_dict("records")[0]
        self.assertEqual(summary_row["Total Sales"], 300)
        self.assertEqual(summary_row["Total Profit"], 70)


if __name__ == "__main__":
    unittest.main()
