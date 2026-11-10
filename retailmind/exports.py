"""Additional exports: PDF reports, multi-sheet workbooks and theme JSON.

All exports are generated from the active filtered data.  PDF generation uses
reportlab when installed and falls back to a plain-text PDF-free response only
when it is missing (the caller is told which format was produced).
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from typing import Any, Iterable
from xml.sax.saxutils import escape

import pandas as pd

from retailmind.schema import DatasetSchema
from retailmind.utils import format_number, money, safe_percent


@dataclass
class ExportBundle:
    data: bytes
    filename: str
    mime: str


def _safe_sheet(name: str) -> str:
    cleaned = "".join(character for character in str(name) if character not in "[]:*?/\\")[:31]
    return cleaned or "Sheet"


def workbook_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            if frame is None:
                continue
            frame.to_excel(writer, sheet_name=_safe_sheet(name), index=False)
    return output.getvalue()


def markdown_report(
    frame: pd.DataFrame,
    *,
    title: str,
    filters: dict[str, Any] | None = None,
) -> ExportBundle:
    """Build a portable Markdown table from the active filtered dataset."""
    def cell(value: Any) -> str:
        if value is None or (not isinstance(value, (list, dict, tuple)) and pd.isna(value)):
            return ""
        text = str(value).replace("\\", "\\\\").replace("|", "\\|")
        return text.replace("\r\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")

    lines = [f"# {title} data report", "", f"Rows: {len(frame):,}", "", "## Active date filters"]
    active_filters = [(key, value) for key, value in (filters or {}).items() if value not in (None, "", [])]
    if active_filters:
        lines.extend(f"- **{cell(key)}:** {cell(value)}" for key, value in active_filters)
    else:
        lines.append("- None")
    lines.extend(["", "## Dataset"])
    if frame.empty:
        lines.extend(["", "No rows match the selected date range."])
    elif len(frame.columns) == 0:
        lines.extend(["", "The dataset has no columns to display."])
    else:
        headers = [cell(column) for column in frame.columns]
        lines.extend([
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ])
        lines.extend(
            "| " + " | ".join(cell(value) for value in row) + " |"
            for row in frame.itertuples(index=False, name=None)
        )
    return ExportBundle(
        data=("\n".join(lines) + "\n").encode("utf-8"),
        filename=f"{title.lower().replace(' ', '_')}_report.md",
        mime="text/markdown; charset=utf-8",
    )


def theme_json_bytes(theme_name: str = "RetailMind AI") -> bytes:
    theme = {
        "name": theme_name,
        "dataColors": ["#7C5CFF", "#22D3EE", "#34D399", "#FBBF24", "#F43F5E", "#A78BFA", "#38BDF8", "#FB7185"],
        "background": "#0B1020",
        "foreground": "#E7ECFF",
        "tableAccent": "#7C5CFF",
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{"color": {"solid": {"color": "#141B31"}}, "show": True}],
                    "border": [{"show": True, "color": {"solid": {"color": "#2A3550"}}, "radius": 8}],
                }
            }
        },
    }
    return json.dumps(theme, indent=2).encode("utf-8")


def _paragraph(text: str):
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import getSampleStyleSheet

    styles = getSampleStyleSheet()
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles["BodyText"])


def pdf_report(
    title: str,
    subtitle: str,
    sections: Iterable[tuple[str, list[str]]],
    *,
    tables: dict[str, pd.DataFrame] | None = None,
) -> ExportBundle:
    """Build a real PDF with reportlab; never fabricate a PDF byte stream."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        text = [title, subtitle, ""]
        for heading, lines in sections:
            text.append(heading)
            text.extend(f"- {line}" for line in lines)
            text.append("")
        return ExportBundle(
            data=("\n".join(text)).encode("utf-8"),
            filename=f"{title.lower().replace(' ', '_')}.txt",
            mime="text/plain",
        )

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, title=title, author="RetailMind AI")
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph(escape(title), styles["Title"]),
        Paragraph(escape(subtitle), styles["Italic"]),
        Spacer(1, 12),
    ]
    for heading, lines in sections:
        story.append(Paragraph(escape(heading), styles["Heading2"]))
        for line in lines:
            story.append(_paragraph(f"• {line}"))
        story.append(Spacer(1, 8))
    for name, frame in (tables or {}).items():
        if frame is None or frame.empty:
            continue
        story.append(PageBreak())
        story.append(Paragraph(escape(name), styles["Heading2"]))
        preview = frame.head(40)
        data = [list(map(str, preview.columns))] + [
            [str(value) for value in row] for row in preview.itertuples(index=False, name=None)
        ]
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7C5CFF")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
        if len(frame) > len(preview):
            story.append(Paragraph(f"Showing the first {len(preview):,} of {len(frame):,} rows.", styles["Italic"]))
    document.build(story)
    return ExportBundle(data=output.getvalue(), filename=f"{title.lower().replace(' ', '_')}.pdf", mime="application/pdf")


def executive_pdf(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    filename: str,
    filters: dict[str, Any],
    insights,
    segmentation=None,
    forecast=None,
    inventory=None,
    alerts: Iterable[Any] = (),
) -> ExportBundle:
    revenue = schema.role_column("revenue")
    profit = schema.role_column("profit")
    order = schema.role_column("order_id")
    total_revenue = float(pd.to_numeric(frame[revenue], errors="coerce").sum()) if revenue else 0.0
    total_profit = float(pd.to_numeric(frame[profit], errors="coerce").sum()) if profit else 0.0
    orders = int(frame[order].nunique(dropna=True)) if order else len(frame)
    sections: list[tuple[str, list[str]]] = []
    sections.append(
        (
            "Verified KPIs",
            [
                f"Rows in the active filtered data: {len(frame):,}",
                f"Total revenue: {money(total_revenue)}" if revenue else "Total revenue: not mapped",
                f"Total profit: {money(total_profit)}" if profit else "Total profit: not mapped",
                f"Profit margin: {safe_percent(total_profit / total_revenue) if revenue and total_revenue else 'N/A'}",
                f"Orders (distinct): {orders:,}",
            ],
        )
    )
    sections.append(("Active filters", [f"{key}: {value}" for key, value in filters.items() if value not in (None, "", [])] or ["None"]))
    if insights is not None:
        if hasattr(insights, "facts"):
            sections.append(("Verified facts", list(insights.facts)))
            sections.append(("Statistical anomalies", list(insights.anomalies)))
            sections.append(("Forecasts", list(insights.forecasts)))
            sections.append(("Recommendations (rule-based)", list(insights.recommendations)))
        elif isinstance(insights, (list, tuple)):
            facts = [str(item.text if hasattr(item, "text") else item) for item in insights]
            sections.append(("Verified insights", facts))
    alert_list = list(alerts)
    if alert_list:
        sections.append(
            (
                "Smart alerts",
                [f"[{alert.severity.upper()}] {alert.title}: {alert.description}" for alert in alert_list[:25]],
            )
        )
    if segmentation is not None and segmentation.available:
        sections.append(
            (
                "Customer segments",
                [
                    f"{row['segment']}: {int(row['customers']):,} customers, {row['revenue_share']:.1%} of revenue"
                    for _index, row in segmentation.summary.iterrows()
                ],
            )
        )
    if forecast is not None and forecast.available:
        sections.append(
            (
                "Forecast",
                [
                    f"Method: {forecast.method}; frequency: {forecast.frequency}",
                    f"Next forecast: {format_number(float(forecast.forecast['forecast'].iloc[0]))}",
                    f"MAE: {format_number(forecast.metrics.get('mae'))}; RMSE: {format_number(forecast.metrics.get('rmse'))}; "
                    f"MAPE: {forecast.metrics.get('mape'):.2f}%" if forecast.metrics.get("mape") is not None else "MAPE: N/A",
                ],
            )
        )
    if inventory is not None and inventory.available:
        critical = inventory.table[inventory.table["status"].isin(["Out of stock", "Critical — reorder now", "Low — reorder soon"])]
        sections.append(
            (
                "Inventory",
                [
                    f"Products analysed: {len(inventory.table):,}",
                    f"Products at or below reorder point: {len(critical):,}",
                    *[
                        f"{row['product']}: {row['status']} (reorder point {row['reorder_point']:,.2f})"
                        for _index, row in critical.head(15).iterrows()
                    ],
                ],
            )
        )
    sections.append(
        (
            "Limitations",
            [
                "Figures are deterministic aggregates of the active filtered dataset.",
                "Anomalies state a statistical method; they are not causal explanations.",
                "Forecast intervals are approximate and depend on historical patterns.",
                "Inventory quantities are blank when no current-stock column is supplied.",
            ],
        )
    )
    tables = {"Filtered data preview": frame.head(40)}
    if segmentation is not None and segmentation.available:
        tables["Customer segment summary"] = segmentation.summary
    if forecast is not None and forecast.available:
        tables["Forecast"] = forecast.forecast
    if inventory is not None and inventory.available:
        tables["Inventory recommendations"] = inventory.table.head(40)
    return pdf_report(f"Executive summary — {filename}", "RetailMind AI", sections, tables=tables)


def business_analysis_pdf(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    filename: str,
    insights,
    alerts: Iterable[Any] = (),
) -> ExportBundle:
    facts = list(insights.facts) if hasattr(insights, "facts") else ([str(item.text if hasattr(item, "text") else item) for item in insights] if isinstance(insights, (list, tuple)) else [])
    anomalies = list(insights.anomalies) if hasattr(insights, "anomalies") else []
    forecasts = list(insights.forecasts) if hasattr(insights, "forecasts") else []
    recommendations = list(insights.recommendations) if hasattr(insights, "recommendations") else []
    sections: list[tuple[str, list[str]]] = [
        ("Dataset", [f"File: {filename}", f"Rows: {len(frame):,}", f"Columns: {len(frame.columns)}", f"Domain: {schema.domain_label}"]),
        ("Verified facts", facts),
        ("Statistical anomalies", anomalies),
        ("Forecasts", forecasts),
        ("Recommendations", recommendations),
        (
            "Alert evidence",
            [f"[{alert.severity.upper()}] {alert.title} — {alert.comparison_period}" for alert in list(alerts)[:30]],
        ),
    ]
    return pdf_report(f"Business analysis — {filename}", "RetailMind AI", sections)
