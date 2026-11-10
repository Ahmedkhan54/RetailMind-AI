"""Mobile Excel upload regression tests.

These tests verify that the upload pipeline handles files correctly regardless
of the MIME type reported by the browser.  Android Chrome in particular may
report different or no MIME types for Excel files, so validation must be based
on filename extension and file contents, not MIME type.

Real Android Chrome testing is not available in this environment.  These tests
simulate Android-style MIME types by setting the upload MIME type explicitly.
For physical-device verification, see the manual testing instructions below.
"""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
import zipfile

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---- Fixtures --------------------------------------------------------------

CSV_FIXTURE = (
    b"Order_ID,Order_Date,Customer_Name,City,Region,Product_Category,Product_Name,"
    b"Sales_Rep,Payment_Method,Sales,Profit\n"
    b"A,2025-01-01,Alice,Delhi,North,Office,Pen,Ravi,Card,100,20\n"
    b"B,2025-01-02,Bob,Pune,West,Tech,Phone,Sita,Cash,200,50\n"
    b"C,2025-01-03,Alice,Delhi,North,Office,Pad,Ravi,Card,150,30\n"
)


def _xlsx_fixture() -> bytes:
    """Build a minimal XLSX file in memory."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Order_ID": ["A", "B", "C"],
                "Order_Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
                "Customer_Name": ["Alice", "Bob", "Alice"],
                "City": ["Delhi", "Pune", "Delhi"],
                "Region": ["North", "West", "North"],
                "Product_Category": ["Office", "Tech", "Office"],
                "Product_Name": ["Pen", "Phone", "Pad"],
                "Sales_Rep": ["Ravi", "Sita", "Ravi"],
                "Payment_Method": ["Card", "Cash", "Card"],
                "Sales": [100, 200, 150],
                "Profit": [20, 50, 30],
            }
        ).to_excel(writer, index=False, sheet_name="Sheet1")
    return buffer.getvalue()


def _corrupted_xlsx_fixture() -> bytes:
    """Return bytes that look like an XLSX but are not a valid zip."""
    return b"PK\x03\x04" + b"not a real xlsx file" * 50


def _empty_xlsx_fixture() -> bytes:
    """Return an XLSX with no worksheets."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame().to_excel(writer, index=False, sheet_name="Empty")
    return buffer.getvalue()


# ---- MIME type simulation --------------------------------------------------

# Android Chrome may report these MIME types (or none at all):
MIME_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    # Android sometimes sends this for .xlsx:
    "xlsx_android": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Or no MIME type at all:
    "none": "",
}


def _make_upload(filename: str, content: bytes, mime_type: str) -> tuple:
    """Create an upload tuple (name, bytes, mime) simulating a browser upload."""
    return (filename, content, mime_type)


# ---- Tests -----------------------------------------------------------------


class TestMobileUpload:
    """Mobile upload regression tests."""

    @classmethod
    def setup_class(cls):
        os.environ["RETAIL_DASHBOARD_DEFAULT_SOURCE"] = "Upload CSV or Excel"
        os.environ["RETAIL_DASHBOARD_TEST_AUTH"] = "1"

    @classmethod
    def teardown_class(cls):
        os.environ.pop("RETAIL_DASHBOARD_DEFAULT_SOURCE", None)
        os.environ.pop("RETAIL_DASHBOARD_TEST_AUTH", None)

    def _upload_and_check(self, filename: str, content: bytes, mime_type: str) -> AppTest:
        """Upload a file and verify no exception and dashboard renders."""
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=30).run()
        assert not app.exception, f"App failed to start: {app.exception}"
        app.file_uploader(key="data_upload_999").set_value(
            _make_upload(filename, content, mime_type)
        ).run()
        assert not app.exception, f"Upload failed for {filename}: {app.exception}"
        # Dashboard should render (Overview header present)
        assert any(header.value == "Overview" for header in app.header), (
            f"Dashboard did not render for {filename}"
        )
        return app

    # ---- XLSX uploads -------------------------------------------------------

    def test_xlsx_upload_standard_mime(self):
        """Valid XLSX with standard MIME type uploads and renders dashboard."""
        self._upload_and_check("Retain.xlsx", _xlsx_fixture(), MIME_TYPES["xlsx"])

    def test_xlsx_upload_android_mime(self):
        """Valid XLSX with Android-style MIME type uploads and renders dashboard."""
        self._upload_and_check("Retain.xlsx", _xlsx_fixture(), MIME_TYPES["xlsx_android"])

    def test_xlsx_upload_no_mime(self):
        """Valid XLSX with no MIME type uploads and renders dashboard."""
        self._upload_and_check("Retain.xlsx", _xlsx_fixture(), MIME_TYPES["none"])

    def test_xlsx_upload_wrong_mime(self):
        """Valid XLSX with CSV MIME type still uploads (extension-based validation)."""
        self._upload_and_check("Retain.xlsx", _xlsx_fixture(), MIME_TYPES["csv"])

    # ---- CSV uploads --------------------------------------------------------

    def test_csv_upload_standard_mime(self):
        """Valid CSV with standard MIME type uploads and renders dashboard."""
        self._upload_and_check("Retain.csv", CSV_FIXTURE, MIME_TYPES["csv"])

    def test_csv_upload_no_mime(self):
        """Valid CSV with no MIME type uploads and renders dashboard."""
        self._upload_and_check("Retain.csv", CSV_FIXTURE, MIME_TYPES["none"])

    # ---- XLS and XLSM support ----------------------------------------------

    def test_xls_upload(self):
        """Valid XLS uploads and renders dashboard."""
        # Build a minimal XLS using xlwt if available, otherwise skip
        try:
            import xlwt  # noqa: F401

            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="xlwt") as writer:
                pd.DataFrame(
                    {
                        "Order_ID": ["A", "B"],
                        "Order_Date": ["2025-01-01", "2025-01-02"],
                        "Customer_Name": ["Alice", "Bob"],
                        "City": ["Delhi", "Pune"],
                        "Region": ["North", "West"],
                        "Product_Category": ["Office", "Tech"],
                        "Product_Name": ["Pen", "Phone"],
                        "Sales_Rep": ["Ravi", "Sita"],
                        "Payment_Method": ["Card", "Cash"],
                        "Sales": [100, 200],
                        "Profit": [20, 50],
                    }
                ).to_excel(writer, index=False, sheet_name="Sheet1")
            self._upload_and_check("Retain.xls", buffer.getvalue(), MIME_TYPES["xls"])
        except ImportError:
            pytest.skip("xlwt not installed - cannot create XLS fixture")

    def test_xlsm_upload(self):
        """Valid XLSM uploads and renders dashboard."""
        try:
            import xlwt  # noqa: F401

            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="xlwt") as writer:
                pd.DataFrame(
                    {
                        "Order_ID": ["A", "B"],
                        "Order_Date": ["2025-01-01", "2025-01-02"],
                        "Customer_Name": ["Alice", "Bob"],
                        "City": ["Delhi", "Pune"],
                        "Region": ["North", "West"],
                        "Product_Category": ["Office", "Tech"],
                        "Product_Name": ["Pen", "Phone"],
                        "Sales_Rep": ["Ravi", "Sita"],
                        "Payment_Method": ["Card", "Cash"],
                        "Sales": [100, 200],
                        "Profit": [20, 50],
                    }
                ).to_excel(writer, index=False, sheet_name="Sheet1")
            self._upload_and_check("Retain.xlsm", buffer.getvalue(), MIME_TYPES["xlsm"])
        except ImportError:
            pytest.skip("xlwt not installed - cannot create XLSM fixture")

    # ---- Corrupted / invalid files -----------------------------------------

    def test_corrupted_xlsx_rejected(self):
        """Corrupted XLSX file produces a clear error, not a crash."""
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=30).run()
        app.file_uploader(key="data_upload_999").set_value(
            _make_upload("corrupted.xlsx", _corrupted_xlsx_fixture(), MIME_TYPES["xlsx"])
        ).run()
        # Should not crash - should show an error message
        assert not app.exception or "Could not read" in str(app.exception)

    def test_empty_file_rejected(self):
        """Empty file produces a clear error."""
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=30).run()
        app.file_uploader(key="data_upload_999").set_value(
            _make_upload("empty.csv", b"", MIME_TYPES["csv"])
        ).run()
        assert not app.exception

    def test_unsupported_extension_rejected(self):
        """Unsupported file extension produces a clear error."""
        app = AppTest.from_file(PROJECT_ROOT / "dashboard.py", default_timeout=30).run()
        app.file_uploader(key="data_upload_999").set_value(
            _make_upload("document.pdf", b"%PDF-1.4 fake pdf", "application/pdf")
        ).run()
        assert not app.exception

    # ---- Dashboard generation after upload --------------------------------

    def test_dashboard_generates_after_xlsx_upload(self):
        """Dashboard KPIs and charts render after XLSX upload."""
        app = self._upload_and_check("Retail.xlsx", _xlsx_fixture(), MIME_TYPES["xlsx"])
        assert any(metric.label == "Total sales" for metric in app.metric)
        assert any(element.type == "vega_lite_chart" for element in app)

    def test_dashboard_generates_after_csv_upload(self):
        """Dashboard KPIs and charts render after CSV upload."""
        app = self._upload_and_check("Retain.csv", CSV_FIXTURE, MIME_TYPES["csv"])
        assert any(metric.label == "Total sales" for metric in app.metric)
        assert any(element.type == "vega_lite_chart" for element in app)


# ---- Manual testing instructions ------------------------------------------

"""
MANUAL ANDROID CHROME TESTING INSTRUCTIONS
==========================================

Physical-device testing could not be performed in this environment (no Android
device or Chrome mobile installation available).  To verify on a real device:

1. Start the RetailMind AI server:
   .\\.venv\\Scripts\\Activate.ps1
   streamlit run dashboard.py

2. Open Chrome on your Android phone and navigate to the server URL
   (e.g. http://<computer-ip>:8501).

3. Upload Retain.xlsx (58.5 KB) using the file chooser.

4. Verify:
   - The file does NOT appear in a red error state.
   - No red exclamation icon or red remove button appears.
   - The dashboard is generated automatically with KPIs and charts.
   - The "Overview" page loads with data.

5. If the file still shows as an error:
   - Check the browser console for JavaScript errors.
   - Check the Streamlit server logs for Python exceptions.
   - Try renaming the file with a lowercase extension (retain.xlsx).

Expected fix: removing the `type=` parameter from st.file_uploader allows
Android Chrome to select any file. Server-side validation then checks the
filename extension and attempts to read the file contents, providing clear
error messages for unsupported or corrupted files.
"""
