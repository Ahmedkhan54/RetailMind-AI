"""Unit tests for RetailMind AI additional exports (PDF, multi-sheet Excel, Power BI theme)."""
from __future__ import annotations

from io import BytesIO
import json
import pandas as pd
import pytest

from retailmind.alerts import Alert
from retailmind.exports import (
    business_analysis_pdf,
    executive_pdf,
    markdown_report,
    pdf_report,
    theme_json_bytes,
    workbook_bytes,
)
from retailmind.forecasting import ForecastResult
from retailmind.inventory import InventoryResult
from retailmind.schema import infer_schema
from retailmind.segmentation import SegmentationResult


def test_theme_json_bytes():
    raw = theme_json_bytes("RetailMind Dark")
    assert isinstance(raw, bytes)
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["name"] == "RetailMind Dark"
    assert "dataColors" in parsed
    assert "visualStyles" in parsed
    assert len(parsed["dataColors"]) >= 4


def test_workbook_bytes_multi_sheet():
    sheets = {
        "Summary": pd.DataFrame({"Metric": ["Revenue", "Profit"], "Value": [1000, 200]}),
        "Details": pd.DataFrame({"ID": [1, 2, 3], "Amount": [10, 20, 30]}),
    }
    raw = workbook_bytes(sheets)
    assert isinstance(raw, bytes)
    assert len(raw) > 0
    
    # Read back with pandas
    read_sheets = pd.read_excel(BytesIO(raw), sheet_name=None)
    assert "Summary" in read_sheets
    assert "Details" in read_sheets
    assert len(read_sheets["Summary"]) == 2
    assert len(read_sheets["Details"]) == 3


def test_pdf_report_generation():
    sections = [
        ("Executive Overview", ["Revenue was $10,000", "Profit margin reached 22%"]),
        ("Key Drivers", ["Top product was Widget A", "Region North led growth"]),
    ]
    tables = {
        "Top Products": pd.DataFrame({"Product": ["Widget A", "Widget B"], "Sales": [5000, 3000]})
    }
    bundle = pdf_report("Monthly Report", "February 2025", sections, tables=tables)
    assert bundle.filename.endswith(".pdf") or bundle.filename.endswith(".txt")
    assert len(bundle.data) > 0
    if bundle.mime == "application/pdf":
        assert bundle.data.startswith(b"%PDF")
    else:
        assert b"Monthly Report" in bundle.data


def test_executive_pdf():
    df = pd.DataFrame({
        "order_id": ["O1", "O2", "O3"],
        "order_date": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "sales": [100.0, 200.0, 300.0],
        "profit": [20.0, 40.0, 60.0],
    })
    schema = infer_schema(df)
    alert = Alert(title="Sales increased", description="Rose 20%", metric="sales", severity="info")
    
    bundle = executive_pdf(
        df,
        schema,
        filename="sales_data.csv",
        filters={"Region": "All"},
        insights=None,
        alerts=[alert],
    )
    assert len(bundle.data) > 0
    assert bundle.filename.startswith("executive_summary")


def test_markdown_report_escapes_table_separators_and_includes_active_filters():
    frame = pd.DataFrame({"Product|name": ["A|B", "C\nD"], "Sales": [12, 34]})
    bundle = markdown_report(
        frame,
        title="Retail sales",
        filters={"date_from": "2025-01-02", "date_to": "2025-01-03"},
    )

    content = bundle.data.decode("utf-8")
    assert bundle.filename == "retail_sales_report.md"
    assert bundle.mime == "text/markdown; charset=utf-8"
    assert "Rows: 2" in content
    assert "**date_from:** 2025-01-02" in content
    assert "Product\\|name" in content
    assert "A\\|B" in content
    assert "C<br>D" in content


def test_business_analysis_pdf():
    df = pd.DataFrame({
        "order_date": ["2025-01-01", "2025-01-02"],
        "sales": [100.0, 200.0],
    })
    schema = infer_schema(df)
    alert = Alert(title="Revenue anomaly", description="Unusual spike", metric="sales", severity="warning")
    
    bundle = business_analysis_pdf(
        df,
        schema,
        filename="q1_sales.csv",
        insights=None,
        alerts=[alert],
    )
    assert len(bundle.data) > 0
    assert bundle.filename.startswith("business_analysis")
