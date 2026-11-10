"""In-memory reports only; generated files are not saved or re-downloadable."""
from __future__ import annotations
from io import BytesIO
import pandas as pd


def excel_report(filtered: pd.DataFrame, category: pd.DataFrame, products: pd.DataFrame, monthly: pd.DataFrame, rfm: pd.DataFrame, quality: dict, recommendations: list[str]) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame([{"Total Sales": filtered.sales.sum(), "Total Profit": filtered.profit.sum(), "Total Orders": filtered.order_id.nunique()}]).to_excel(writer, sheet_name="Summary", index=False)
        filtered.to_excel(writer, sheet_name="Sales Data", index=False)
        category.to_excel(writer, sheet_name="Category Analysis", index=False)
        products.head(10).to_excel(writer, sheet_name="Product Analysis", index=False)
        monthly.to_excel(writer, sheet_name="Monthly Trends", index=False)
        rfm.to_excel(writer, sheet_name="Customer Insights", index=False)
        pd.DataFrame([quality]).to_excel(writer, sheet_name="Data Quality Report", index=False)
        pd.DataFrame({"Business Recommendations": recommendations}).to_excel(writer, sheet_name="Business Recommendations", index=False)
    return output.getvalue()


def pdf_report(filtered: pd.DataFrame | None = None, filters: dict | None = None, insights: list[str] | None = None) -> bytes:
    """Generate on demand only when ReportLab is installed; never persists a file."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen.canvas import Canvas
    except ImportError as error:
        raise RuntimeError("PDF reports require the optional reportlab dependency.") from error
    output = BytesIO(); canvas = Canvas(output, pagesize=letter)
    canvas.drawString(72, 720, "RetailMind AI Business Report")
    canvas.drawString(72, 700, "Generated from the authenticated user's active uploaded dataset.")
    if filtered is not None:
        canvas.drawString(72, 680, f"KPIs — sales: {filtered.sales.sum():,.2f}; profit: {filtered.profit.sum():,.2f}; orders: {filtered.order_id.nunique():,}")
    if filters:
        canvas.drawString(72, 660, "Active filters: " + str(filters)[:100])
    if insights:
        canvas.drawString(72, 640, "Business recommendation: " + str(insights[0])[:90])
    canvas.save(); return output.getvalue()


def generate_executive_summary_markdown(
    filtered: pd.DataFrame,
    kpis: dict,
    dataset_name: str = "Active Dataset",
    filters: dict | None = None,
    insights: list[str] | None = None,
    category_summary: pd.DataFrame | None = None,
    top_products: pd.DataFrame | None = None,
) -> str:
    """Generate a comprehensive executive markdown report from actual dataset results."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Executive Performance Summary: {dataset_name}",
        f"**Generated:** {now} | **Dataset Records:** {len(filtered):,}",
        "",
        "## Key Performance Indicators",
        f"- **Total Revenue / Sales:** ₹{kpis.get('total_sales', 0.0):,.2f}",
        f"- **Total Gross Profit:** ₹{kpis.get('total_profit', 0.0):,.2f}",
        f"- **Profit Margin:** {kpis.get('profit_margin', 0.0):.1%}" if kpis.get("profit_margin") is not None else "- **Profit Margin:** Not available",
        f"- **Distinct Transactions / Orders:** {kpis.get('order_count', len(filtered)):,}",
        f"- **Average Order Value (AOV):** ₹{kpis.get('average_order_value', 0.0):,.2f}" if kpis.get("average_order_value") is not None else "- **Average Order Value:** Not available",
    ]
    if kpis.get("quantity_sold") is not None:
        lines.append(f"- **Total Quantity Sold:** {kpis['quantity_sold']:,}")

    if filters:
        lines.extend(["", "## Applied Filter Parameters"])
        for k, v in filters.items():
            if v:
                lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")

    if category_summary is not None and not category_summary.empty and "category" in category_summary.columns:
        lines.extend(["", "## Category Performance Breakdown", "| Category | Sales (₹) | Profit (₹) | Margin |", "| :--- | :--- | :--- | :--- |"])
        for _, row in category_summary.head(5).iterrows():
            margin_str = f"{row['margin']:.1%}" if "margin" in row and pd.notna(row["margin"]) else "N/A"
            profit_str = f"₹{row['profit']:,.2f}" if "profit" in row and pd.notna(row["profit"]) else "N/A"
            lines.append(f"| {row['category']} | ₹{row['sales']:,.2f} | {profit_str} | {margin_str} |")

    if top_products is not None and not top_products.empty and "product_name" in top_products.columns:
        lines.extend(["", "## Top Performing Products by Revenue", "| Rank | Product Name | Sales (₹) |", "| :---: | :--- | :--- |"])
        for rank, (_, row) in enumerate(top_products.head(5).iterrows(), 1):
            lines.append(f"| {rank} | {row['product_name']} | ₹{row['sales']:,.2f} |")

    if insights:
        lines.extend(["", "## Strategic Insights & Observations"])
        for insight in insights:
            lines.append(f"- {insight}")

    lines.extend([
        "",
        "---",
        "*Note: All metrics and insights are deterministically calculated from active uploaded data. No synthetic or fabricated metrics are included.*"
    ])
    return "\n".join(lines)

