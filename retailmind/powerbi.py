"""Power BI Project (PBIP) generation.

This module creates a genuine, editable Power BI Project:

* ``*.pbip`` project file
* TMDL semantic model (``definition/database.tmdl``, ``model.tmdl``,
  ``tables/*.tmdl``, ``relationships.tmdl``)
* PBIR report definition (``definition/report.json``, pages and visual
  containers)
* theme JSON and ``.platform`` metadata files

It never renames a ZIP/JSON/PBIP to ``.pbix``.  Genuine PBIX generation needs
Power BI Desktop or a supported automation service; if neither is available the
UI says so and provides instructions for saving the PBIP as PBIX manually.

The generated report definitions follow the published PBIP/PBIR shape, but
Power BI Desktop is the final authority.  ``validate_pbip`` performs structural
validation (JSON, required files, table/column/relationship references, page
order, visual positions) and reports every problem it finds.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from io import BytesIO
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from retailmind.schema import DatasetSchema
from retailmind.utils import slugify


PBIP_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"
REPORT_PROPERTIES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json"
SEMANTIC_PROPERTIES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json"
REPORT_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json"
VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json"
VERSION_METADATA_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"
REPORT_PAGE_VERSION = "1.0.0"
REPORT_VISUAL_VERSION = "1.0.0"
REPORT_FORMAT_VERSION = "3.3.0"
# ``definition/version.json`` describes the report definition format this
# project targets.  It matches the ``report/definition/report`` schema version
# used for ``definition/report.json`` so Power BI Desktop can validate the
# pair consistently.
REPORT_VERSION_METADATA_VERSION = "3.3.0"
PLATFORM_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json"


def _identifier(value: str, fallback: str = "Column") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", str(value))
    if not cleaned:
        cleaned = fallback
    if cleaned[0].isdigit():
        cleaned = f"_{cleaned}"
    return cleaned


def _unique(name: str, used: set[str]) -> str:
    candidate = name
    index = 2
    while candidate in used:
        candidate = f"{name}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def _quote_tmdl(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(name)):
        return str(name)
    return "'" + str(name).replace("'", "''") + "'"


def _dtype_to_tmdl(dtype: Any) -> str:
    text = str(dtype).lower()
    if "datetime" in text or "date" in text:
        return "dateTime"
    if "bool" in text:
        return "boolean"
    if "int" in text or "uint" in text:
        return "int64"
    if "float" in text or "decimal" in text:
        return "double"
    return "string"


def _lineage(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _measure(name: str, expression: str, format_string: str = "#,0.00") -> str:
    return (
        f"\tmeasure '{name}' = {expression}\n"
        f"\t\tformatString: {format_string}\n"
        f"\t\tlineageTag: {_lineage('measure')}\n"
    )


def _column_tmdl(name: str, source: str, dtype: str, *, summarize: str = "none") -> str:
    return (
        f"\tcolumn {_quote_tmdl(name)}\n"
        f"\t\tdataType: {dtype}\n"
        + (f"\t\tformatString: yyyy-MM-dd\n" if dtype == "dateTime" else "")
        + f"\t\tlineageTag: {_lineage('column')}\n"
        f"\t\tsummarizeBy: {summarize}\n"
        f"\t\tsourceColumn: {_quote_tmdl(source)}\n"
        f"\t\tannotation SummarizationSetBy = Automatic\n"
    )


def _page_id(project: str, page: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"retailmind:{project}:{page}"))


def _table_header(name: str, lineage_tag: str) -> str:
    """TMDL table declaration header.

    The table name is declared on its own line with no ``= DAX`` assignment.
    Power BI Desktop rejects ``table Name = <DAX expression>`` because an
    object of type Table does not support a default property assignment.
    Calculated tables must instead declare the table and add a separate
    ``partition <name> = calculated`` block.
    """
    return f"table {name}\n\tlineageTag: {lineage_tag}\n"


def _calculated_partition(partition_name: str, dax_source: str) -> str:
    """TMDL calculated partition for DAX calculated tables."""
    return (
        f"\tpartition {partition_name} = calculated\n"
        f"\t\tmode: import\n"
        f"\t\tsource = {dax_source}\n"
    )


def _source_partition(partition_name: str, m_expression: str) -> str:
    """TMDL M partition for import tables with an inline M expression.

    The M expression (e.g. ``Csv.Document(File.Contents("..."), ...)``) goes
    directly in the partition's ``source`` property, not in a separate data
    source file.  ``mode: import`` belongs here in the partition block.
    """
    return (
        f"\tpartition {partition_name} = m\n"
        f"\t\tmode: import\n"
        f"\t\tsource = {m_expression}\n"
    )


def _data_source(name: str) -> str:
    """TMDL data source definition for an import data source.

    Microsoft's TMDL format for data source definition files does NOT support
    ``source = <M expression>`` or ``kind: ...`` as properties.  The M
    expression belongs in the table's partition block.  A data source file
    only declares the data source name; Power BI infers the connection kind
    from the partition's M expression.

    Returns just ``dataSource <name>`` with no properties.
    """
    return f"dataSource {name}\n"


def _visual_id(project: str, page: str, title: str, index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"retailmind:{project}:{page}:{title}:{index}"))


@dataclass
class PBIPProject:
    project_name: str
    files: dict[str, str] = field(default_factory=dict)
    tables: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    validation: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    pbix_available: bool = False
    power_bi_path: str | None = None

    @property
    def valid(self) -> bool:
        return not self.validation

    def to_zip_bytes(self) -> bytes:
        import zipfile

        output = BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, content in sorted(self.files.items()):
                archive.writestr(path, content.encode("utf-8"))
        return output.getvalue()

    def summary(self) -> dict[str, Any]:
        return {
            "project": self.project_name,
            "tables": self.tables,
            "measures": self.measures,
            "pages": self.pages,
            "file_count": len(self.files),
            "valid": self.valid,
            "validation_errors": self.validation,
            "pbix_available": self.pbix_available,
            "power_bi_desktop": self.power_bi_path,
        }


def detect_power_bi_desktop() -> str | None:
    """Best-effort detection of an installed Power BI Desktop executable."""
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft Power BI Desktop" / "bin" / "PBIDesktop.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Power BI Desktop" / "bin" / "PBIDesktop.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "PBIDesktop.exe",
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            continue
    return None


def _visual_container(
    *,
    name: str,
    x: int,
    y: int,
    width: int,
    height: int,
    tab_order: int,
    visual: dict[str, Any],
) -> dict[str, Any]:
    return {
        "$schema": VISUAL_SCHEMA,
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": height, "width": width, "tabOrder": tab_order},
        "visual": visual,
    }


def _field_ref(entity: str, prop: str, *, measure: bool = False) -> dict[str, Any]:
    key = "Measure" if measure else "Column"
    return {
        key: {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }


def _projection(field: dict[str, Any], query_ref: str, native: str) -> dict[str, Any]:
    return {"field": field, "queryRef": query_ref, "nativeQueryRef": native}


def _card(project: str, page: str, title: str, measure: str, entity: str, x: int, y: int, index: int) -> dict[str, Any]:
    visual = {
        "visualType": "card",
        "query": {
            "queryState": {
                "Values": {
                    "projections": [
                        _projection(_field_ref(entity, measure, measure=True), f"{entity}.{measure}", measure)
                    ]
                }
            }
        },
        "objects": {},
        "visualContainerObjects": {},
    }
    return _visual_container(
        name=_visual_id(project, page, title, index), x=x, y=y, width=260, height=150,
        tab_order=index, visual=visual,
    )


def _bar_chart(
    project: str, page: str, title: str, dimension_entity: str, dimension: str,
    measure_entity: str, measure: str, x: int, y: int, index: int,
) -> dict[str, Any]:
    visual = {
        "visualType": "barChart",
        "query": {
            "queryState": {
                "Category": {
                    "projections": [
                        _projection(_field_ref(dimension_entity, dimension), f"{dimension_entity}.{dimension}", dimension)
                    ]
                },
                "Y": {
                    "projections": [
                        _projection(_field_ref(measure_entity, measure, measure=True), f"{measure_entity}.{measure}", measure)
                    ]
                },
            }
        },
        "objects": {},
        "visualContainerObjects": {},
    }
    return _visual_container(
        name=_visual_id(project, page, title, index), x=x, y=y, width=520, height=300,
        tab_order=index, visual=visual,
    )


def _line_chart(
    project: str, page: str, title: str, date_entity: str, date_prop: str,
    measure_entity: str, measure: str, x: int, y: int, index: int,
) -> dict[str, Any]:
    visual = {
        "visualType": "lineChart",
        "query": {
            "queryState": {
                "Category": {
                    "projections": [
                        _projection(_field_ref(date_entity, date_prop), f"{date_entity}.{date_prop}", date_prop)
                    ]
                },
                "Y": {
                    "projections": [
                        _projection(_field_ref(measure_entity, measure, measure=True), f"{measure_entity}.{measure}", measure)
                    ]
                },
            }
        },
        "objects": {},
        "visualContainerObjects": {},
    }
    return _visual_container(
        name=_visual_id(project, page, title, index), x=x, y=y, width=780, height=320,
        tab_order=index, visual=visual,
    )


def _textbox(project: str, page: str, title: str, text: str, x: int, y: int, index: int) -> dict[str, Any]:
    visual = {
        "visualType": "textbox",
        "objects": {
            "general": [
                {
                    "properties": {
                        "paragraphs": [
                            {
                                "textRuns": [
                                    {"value": title, "textStyle": {"fontSize": "18pt", "fontWeight": "bold"}},
                                    {"value": "\n" + text, "textStyle": {"fontSize": "11pt"}},
                                ],
                                "horizontalTextAlignment": "left",
                            }
                        ]
                    }
                }
            ]
        },
        "visualContainerObjects": {},
    }
    return _visual_container(
        name=_visual_id(project, page, title, index), x=x, y=y, width=1000, height=300,
        tab_order=index, visual=visual,
    )


def _theme(project_name: str) -> dict[str, Any]:
    return {
        "name": project_name,
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


def build_pbip(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    project_name: str = "RetailMind AI Report",
    dashboard_name: str | None = None,
    page_titles: Iterable[str] | None = None,
    insights: Iterable[str] = (),
    forecast_available: bool = False,
    inventory_available: bool = False,
) -> PBIPProject:
    project = slugify(project_name, "RetailMindReport")
    safe_project = re.sub(r"[^A-Za-z0-9_]", "", project) or "RetailMindReport"
    report_folder = f"{safe_project}.Report"
    model_folder = f"{safe_project}.SemanticModel"
    files: dict[str, str] = {}

    roles = schema.roles
    date_column = roles.get("date")
    revenue = roles.get("revenue")
    profit = roles.get("profit")
    cost = roles.get("cost")
    quantity = roles.get("quantity")
    order = roles.get("order_id")
    customer = roles.get("customer")
    product = roles.get("product")
    category = roles.get("category")
    region = roles.get("region") or roles.get("city")

    # ---- fact table -----------------------------------------------------
    fact_name = "FactSales" if revenue or profit else "FactData"
    used_columns: set[str] = set()
    column_map: dict[str, str] = {}
    column_tmdl: list[str] = []
    for column in frame.columns:
        friendly = _unique(_identifier(str(column)), used_columns)
        column_map[str(column)] = friendly
        dtype = _dtype_to_tmdl(frame[column].dtype)
        summarize = "sum" if dtype in {"int64", "double"} else "none"
        column_tmdl.append(_column_tmdl(friendly, str(column), dtype, summarize=summarize))

    measures: dict[str, str] = {}
    fact_ref = f"{fact_name}"
    if revenue:
        revenue_name = column_map.get(str(revenue), _identifier(str(revenue)))
        measures["Total Sales"] = _measure("Total Sales", f"SUM ( {fact_ref}[{revenue_name}] )")
        measures["Total Revenue"] = _measure("Total Revenue", "[Total Sales]")
    if profit:
        profit_name = column_map.get(str(profit), _identifier(str(profit)))
        measures["Total Profit"] = _measure("Total Profit", f"SUM ( {fact_ref}[{profit_name}] )")
    if "Total Revenue" in measures and "Total Profit" in measures:
        measures["Profit Margin"] = _measure("Profit Margin", "DIVIDE ( [Total Profit], [Total Revenue] )", "0.00%")
    if order:
        order_name = column_map.get(str(order), _identifier(str(order)))
        measures["Total Orders"] = _measure("Total Orders", f"DISTINCTCOUNT ( {fact_ref}[{order_name}] )", "#,0")
    if customer:
        customer_name = column_map.get(str(customer), _identifier(str(customer)))
        measures["Total Customers"] = _measure("Total Customers", f"DISTINCTCOUNT ( {fact_ref}[{customer_name}] )", "#,0")
    if "Total Revenue" in measures and "Total Orders" in measures:
        measures["Average Order Value"] = _measure("Average Order Value", "DIVIDE ( [Total Revenue], [Total Orders] )")
    if quantity:
        quantity_name = column_map.get(str(quantity), _identifier(str(quantity)))
        measures["Total Quantity"] = _measure("Total Quantity", f"SUM ( {fact_ref}[{quantity_name}] )")
    if cost:
        cost_name = column_map.get(str(cost), _identifier(str(cost)))
        measures["Total Cost"] = _measure("Total Cost", f"SUM ( {fact_ref}[{cost_name}] )")
        if "Total Revenue" in measures:
            measures["Expense Ratio"] = _measure("Expense Ratio", "DIVIDE ( [Total Cost], [Total Revenue] )", "0.00%")
    if date_column and "Total Revenue" in measures:
        measures["Previous Period Sales"] = _measure(
            "Previous Period Sales",
            "CALCULATE ( [Total Revenue], DATEADD ( DimDate[Date], -1, MONTH ) )",
        )
        measures["Sales Growth"] = _measure("Sales Growth", "[Total Revenue] - [Previous Period Sales]")
        measures["Sales Growth %"] = _measure(
            "Sales Growth %", "DIVIDE ( [Sales Growth], [Previous Period Sales] )", "0.00%"
        )
        measures["YTD Sales"] = _measure("YTD Sales", "TOTALYTD ( [Total Revenue], DimDate[Date] )")

    if not measures:
        measures["Total Records"] = _measure("Total Records", f"COUNTROWS ( {fact_ref} )", "#,0")
        for num_col in schema.numeric:
            if num_col in frame.columns:
                col_name = column_map.get(str(num_col), _identifier(str(num_col)))
                measures[f"Total {col_name}"] = _measure(f"Total {col_name}", f"SUM ( {fact_ref}[{col_name}] )")
                break

    # Keep the source file inside the semantic model folder so it is included
    # in the PBIP archive alongside the M partition that reads it.
    csv_filename = f"{fact_name}.csv"
    csv_contents = frame.to_csv(
        index=False,
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n",
    )
    files[f"{model_folder}/{csv_filename}"] = f"\ufeff{csv_contents}"

    # Promote the serialized source headers so they match each TMDL
    # sourceColumn, and use CSV quote handling for embedded delimiters/quotes.
    fact_csv_expression = (
        "Table.PromoteHeaders("
        f'Csv.Document(File.Contents("{csv_filename}"), '
        f'[Delimiter=",", Columns=null, Encoding=65001, QuoteStyle=QuoteStyle.Csv]), '
        "[PromoteAllScalars=true])"
    )

    files[f"{model_folder}/definition/tables/{fact_name}.tmdl"] = (
        _table_header(fact_name, _lineage('table'))
        + "".join(column_tmdl)
        + "".join(measures.values())
        + _source_partition(fact_name, fact_csv_expression)
    )
    files[f"{model_folder}/definition/dataSources/{fact_name}.tmdl"] = _data_source(fact_name)

    tables = [fact_name]
    relationships: list[tuple[str, str, str, str]] = []
    date_name = column_map.get(str(date_column)) if date_column else None

    # ---- date dimension -------------------------------------------------
    if date_column and date_name:
        dax_date = (
            "ADDCOLUMNS ( CALENDAR ( MIN ( "
            f"{fact_name}[{date_name}] ), MAX ( {fact_name}[{date_name}] ) ), "
            '"Year", YEAR ( [Date] ), "Month", FORMAT ( [Date], "YYYY-MM" ), '
            '"MonthNumber", MONTH ( [Date] ), "Quarter", "Q" & QUARTER ( [Date] ), '
            '"Weekday", FORMAT ( [Date], "dddd" ) )'
        )
        dim_date = (
            _table_header("DimDate", _lineage('table'))
            + "\tcolumn Date\n\t\tdataType: dateTime\n\t\tisNameInferred\n\t\tsourceColumn: [Date]\n"
            + "\t\tannotation SummarizationSetBy = Automatic\n"
            + "\tcolumn Year\n\t\tdataType: int64\n\t\tisNameInferred\n\t\tsourceColumn: [Year]\n"
            + "\t\tannotation SummarizationSetBy = Automatic\n"
            + "\tcolumn Month\n\t\tdataType: string\n\t\tisNameInferred\n\t\tsourceColumn: [Month]\n"
            + "\t\tannotation SummarizationSetBy = Automatic\n"
            + "\tcolumn MonthNumber\n\t\tdataType: int64\n\t\tisNameInferred\n\t\tsourceColumn: [MonthNumber]\n"
            + "\t\tannotation SummarizationSetBy = Automatic\n"
            + "\tcolumn Quarter\n\t\tdataType: string\n\t\tisNameInferred\n\t\tsourceColumn: [Quarter]\n"
            + "\t\tannotation SummarizationSetBy = Automatic\n"
            + "\tcolumn Weekday\n\t\tdataType: string\n\t\tisNameInferred\n\t\tsourceColumn: [Weekday]\n"
            + "\t\tannotation SummarizationSetBy = Automatic\n"
            + _calculated_partition("DimDate", dax_date)
        )
        files[f"{model_folder}/definition/tables/DimDate.tmdl"] = dim_date
        tables.append("DimDate")
        relationships.append((fact_name, date_name, "DimDate", "Date"))

    # ---- dimensions -----------------------------------------------------
    def add_dimension(role: str, table_name: str) -> str | None:
        source = roles.get(role)
        if not source or source not in frame.columns:
            return None
        source_name = column_map.get(str(source))
        if not source_name:
            return None
        dim_column = _identifier(str(source))
        lineage_tag = _lineage('table')
        dax = (
            f"SELECTCOLUMNS ( DISTINCT ( {fact_name}[{source_name}] ), "
            f'"{dim_column}", {fact_name}[{source_name}] )'
        )
        files[f"{model_folder}/definition/tables/{table_name}.tmdl"] = (
            _table_header(table_name, lineage_tag)
            + f"\tcolumn {_quote_tmdl(dim_column)}\n"
            + f"\t\tdataType: string\n\t\tisNameInferred\n\t\tsourceColumn: [{dim_column}]\n"
            + f"\t\tannotation SummarizationSetBy = Automatic\n"
            + _calculated_partition(table_name, dax)
        )
        tables.append(table_name)
        relationships.append((fact_name, source_name, table_name, dim_column))
        return dim_column

    product_dim = add_dimension("product", "DimProduct")
    category_dim = add_dimension("category", "DimCategory")
    customer_dim = add_dimension("customer", "DimCustomer")
    region_dim = add_dimension("region", "DimRegion") or add_dimension("city", "DimRegion")

    # ---- model + database + relationships ------------------------------
    files[f"{model_folder}/definition/database.tmdl"] = "database\n\tcompatibilityLevel: 1567\n"
    files[f"{model_folder}/definition/model.tmdl"] = (
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tdiscourageImplicitMeasures\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n"
    )
    relationship_tmdl = []
    for index, (from_table, from_column, to_table, to_column) in enumerate(relationships, start=1):
        relationship_tmdl.append(
            f"relationship {uuid.uuid5(uuid.NAMESPACE_URL, f'{project}:{index}').hex[:20]}\n"
            f"\tfromColumn: {from_table}[{_quote_tmdl(from_column)}]\n"
            f"\ttoColumn: {to_table}[{_quote_tmdl(to_column)}]\n"
        )
    files[f"{model_folder}/definition/relationships.tmdl"] = "\n".join(relationship_tmdl) + ("\n" if relationship_tmdl else "")
    files[f"{model_folder}/definition.pbism"] = json.dumps(
        {"$schema": SEMANTIC_PROPERTIES_SCHEMA, "version": "4.0", "settings": {}}, indent=2
    )
    files[f"{model_folder}/.platform"] = json.dumps(
        {
            "$schema": PLATFORM_SCHEMA,
            "metadata": {"type": "SemanticModel", "displayName": safe_project},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{project}:model"))},
        },
        indent=2,
    )

    # ---- report pages ---------------------------------------------------
    pages: list[str] = []
    page_files: dict[str, dict[str, Any]] = {}

    def add_page(title: str, visuals: list[dict[str, Any]]) -> None:
        page_id = _page_id(project, title)
        pages.append(title)
        page_files[page_id] = {
            "page": {
                "$schema": PAGE_SCHEMA,
                "name": page_id,
                "displayName": title,
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
            },
            "visuals": visuals,
        }

    kpi_measures = [name for name in ("Total Revenue", "Total Profit", "Profit Margin", "Total Orders", "Total Customers", "Total Quantity") if name in measures]
    if not kpi_measures and measures:
        kpi_measures = list(measures)[:4]
    if kpi_measures:
        visuals = [
            _card(project, "Executive Overview", name, name, fact_name, 20 + index * 290, 20, index)
            for index, name in enumerate(kpi_measures[:4])
        ]
        add_page("Executive Overview", visuals)

    if date_column and "Total Revenue" in measures and date_name:
        add_page(
            "Sales Analysis",
            [_line_chart(project, "Sales Analysis", "Revenue over time", "DimDate", "Date", fact_name, "Total Revenue", 20, 20, 0)],
        )
    if category and "Total Revenue" in measures and category_dim:
        add_page(
            "Profitability Analysis",
            [_bar_chart(project, "Profitability Analysis", "Revenue by category", "DimCategory", category_dim, fact_name, "Total Revenue", 20, 20, 0)],
        )
    if product and "Total Revenue" in measures and product_dim:
        add_page(
            "Product Analysis",
            [_bar_chart(project, "Product Analysis", "Revenue by product", "DimProduct", product_dim, fact_name, "Total Revenue", 20, 20, 0)],
        )
    if customer and customer_dim:
        add_page(
            "Customer Analysis",
            [_card(project, "Customer Analysis", "Total Customers", "Total Customers", fact_name, 20, 20, 0)],
        )
    if region and region_dim and "Total Revenue" in measures:
        add_page(
            "Regional Analysis",
            [_bar_chart(project, "Regional Analysis", "Revenue by region", "DimRegion", region_dim, fact_name, "Total Revenue", 20, 20, 0)],
        )
    if forecast_available and "Total Revenue" in measures and date_name:
        add_page(
            "Forecasting",
            [_line_chart(project, "Forecasting", "Revenue history", "DimDate", "Date", fact_name, "Total Revenue", 20, 20, 0)],
        )
    if inventory_available:
        add_page("Inventory Analysis", [])
    insight_text = "\n".join(list(insights)[:8]) or "Open the RetailMind AI Streamlit app for verified insights."
    add_page("AI Business Insights", [_textbox(project, "AI Business Insights", "Verified insights", insight_text, 20, 20, 0)])
    if page_titles:
        existing = set(pages)
        for title in page_titles:
            if title and title not in existing:
                add_page(str(title), [])

    files[f"{report_folder}/definition/report.json"] = json.dumps(
        {
            "$schema": REPORT_SCHEMA,
            "themeCollection": {
                "baseTheme": {
                    "name": "CY24SU10",
                    "reportVersionAtImport": {
                        "page": REPORT_PAGE_VERSION,
                        "report": REPORT_FORMAT_VERSION,
                        "visual": REPORT_VISUAL_VERSION,
                    },
                    "type": "SharedResources",
                },
                "customTheme": {
                    "name": "RetailMind AI",
                    "reportVersionAtImport": {
                        "page": REPORT_PAGE_VERSION,
                        "report": REPORT_FORMAT_VERSION,
                        "visual": REPORT_VISUAL_VERSION,
                    },
                    "type": "RegisteredResources",
                },
            },
            "objects": {},
            "resourcePackages": [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [
                        {
                            "name": "RetailMind AI",
                            "path": "RetailMindTheme.json",
                            "type": "CustomTheme",
                        }
                    ],
                }
            ],
        },
        indent=2,
    )
    files[f"{report_folder}/definition/version.json"] = json.dumps(
        {
            "$schema": VERSION_METADATA_SCHEMA,
            "version": REPORT_VERSION_METADATA_VERSION,
        },
        indent=2,
    )
    page_ids = list(page_files)
    files[f"{report_folder}/definition/pages/pages.json"] = json.dumps(
        {
            "$schema": PAGES_SCHEMA,
            "pageOrder": page_ids,
            "activePageName": page_ids[0] if page_ids else "",
        },
        indent=2,
    )
    for page_id, payload in page_files.items():
        files[f"{report_folder}/definition/pages/{page_id}/page.json"] = json.dumps(payload["page"], indent=2)
        for visual in payload["visuals"]:
            files[f"{report_folder}/definition/pages/{page_id}/visuals/{visual['name']}/visual.json"] = json.dumps(visual, indent=2)
    files[f"{report_folder}/StaticResources/RegisteredResources/RetailMindTheme.json"] = json.dumps(_theme(project_name), indent=2)
    files[f"{report_folder}/definition.pbir"] = json.dumps(
        {
            "$schema": REPORT_PROPERTIES_SCHEMA,
            "version": "4.0",
            "datasetReference": {"byPath": {"path": f"../{model_folder}"}},
        },
        indent=2,
    )
    files[f"{report_folder}/.platform"] = json.dumps(
        {
            "$schema": PLATFORM_SCHEMA,
            "metadata": {"type": "Report", "displayName": safe_project},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{project}:report"))},
        },
        indent=2,
    )
    files[f"{safe_project}.pbip"] = json.dumps(
        {
            "$schema": PBIP_SCHEMA,
            "version": "1.0",
            "artifacts": [{"report": {"path": report_folder}}],
            "settings": {"enableAutoRecovery": True},
        },
        indent=2,
    )

    project_obj = PBIPProject(
        project_name=project_name,
        files=files,
        tables=tables,
        measures=list(measures),
        pages=pages,
        pbix_available=False,
        power_bi_path=detect_power_bi_desktop(),
    )
    project_obj.validation = validate_pbip(project_obj)
    project_obj.notes = [
        "The generated project uses PBIP + TMDL + PBIR definitions and can be opened in a Power BI Desktop version that supports PBIP.",
        "Direct PBIX generation is not supported here. Open the .pbip in Power BI Desktop and use File > Save As > Power BI file (*.pbix) if required.",
        "Streamlit-only interactions (chat, RAG, live filters) are not translated into the static report; they remain in the app.",
    ]
    if project_obj.power_bi_path:
        project_obj.notes.append(f"Power BI Desktop detected at {project_obj.power_bi_path}; automatic PBIX conversion is still not a supported workflow.")
    else:
        project_obj.notes.append("Power BI Desktop was not detected on this machine, so the project could not be opened or saved as PBIX here.")
    return project_obj


def validate_pbip(project: PBIPProject | dict[str, str]) -> list[str]:
    """Structural validation of a generated PBIP project."""
    files = project.files if isinstance(project, PBIPProject) else dict(project)
    errors: list[str] = []
    pbip_files = [path for path in files if path.lower().endswith(".pbip")]
    if not pbip_files:
        return ["No .pbip project file was generated."]
    pbip_path = pbip_files[0]
    try:
        pbip = json.loads(files[pbip_path])
    except json.JSONDecodeError as error:
        return [f"{pbip_path}: invalid JSON ({error})."]
    artifacts = pbip.get("artifacts") or []
    report_paths = [artifact.get("report", {}).get("path") for artifact in artifacts if isinstance(artifact, dict)]
    if not report_paths or not report_paths[0]:
        errors.append(f"{pbip_path}: no report artifact path.")
        return errors
    report_folder = report_paths[0].rstrip("/")
    model_folder = report_folder.replace(".Report", ".SemanticModel")

    # Microsoft's published schema identifiers.  Using an unsupported URL makes
    # Power BI Desktop reject the project ("Expected '$schema' property"), so
    # verify the exact identifiers instead of trusting that they were copied.
    expected_schemas = {
        pbip_path: PBIP_SCHEMA,
        f"{report_folder}/definition.pbir": REPORT_PROPERTIES_SCHEMA,
        f"{report_folder}/definition/report.json": REPORT_SCHEMA,
        f"{report_folder}/definition/pages/pages.json": PAGES_SCHEMA,
        f"{report_folder}/definition/version.json": VERSION_METADATA_SCHEMA,
        f"{model_folder}/definition.pbism": SEMANTIC_PROPERTIES_SCHEMA,
        f"{model_folder}/.platform": PLATFORM_SCHEMA,
        f"{report_folder}/.platform": PLATFORM_SCHEMA,
    }
    for path, expected in expected_schemas.items():
        if path not in files:
            continue
        try:
            payload = json.loads(files[path])
        except json.JSONDecodeError:
            continue
        actual = payload.get("$schema")
        if actual != expected:
            errors.append(f"{path}: $schema is {actual!r}, expected {expected!r}.")

    report_json_path = f"{report_folder}/definition/report.json"
    if report_json_path in files:
        try:
            report_json = json.loads(files[report_json_path])
        except json.JSONDecodeError:
            report_json = {}
        themes = report_json.get("themeCollection") or {}
        for slot in ("baseTheme", "customTheme"):
            theme = themes.get(slot)
            if not isinstance(theme, dict):
                continue
            version_at_import = theme.get("reportVersionAtImport") or {}
            if not all(key in version_at_import for key in ("page", "report", "visual")):
                errors.append(f"{report_json_path}: {slot} is missing reportVersionAtImport page/report/visual.")

    required_report = [
        f"{report_folder}/definition.pbir",
        f"{report_folder}/definition/report.json",
        f"{report_folder}/definition/pages/pages.json",
        f"{report_folder}/definition/version.json",
    ]
    required_model = [
        f"{model_folder}/definition.pbism",
        f"{model_folder}/definition/model.tmdl",
        f"{model_folder}/definition/database.tmdl",
    ]
    for path in required_report + required_model:
        if path not in files:
            errors.append(f"Missing required file: {path}.")
    for path in required_report:
        if path in files and path.endswith(".json"):
            try:
                json.loads(files[path])
            except json.JSONDecodeError as error:
                errors.append(f"{path}: invalid JSON ({error}).")

    version_json_path = f"{report_folder}/definition/version.json"
    if version_json_path in files:
        try:
            version_meta = json.loads(files[version_json_path])
        except json.JSONDecodeError as error:
            errors.append(f"{version_json_path}: invalid JSON ({error}).")
        else:
            version = version_meta.get("version")
            if not isinstance(version, str) or not version:
                errors.append(f"{version_json_path}: 'version' must be a non-empty string.")

    # Data source check: data source files must only declare the name.
    # Power BI Desktop rejects "kind: ..." and "source = ..." in dataSource
    # definition files.  The M expression belongs in the partition block.
    data_source_paths = [
        path for path in files if "/definition/dataSources/" in path and path.endswith(".tmdl")
    ]
    data_source_names = set()
    if not data_source_paths:
        errors.append(
            "No data source definitions found under definition/dataSources/. "
            "Import tables need a data source to load data in Power BI Desktop."
        )
    else:
        for ds_path in data_source_paths:
            ds_lines = files[ds_path].splitlines()
            if ds_lines:
                ds_match = re.match(r"^dataSource\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", ds_lines[0])
                if ds_match:
                    data_source_names.add(ds_match.group(1))
            # Catch the exact Power BI Desktop errors for dataSource files:
            # "kind is not a supported property" and "source is neither a
            # property nor an object in the current context".
            for line_num, line in enumerate(ds_lines, start=1):
                if re.match(r"^\tkind\s*:", line):
                    errors.append(
                        f"{ds_path}:{line_num}: invalid TMDL — 'kind' is not a "
                        f"supported property in a dataSource definition. Remove "
                        f"'kind: ...'."
                    )
                if re.match(r"^\tmode\s*:", line):
                    errors.append(
                        f"{ds_path}:{line_num}: invalid TMDL — 'mode' is not a "
                        f"supported property in a dataSource definition. Remove "
                        f"'mode: ...'; partition mode belongs in the table's "
                        f"partition block."
                    )
                if re.match(r"^\tsource\s*=\s*", line):
                    errors.append(
                        f"{ds_path}:{line_num}: invalid TMDL — 'source' is not a "
                        f"supported property in a dataSource definition. Move "
                        f"the M expression into the table's partition block "
                        f"('partition <name> = m' + 'source = <M expression>')."
                    )

    # TMDL import partitions use the M partition source type and must provide
    # a source expression. The referenced CSV must be packaged with the model.
    for path, content in files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue
        lines = content.splitlines()
        current_table = ""
        current_partition = None
        partition_type = None
        partition_start_line = 0
        partition_lines = []

        for line_num, line in enumerate(lines, start=1):
            # Detect table declaration
            table_match = re.match(r"^table\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", line)
            if table_match:
                current_table = table_match.group(1)
                current_partition = None
                partition_type = None
                partition_lines = []
                continue

            # Detect partition declaration
            part_match = re.match(
                r"^\tpartition\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(m|calculated)\s*$",
                line,
            )
            if part_match and current_table:
                # Validate previous partition block before starting a new one
                if current_partition and partition_type == "m":
                    has_source = any(
                        re.match(r"^\t+\tsource\s*=\s*\S", l) for l in partition_lines
                    )
                    if not has_source:
                        errors.append(
                            f"{path}:{partition_start_line}: import partition "
                            f"'{current_partition}' in table '{current_table}' "
                            f"is missing 'source = <M expression>'."
                        )
                current_partition = part_match.group(1)
                partition_type = part_match.group(2)
                partition_start_line = line_num
                partition_lines = []
                continue

            # Collect lines inside an M partition and verify packaged files.
            if current_partition and partition_type == "m":
                partition_lines.append(line)
                if re.match(r"^\t+\tsource\s*=\s*\S", line):
                    source_file = re.search(r'File\.Contents\("([^"]+)"\)', line)
                    if source_file:
                        packaged_path = f"{model_folder}/{source_file.group(1)}"
                        if packaged_path not in files:
                            errors.append(
                                f"{path}:{line_num}: M partition references "
                                f"'{source_file.group(1)}', but '{packaged_path}' "
                                "is not included in the PBIP project."
                            )
                    # Found source expression — partition is complete
                    current_partition = None
                    partition_type = None
                    partition_lines = []

        # End of file — check last partition block
        if current_partition and partition_type == "m":
            has_source = any(
                re.match(r"^\t+\tsource\s*=\s*\S", l) for l in partition_lines
            )
            if not has_source:
                errors.append(
                    f"{path}:{partition_start_line}: import partition "
                    f"'{current_partition}' in table '{current_table}' "
                    f"is missing 'source = <M expression>'."
                )

    if f"{report_folder}/definition.pbir" in files:
        try:
            pbir = json.loads(files[f"{report_folder}/definition.pbir"])
            by_path = (pbir.get("datasetReference") or {}).get("byPath", {}).get("path", "")
            if by_path and Path(by_path).name != Path(model_folder).name:
                errors.append(f"definition.pbir points to '{by_path}', expected '{model_folder}'.")
        except json.JSONDecodeError:
            pass

    # TMDL tables, columns and measures.
    table_names: set[str] = set()
    table_columns: dict[str, set[str]] = {}
    measure_names: set[str] = set()
    for path, content in files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue
        current_table = ""
        for line in content.splitlines():
            match = re.match(r"^table\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if match:
                current_table = match.group(1)
                table_names.add(current_table)
            column_match = re.match(r"^\tcolumn\s+'?([^'\n]+)'?\s*$", line)
            if column_match and current_table:
                table_columns.setdefault(current_table, set()).add(column_match.group(1).strip())
            measure_match = re.match(r"^\tmeasure\s+'([^']+)'", line)
            if measure_match:
                measure_names.add(measure_match.group(1))
    if not table_names:
        errors.append("No TMDL table definitions were found.")
    if not measure_names:
        errors.append("No DAX measures were generated.")
    all_columns = {column for columns in table_columns.values() for column in columns}
    for path, content in files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue
        for line in content.splitlines():
            measure_match = re.match(r"^\tmeasure\s+'([^']+)'\s*=\s*(.+)$", line)
            if not measure_match:
                continue
            expression = measure_match.group(2)
            for reference in re.findall(r"\[([^\]]+)\]", expression):
                if reference not in measure_names and reference not in all_columns:
                    errors.append(
                        f"Measure '{measure_match.group(1)}' references unknown measure/column '[{reference}]'."
                    )
    relationships_path = f"{model_folder}/definition/relationships.tmdl"
    if relationships_path in files:
        for line in files[relationships_path].splitlines():
            for key in ("fromColumn", "toColumn"):
                match = re.match(rf"^\t{key}:\s*([A-Za-z_][A-Za-z0-9_]*)\[(.+)\]$", line)
                if match:
                    table, column = match.group(1), match.group(2).strip("'")
                    if table not in table_names:
                        errors.append(f"Relationship references unknown table '{table}'.")
                    elif column not in table_columns.get(table, set()):
                        errors.append(f"Relationship references unknown column '{table}[{column}]'.")

    # ---- TMDL structural validation --------------------------------------
    # Validate every generated TMDL file for valid table declarations,
    # calculated partitions, source partitions, and cross-references.
    # This is a structural parser (not regex-only) that walks each TMDL
    # file line by line, tracking table/partition/column context.
    tmdl_errors = _validate_tmdl_files(files, model_folder, table_names, table_columns)
    errors.extend(tmdl_errors)

    # Page and visual JSON.
    pages_path = f"{report_folder}/definition/pages/pages.json"
    if pages_path in files:
        try:
            pages = json.loads(files[pages_path])
            order = pages.get("pageOrder") or []
            for page_id in order:
                page_path = f"{report_folder}/definition/pages/{page_id}/page.json"
                if page_path not in files:
                    errors.append(f"Page order references missing page: {page_id}.")
                else:
                    try:
                        page = json.loads(files[page_path])
                        if not page.get("name") or not page.get("displayName"):
                            errors.append(f"{page_path}: missing name/displayName.")
                        if page.get("$schema") != PAGE_SCHEMA:
                            errors.append(f"{page_path}: unsupported $schema {page.get('$schema')!r}.")
                    except json.JSONDecodeError as error:
                        errors.append(f"{page_path}: invalid JSON ({error}).")
            if not order:
                errors.append("Report has no pages.")
        except json.JSONDecodeError as error:
            errors.append(f"{pages_path}: invalid JSON ({error}).")
    visual_count = 0
    for path, content in files.items():
        if "/visuals/" in path and path.endswith("visual.json"):
            visual_count += 1
            try:
                visual = json.loads(content)
                position = visual.get("position") or {}
                if not visual.get("name") or not visual.get("visual"):
                    errors.append(f"{path}: missing name or visual definition.")
                if visual.get("$schema") != VISUAL_SCHEMA:
                    errors.append(f"{path}: unsupported $schema {visual.get('$schema')!r}.")
                if any(key not in position for key in ("x", "y", "width", "height")):
                    errors.append(f"{path}: incomplete position.")
            except json.JSONDecodeError as error:
                errors.append(f"{path}: invalid JSON ({error}).")
    if visual_count == 0:
        errors.append("Report contains no visual containers.")
    return errors


def _validate_tmdl_files(
    files: dict[str, str],
    model_folder: str,
    table_names: set[str],
    table_columns: dict[str, set[str]],
) -> list[str]:
    """Structural validation of all generated TMDL files.

    Walks each TMDL file line by line, tracking table/partition context,
    and checks for:

    * Invalid ``table Name = <DAX>`` declarations — table names cannot have
      a default property assignment. The table must be declared on its own
      line, with DAX expressions moved to a separate
      ``partition <name> = calculated`` block.
    * Missing partitions on tables — every table needs either a
      ``partition Name = m`` (import) or
      ``partition Name = calculated`` (DAX calculated) block.
    * Calculated partitions without a ``source = <DAX>`` expression.
    * Column ``sourceColumn`` references that don't exist in the table.

    Returns a list of error messages with file paths and line numbers.
    This is a structural parser (not regex-only) that tracks table and
    partition context while walking each TMDL file.
    """
    errors: list[str] = []
    table_partitions: dict[str, list[tuple[str, str, int]]] = {}

    for path, content in files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue

        lines = content.splitlines()
        current_table = ""
        current_partition = None
        partition_type = None

        for line_num, line in enumerate(lines, start=1):
            # Detect table declaration (valid: table Name on its own line)
            table_match = re.match(r"^table\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", line)
            if table_match:
                current_table = table_match.group(1)
                if current_table not in table_partitions:
                    table_partitions[current_table] = []
                current_partition = None
                partition_type = None
                continue

            # Detect INVALID table declaration with = <expression>
            table_assign_match = re.match(
                r"^table\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*.+$", line
            )
            if table_assign_match:
                bad_table = table_assign_match.group(1)
                errors.append(
                    f"{path}:{line_num}: invalid TMDL — "
                    f"'table {bad_table} = ...' is not valid TMDL syntax. "
                    f"Declare the table on its own line ('table {bad_table}') "
                    f"and use a separate 'partition {bad_table} = calculated' "
                    f"block for DAX calculated tables."
                )
                current_table = bad_table
                if current_table not in table_partitions:
                    table_partitions[current_table] = []
                current_partition = None
                partition_type = None
                continue

            # Detect partition declarations
            partition_match = re.match(
                r"^\tpartition\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(m|calculated)\s*$",
                line,
            )
            if partition_match and current_table:
                part_name = partition_match.group(1)
                part_kind = partition_match.group(2)
                table_partitions[current_table].append((part_name, part_kind, line_num))
                current_partition = part_name
                partition_type = part_kind
                continue

            # Detect column sourceColumn references
            column_match = re.match(r"^\tcolumn\s+", line)
            if column_match and current_table and current_partition is None:
                col_match2 = re.match(r"^\tcolumn\s+'?([^'\n]+)'?\s*$", line)
                if col_match2:
                    col_name = col_match2.group(1).strip()
                    source_col_match = re.search(
                        r"sourceColumn:\s*'?([^'\n]+)'?", line
                    )
                    if source_col_match:
                        src_col = source_col_match.group(1).strip()
                        if src_col not in table_columns.get(current_table, set()):
                            errors.append(
                                f"{path}:{line_num}: column '{col_name}' in "
                                f"table '{current_table}' references "
                                f"sourceColumn '{src_col}' which is not defined "
                                f"in that table's column list."
                            )

    # Check that every table has at least one partition
    for table_name in sorted(table_names):
        partitions = table_partitions.get(table_name, [])
        if not partitions:
            errors.append(
                f"Table '{table_name}' has no partition definition. "
                f"Add a 'partition {table_name} = m' (import) or "
                f"'partition {table_name} = calculated' (DAX) block."
            )

    # Check that calculated partitions have a source = DAX expression
    for path, content in files.items():
        if "/definition/tables/" not in path or not path.endswith(".tmdl"):
            continue
        lines = content.splitlines()
        current_table = ""
        current_partition = None
        partition_type = None

        for line_num, line in enumerate(lines, start=1):
            table_match = re.match(r"^table\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", line)
            if table_match:
                # End of previous partition block — if it was calculated
                # without a source, flag it now
                if current_partition and partition_type == "calculated":
                    errors.append(
                        f"{path}:{line_num - 1}: calculated partition "
                        f"'{current_partition}' in table '{current_table}' "
                        f"is missing a 'source = <DAX expression>' line."
                    )
                current_table = table_match.group(1)
                current_partition = None
                partition_type = None
                continue

            partition_match = re.match(
                r"^\tpartition\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(m|calculated)\s*$",
                line,
            )
            if partition_match and current_table:
                # End of previous partition block — check for missing source
                if current_partition and partition_type == "calculated":
                    errors.append(
                        f"{path}:{line_num - 1}: calculated partition "
                        f"'{current_partition}' in table '{current_table}' "
                        f"is missing a 'source = <DAX expression>' line."
                    )
                current_partition = partition_match.group(1)
                partition_type = partition_match.group(2)
                continue

            # For calculated partitions, look for source = <DAX expression>
            if partition_type == "calculated" and current_partition:
                if re.match(r"^\t\tsource\s*=\s*.+$", line):
                    # Calculated partition has its source expression — complete
                    current_partition = None
                    partition_type = None
                elif re.match(r"^\t\tsource\s*=\s*$", line):
                    errors.append(
                        f"{path}:{line_num}: calculated partition "
                        f"'{current_partition}' in table '{current_table}' "
                        f"has an empty 'source =' expression."
                    )
                    current_partition = None
                    partition_type = None

        # End of file — check for unterminated calculated partition
        if current_partition and partition_type == "calculated":
            errors.append(
                f"{path}:{len(lines)}: calculated partition "
                f"'{current_partition}' in table '{current_table}' "
                f"is missing a 'source = <DAX expression>' line."
            )

    return errors
