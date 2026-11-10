"""Automatic dashboard generation.

The engine turns a :class:`DatasetSchema` into a usable dashboard without
asking the user to design anything.  It only emits components whose required
columns actually exist, so no empty or fabricated visuals are created.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from retailmind.models import Component, DashboardConfig, Page, Theme
from retailmind.schema import DatasetSchema
from retailmind.config import PALETTES


@dataclass(frozen=True)
class DashboardPlan:
    pages: int
    kpis: int
    charts: int
    domain: str


def _add_kpi(
    page: Page,
    title: str,
    role: str,
    fmt: str,
    description: str = "",
    order: int | None = None,
    measure: str | None = None,
    aggregation: str = "sum",
) -> Component:
    component = Component(
        type="kpi",
        title=title,
        page=page.name,
        kpi_role=role,
        measure=measure,
        aggregation=aggregation,
        format=fmt,
        width=3,
        height=180,
        description=description,
    )
    if order is None:
        page.add(component)
    else:
        page.components.insert(order, component)
        page._reindex()
    return component


def _add_chart(
    page: Page,
    title: str,
    chart_type: str,
    dimension: str | None,
    measure: str | None,
    aggregation: str = "sum",
    top_n: int = 10,
    measure_y: str | None = None,
    width: int = 6,
    height: int = 320,
    description: str = "",
) -> Component:
    component = Component(
        type=chart_type,
        title=title,
        page=page.name,
        dimension=dimension,
        measure=measure,
        measure_y=measure_y,
        aggregation=aggregation,
        top_n=top_n,
        width=width,
        height=height,
        description=description,
    )
    page.add(component)
    return component


def _add_special(page: Page, title: str, component_type: str, width: int = 12, height: int = 360, description: str = "") -> Component:
    component = Component(type=component_type, title=title, page=page.name, width=width, height=height, description=description)
    page.add(component)
    return component


def primary_measure(schema: DatasetSchema) -> str | None:
    for role in ("revenue", "profit", "cost", "salary", "grade", "age"):
        column = schema.role_column(role)
        if column:
            return column
    return schema.measures[0] if schema.measures else None


def secondary_measure(schema: DatasetSchema) -> str | None:
    for role in ("profit", "cost", "quantity", "salary"):
        column = schema.role_column(role)
        if column and column != primary_measure(schema):
            return column
    for column in schema.measures:
        if column != primary_measure(schema):
            return column
    return None


def preferred_dimensions(schema: DatasetSchema) -> list[str]:
    ordered: list[str] = []
    for role in ("product", "category", "region", "city", "store", "customer", "department", "sales_rep", "course", "gender", "attendance"):
        column = schema.role_column(role)
        if column:
            ordered.append(column)
    for column in schema.categorical:
        if column not in ordered:
            ordered.append(column)
    return ordered


def _measure_label(schema: DatasetSchema, column: str | None) -> str:
    if column is None:
        return "Records"
    return schema.label_for(column)


def _kpi_title(role: str, schema: DatasetSchema) -> str:
    if role == "records":
        return "Total records"
    if role == "revenue":
        return "Total sales" if schema.domain in ("retail", "commerce") else "Total revenue"
    if role == "profit":
        return "Total profit"
    if role == "margin":
        return "Profit margin"
    if role == "quantity":
        return "Total quantity"
    if role == "orders":
        return "Total orders"
    if role == "customers":
        return "Total customers"
    if role == "aov":
        return "Average order value"
    if role == "employees":
        return "Employee count"
    if role == "salary":
        return "Total salary"
    if role == "avg_salary":
        return "Average salary"
    if role == "cost":
        return "Total expenses"
    if role == "growth":
        return "Sales growth" if schema.domain in ("retail", "commerce") else "Revenue growth"
    if role == "attendance_rate":
        return "Attendance rate"
    return role.replace("_", " ").title()


def _build_overview(config: DashboardConfig, schema: DatasetSchema, primary: str | None, secondary: str | None) -> None:
    page = config.add_page("Executive Overview", "The most important KPIs and performance visuals at a glance.")
    _add_kpi(page, _kpi_title("records", schema), "records", "number", "Total rows in the cleaned dataset.")
    if schema.has("revenue"):
        _add_kpi(page, _kpi_title("revenue", schema), "revenue", "currency", f"Sum of {schema.label_for(schema.role_column('revenue'))}.")
    if schema.has("profit"):
        _add_kpi(page, _kpi_title("profit", schema), "profit", "currency", "Sum of the mapped profit column.")
    if schema.has("revenue") and schema.has("profit"):
        _add_kpi(page, _kpi_title("margin", schema), "margin", "percent", "Profit divided by revenue.")
    if schema.has("quantity"):
        _add_kpi(page, _kpi_title("quantity", schema), "quantity", "number", "Sum of the mapped quantity column.")
    if schema.has("order_id"):
        _add_kpi(page, _kpi_title("orders", schema), "orders", "number", "Distinct order identifiers.")
    if schema.has("customer"):
        _add_kpi(page, _kpi_title("customers", schema), "customers", "number", "Distinct customer identifiers or names.")
    if schema.has("revenue") and schema.has("order_id"):
        _add_kpi(page, _kpi_title("aov", schema), "aov", "currency", "Revenue divided by distinct orders.")
    if schema.has("salary"):
        _add_kpi(page, _kpi_title("salary", schema), "salary", "currency", "Sum of the mapped salary column.")
        _add_kpi(page, _kpi_title("avg_salary", schema), "avg_salary", "currency", "Average salary across rows.")
    if schema.has("employee_id") or schema.has("employee_name"):
        _add_kpi(page, _kpi_title("employees", schema), "employees", "number", "Distinct employees detected.")
    if schema.has("attendance"):
        _add_kpi(page, _kpi_title("attendance_rate", schema), "attendance_rate", "percent", "Share of present/yes attendance values.")
    if schema.has("cost"):
        _add_kpi(page, _kpi_title("cost", schema), "cost", "currency", "Sum of the mapped expense/cost column.")
    if schema.has("revenue") and schema.has("date"):
        _add_kpi(page, _kpi_title("growth", schema), "growth", "percent", "Latest period versus the immediately preceding equal-length period.")

    # Universal fallback: surface a real total for a dominant numeric measure
    # that has no recognised commercial role (for example "Amount" or "Score").
    mapped_measures = {
        schema.role_column(role)
        for role in ("revenue", "profit", "cost", "salary", "grade", "age", "quantity", "unit_price", "discount")
    }
    for candidate in (primary, secondary):
        if candidate and candidate not in mapped_measures and candidate in schema.measures:
            _add_kpi(
                page,
                f"Total {schema.label_for(candidate)}",
                "measure_sum",
                "currency" if candidate == primary and schema.domain in ("retail", "commerce", "finance") else "number",
                f"Sum of the {schema.label_for(candidate)} column across the active rows.",
                measure=candidate,
            )
            mapped_measures.add(candidate)

    if schema.has("date") and primary:
        _add_chart(page, f"{_measure_label(schema, primary)} over time", "line", schema.role_column("date"), primary, width=12, height=340)
    dimensions = preferred_dimensions(schema)
    if dimensions and primary:
        _add_chart(page, f"Top 10 {schema.label_for(dimensions[0])} by {_measure_label(schema, primary)}", "bar", dimensions[0], primary, top_n=10)
    if secondary and secondary != primary:
        dimension = next((d for d in dimensions if d != schema.role_column("date")), None)
        if dimension:
            _add_chart(page, f"{_measure_label(schema, secondary)} by {schema.label_for(dimension)}", "bar", dimension, secondary, top_n=10)
    if primary:
        _add_chart(page, f"Distribution of {_measure_label(schema, primary)}", "histogram", None, primary)
    _add_special(page, "AI business insights", "insights", width=12, height=260)


def _build_sales_page(config: DashboardConfig, schema: DatasetSchema, primary: str | None) -> None:
    if not schema.has("revenue"):
        return
    revenue = schema.role_column("revenue")
    page = config.add_page("Sales Analysis", "Revenue performance by product, category and geography.")
    if schema.has("date"):
        _add_chart(page, "Revenue trend", "line", schema.role_column("date"), revenue, width=12, height=340)
    for role in ("product", "category", "region", "city", "store"):
        column = schema.role_column(role)
        if column:
            _add_chart(page, f"Revenue by {schema.label_for(column)}", "bar", column, revenue, top_n=10)
    if schema.has("quantity"):
        _add_chart(page, "Quantity by category" if schema.has("category") else "Quantity distribution", "bar" if schema.has("category") else "histogram", schema.role_column("category"), schema.role_column("quantity"))
    if schema.has("product"):
        _add_chart(page, "Product performance table", "table", schema.role_column("product"), revenue, width=12, height=360)


def _build_profit_page(config: DashboardConfig, schema: DatasetSchema) -> None:
    if not schema.has("profit"):
        return
    profit = schema.role_column("profit")
    revenue = schema.role_column("revenue")
    page = config.add_page("Profit Analysis", "Where profit is made and where margin is under pressure.")
    if schema.has("date"):
        _add_chart(page, "Profit trend", "line", schema.role_column("date"), profit, width=12, height=340)
    for role in ("product", "category", "region", "city"):
        column = schema.role_column(role)
        if column:
            _add_chart(page, f"Profit by {schema.label_for(column)}", "bar", column, profit, top_n=10)
    if revenue and schema.has("product"):
        _add_chart(page, "Revenue versus profit", "scatter", schema.role_column("product"), revenue, measure_y=profit, width=12, height=380)
    if schema.has("discount") and revenue:
        _add_chart(page, "Margin by discount level", "bar", schema.role_column("discount"), profit, top_n=12)


def _build_customer_page(config: DashboardConfig, schema: DatasetSchema) -> None:
    customer = schema.role_column("customer")
    if not customer:
        return
    measure = schema.role_column("revenue") or primary_measure(schema)
    page = config.add_page("Customer Analysis", "Customer concentration and value.")
    if measure:
        _add_chart(page, f"Top customers by {_measure_label(schema, measure)}", "bar", customer, measure, top_n=15)
    _add_chart(page, "Orders per customer", "bar", customer, None, aggregation="count", top_n=15)
    if schema.has("revenue") and schema.has("order_id"):
        _add_chart(page, "Customer value table", "table", customer, schema.role_column("revenue"), width=12, height=360)


def _build_product_page(config: DashboardConfig, schema: DatasetSchema) -> None:
    product = schema.role_column("product")
    if not product:
        return
    measure = schema.role_column("revenue") or primary_measure(schema)
    page = config.add_page("Product Analysis", "Product-level ranking and profitability.")
    if measure:
        _add_chart(page, f"Top products by {_measure_label(schema, measure)}", "bar", product, measure, top_n=15)
        _add_chart(page, "Product revenue share", "donut", product, measure, top_n=8)
    if schema.has("profit"):
        _add_chart(page, "Profit by product", "bar", product, schema.role_column("profit"), top_n=15)
    _add_chart(page, "Product matrix", "matrix", product, measure, width=12, height=400)


def _build_workforce_page(config: DashboardConfig, schema: DatasetSchema) -> None:
    department = schema.role_column("department")
    salary = schema.role_column("salary")
    employee = schema.role_column("employee_id") or schema.role_column("employee_name")
    if not (department or salary or employee or schema.has("attendance")):
        return
    page = config.add_page("Workforce Analysis", "Headcount, compensation and attendance.")
    if department:
        _add_chart(page, "Headcount by department", "bar", department, None, aggregation="count")
        if salary:
            _add_chart(page, "Salary by department", "bar", department, salary, aggregation="avg")
    if salary:
        _add_chart(page, "Salary distribution", "histogram", None, salary)
    if schema.has("attendance"):
        attendance = schema.role_column("attendance")
        _add_chart(page, "Attendance distribution", "bar", attendance, None, aggregation="count")
        if department:
            _add_chart(page, "Attendance by department", "bar", department, attendance, aggregation="count")
    if employee and salary:
        _add_chart(page, "Employee compensation table", "table", employee, salary, width=12, height=360)


def _build_finance_page(config: DashboardConfig, schema: DatasetSchema) -> None:
    if not (schema.has("revenue") or schema.has("cost")):
        return
    page = config.add_page("Financial Analysis", "Revenue, expenses and profit structure.")
    revenue = schema.role_column("revenue")
    cost = schema.role_column("cost")
    profit = schema.role_column("profit")
    if revenue and schema.has("date"):
        _add_chart(page, "Revenue trend", "line", schema.role_column("date"), revenue, width=12)
    if cost and schema.has("category"):
        _add_chart(page, "Expenses by category", "bar", schema.role_column("category"), cost)
    if revenue and profit:
        _add_chart(page, "Revenue versus profit", "scatter", None, revenue, measure_y=profit, width=12, height=380)
    if profit and schema.has("date"):
        _add_chart(page, "Profit trend", "line", schema.role_column("date"), profit, width=12)


def _build_education_page(config: DashboardConfig, schema: DatasetSchema) -> None:
    grade = schema.role_column("grade")
    course = schema.role_column("course")
    if not (grade or course or schema.has("attendance")):
        return
    page = config.add_page("Academic Analysis", "Course performance, grades and attendance.")
    if course and grade:
        _add_chart(page, "Average grade by course", "bar", course, grade, aggregation="avg")
        _add_chart(page, "Grade distribution", "histogram", None, grade)
    if course:
        _add_chart(page, "Enrollment by course", "bar", course, None, aggregation="count")
    if schema.has("attendance") and course:
        _add_chart(page, "Attendance by course", "bar", course, schema.role_column("attendance"), aggregation="count")


def _build_quality_page(config: DashboardConfig) -> None:
    page = config.add_page("Data Quality", "Factual profile of the uploaded dataset and missingness.")
    _add_special(page, "Dataset profile", "profile_table", width=12, height=430)
    _add_special(page, "Missing values by column", "missing_bar", width=12, height=380)


def build_dashboard(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    dataset_name: str,
    dataset_id: str,
    dashboard_name: str | None = None,
) -> DashboardConfig:
    """Create a complete auto dashboard for the dataset."""
    stem = dataset_name.rsplit(".", 1)[0] if "." in dataset_name else dataset_name
    config = DashboardConfig(
        name=dashboard_name or f"{stem} — RetailMind AI",
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        domain=schema.domain,
        theme=Theme(preset="dark", palette=PALETTES["dark"]),
    )
    primary = primary_measure(schema)
    secondary = secondary_measure(schema)

    _build_overview(config, schema, primary, secondary)
    if schema.domain in ("retail", "commerce", "finance"):
        _build_sales_page(config, schema, primary)
    if schema.has("profit"):
        _build_profit_page(config, schema)
    if schema.has("customer"):
        _build_customer_page(config, schema)
    if schema.has("product"):
        _build_product_page(config, schema)
    if schema.domain == "hr":
        _build_workforce_page(config, schema)
    if schema.domain in ("finance", "operations"):
        _build_finance_page(config, schema)
    if schema.domain == "education":
        _build_education_page(config, schema)
    # Keep the dashboard focused: at most six business pages plus quality.
    if len(config.pages) > 6:
        config.pages = config.pages[:6]
    _build_quality_page(config)
    return config


def plan_summary(config: DashboardConfig) -> DashboardPlan:
    counts = config.counts()
    return DashboardPlan(pages=counts["pages"], kpis=counts["kpis"], charts=counts["charts"], domain=config.domain)


def add_component_to_page(config: DashboardConfig, page_name: str, component: Component) -> Component:
    page = config.add_page(page_name or "Custom")
    return page.add(component)
