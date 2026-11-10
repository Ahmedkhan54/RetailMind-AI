"""AI Dashboard Assistant.

Natural-language commands are parsed into a small, explicit allowlist of
dashboard actions.  Every action is validated against the current dataset
schema before it is applied.  Destructive actions are flagged so the UI can ask
for confirmation first.

If an LLM is available it may only propose one of the allowlisted actions as
JSON; the same validation runs on that proposal.  If it is unavailable, the
rule-based parser handles the command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from retailmind.ai.nlp import (
    DIMENSION_SYNONYMS,
    METRIC_SYNONYMS,
    QueryIntent,
    _find_hint,
    resolve_dimension,
    resolve_metric,
)
from retailmind.ai.provider import AIProvider
from retailmind.config import PALETTES
from retailmind.models import Component, DashboardConfig, FilterConfig
from retailmind.schema import DatasetSchema


CHART_WORDS = {
    "bar": ("bar chart", "bar", "column chart", "columns"),
    "line": ("line chart", "line", "trend chart", "trend line"),
    "area": ("area chart", "area"),
    "pie": ("pie chart", "pie"),
    "donut": ("donut chart", "donut", "doughnut"),
    "scatter": ("scatter plot", "scatter", "correlation chart"),
    "histogram": ("histogram", "distribution chart"),
    "table": ("table", "matrix", "grid"),
}

ALLOWED_ACTIONS = {
    "add_kpi", "add_chart", "add_table", "set_theme", "set_accent", "change_chart_type",
    "move_component", "duplicate_component", "delete_component", "create_page",
    "delete_page", "rename_dashboard", "add_filter", "reset_dashboard",
}

DERIVED_KPI_ROLES = {
    "records", "margin", "orders", "customers", "aov", "growth",
    "avg_salary", "employees", "attendance_rate", "measure_sum",
}


@dataclass
class AssistantAction:
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    destructive: bool = False
    valid: bool = True
    error: str = ""
    source: str = "rule"
    suggestions: list[str] = field(default_factory=list)


def _chart_type(text: str) -> str | None:
    for chart_type, phrases in CHART_WORDS.items():
        if any(phrase in text for phrase in phrases):
            return chart_type
    return None


def _kpi_role(hint: str | None, schema: DatasetSchema, text: str) -> tuple[str | None, str | None, str]:
    if "margin" in text and schema.has("revenue") and schema.has("profit"):
        return "margin", None, "percent"
    if "average order value" in text or "aov" in text:
        return "aov", None, "currency"
    role, column = resolve_metric(schema, hint)
    if role == "revenue":
        return "revenue", column, "currency"
    if role == "profit":
        return "profit", column, "currency"
    if role == "cost":
        return "cost", column, "currency"
    if role == "salary":
        return "salary", column, "currency"
    if role == "quantity":
        return "quantity", column, "number"
    if role == "orders":
        return "orders", column, "number"
    if role == "customers":
        return "customers", column, "number"
    if role == "employees":
        return "employees", column, "number"
    if role == "attendance":
        return "attendance_rate", column, "percent"
    if role:
        return role, column, "number"
    return None, None, "number"


def _kpi_title(role: str | None, schema: DatasetSchema, fallback: str) -> str:
    mapping = {
        "revenue": "Total sales" if schema.domain in ("retail", "commerce") else "Total revenue",
        "profit": "Total profit",
        "margin": "Profit margin",
        "quantity": "Total quantity",
        "orders": "Total orders",
        "customers": "Total customers",
        "aov": "Average order value",
        "cost": "Total expenses",
        "salary": "Total salary",
        "employees": "Employee count",
        "attendance_rate": "Attendance rate",
    }
    return mapping.get(role or "", fallback)


def _page_name_from_text(text: str) -> str:
    match = re.search(r"create (?:a |an )?(.+?) (?:page|report|tab)", text)
    if match:
        name = match.group(1).strip()
    else:
        match = re.search(r"(?:add|new) (?:a |an )?(.+?) (?:page|report|tab)", text)
        name = match.group(1).strip() if match else ""
    if not name:
        if "customer" in text:
            name = "Customer Analysis"
        elif "profit" in text:
            name = "Profit Analysis"
        elif "sales" in text or "revenue" in text:
            name = "Sales Analysis"
        elif "product" in text:
            name = "Product Analysis"
        else:
            name = "Custom Report"
    return " ".join(part.capitalize() for part in name.split())[:60]


def _find_chartlike(config: DashboardConfig, text: str) -> Component | None:
    needle = text.strip().lower()
    for page in config.pages:
        for component in page.components:
            if component.type in ("kpi", "insights", "profile_table", "missing_bar"):
                continue
            if needle and (needle in component.title.lower() or needle in (component.measure or "").lower() or needle in (component.dimension or "").lower()):
                return component
    return config.find_chart()


def parse_command(
    command: str,
    config: DashboardConfig,
    schema: DatasetSchema,
    selected_component_id: str | None = None,
) -> AssistantAction:
    """Parse a natural-language dashboard command into one validated action."""
    text = (command or "").strip().lower()
    if not text:
        return AssistantAction("unknown", valid=False, error="Enter a dashboard command.", suggestions=_suggestions())

    selected = config.component(selected_component_id) if selected_component_id else None

    # ---- theme --------------------------------------------------------
    if "theme" in text and any(preset in text for preset in ("dark", "light", "midnight", "corporate")):
        preset = next(preset for preset in ("dark", "light", "midnight", "corporate") if preset in text)
        return AssistantAction("set_theme", {"preset": preset}, f"Switch the dashboard theme to {preset}.", source="rule")
    accent_match = re.search(r"(?:accent|colour|color)\s*(?:to|:)?\s*(#[0-9a-f]{6})", text)
    if accent_match:
        return AssistantAction("set_accent", {"accent": accent_match.group(1)}, f"Set the accent colour to {accent_match.group(1)}.", source="rule")

    # ---- reset / delete / destructive ---------------------------------
    if "reset" in text and ("dashboard" in text or "layout" in text):
        return AssistantAction("reset_dashboard", {}, "Reset the dashboard to its originally generated layout.", destructive=True)
    if ("delete" in text or "remove" in text) and "page" in text:
        page_match = re.search(r"(?:delete|remove)\s+(?:the\s+)?(.+?)\s+page", text)
        page_name = page_match.group(1).strip().title() if page_match else ""
        if page_name:
            return AssistantAction("delete_page", {"page": page_name}, f"Delete the '{page_name}' page.", destructive=True)
    if "delete" in text or "remove" in text:
        target = selected
        if target is None:
            cleaned = re.sub(r"^(?:delete|remove)\s+(?:the\s+)?", "", text).replace(" chart", "").replace(" visual", "").strip()
            target = _find_chartlike(config, cleaned)
        if target is None:
            return AssistantAction("unknown", valid=False, error="Select a visual or name the visual to delete.", suggestions=_suggestions())
        return AssistantAction("delete_component", {"component_id": target.id}, f"Delete '{target.title}'.", destructive=True)

    # ---- duplicate ----------------------------------------------------
    if "duplicate" in text or "copy" in text:
        target = selected or _find_chartlike(config, text.replace("duplicate", "").replace("copy", ""))
        if target:
            return AssistantAction("duplicate_component", {"component_id": target.id}, f"Duplicate '{target.title}'.", source="rule")

    # ---- move ---------------------------------------------------------
    if text.startswith("move") or " move " in text or "move the" in text:
        target = selected
        if target is None:
            cleaned = re.sub(r"^move\s+(?:the\s+)?", "", text)
            cleaned = cleaned.split(" to ")[0].strip().replace(" chart", "").replace(" visual", "")
            target = _find_chartlike(config, cleaned)
        if target is None:
            return AssistantAction("unknown", valid=False, error="I could not identify which visual to move.", suggestions=_suggestions())
        if "top" in text:
            return AssistantAction("move_component", {"component_id": target.id, "position": "top"}, f"Move '{target.title}' to the top.", source="rule")
        if "bottom" in text:
            return AssistantAction("move_component", {"component_id": target.id, "position": "bottom"}, f"Move '{target.title}' to the bottom.", source="rule")

    # ---- change chart type -------------------------------------------
    if ("change" in text or "convert" in text or "turn" in text) and any(phrase in text for phrases in CHART_WORDS.values() for phrase in phrases):
        new_type = _chart_type(text)
        target = selected
        if target is None:
            cleaned = re.sub(r"(change|convert|turn)", "", text)
            cleaned = re.sub(r"(into|to)\s+(?:a\s+)?(?:bar|line|area|pie|donut|doughnut|scatter|histogram|table|matrix).*", "", cleaned).strip()
            target = _find_chartlike(config, cleaned) if cleaned else config.find_chart()
        if target is None:
            target = config.find_chart()
        if target is None or new_type is None:
            return AssistantAction("unknown", valid=False, error="Select a chart first, then ask to change its type.", suggestions=_suggestions())
        return AssistantAction("change_chart_type", {"component_id": target.id, "chart_type": new_type}, f"Change '{target.title}' to a {new_type} chart.", source="rule")

    # ---- pages --------------------------------------------------------
    if "page" in text or "report page" in text:
        if any(word in text for word in ("create", "add", "new", "make")):
            name = _page_name_from_text(text)
            return AssistantAction("create_page", {"name": name}, f"Create the '{name}' page.", source="rule")

    # ---- filters ------------------------------------------------------
    if "filter" in text:
        if "date" in text or "time" in text:
            column = schema.role_column("date")
            if not column:
                return AssistantAction("unknown", valid=False, error="This dataset has no date column to filter.", suggestions=_suggestions())
            return AssistantAction("add_filter", {"column": column, "kind": "date"}, "Add a date filter.", source="rule")
        hint = _find_hint(text, DIMENSION_SYNONYMS)
        role, column = resolve_dimension(schema, hint, text) if hint else (None, None)
        if column:
            return AssistantAction("add_filter", {"column": column, "kind": "category"}, f"Add a {schema.label_for(column)} filter.", source="rule")

    # ---- KPI ----------------------------------------------------------
    if "kpi" in text or "card" in text or "metric" in text:
        hint = _find_hint(text, METRIC_SYNONYMS)
        role, column, fmt = _kpi_role(hint, schema, text)
        if role is None:
            return AssistantAction("unknown", valid=False, error="I could not match that KPI to an uploaded column.", suggestions=_suggestions())
        title = _kpi_title(role, schema, column or "KPI")
        return AssistantAction("add_kpi", {"role": role, "measure": column, "title": title, "format": fmt}, f"Add the '{title}' KPI card.", source="rule")

    # ---- table --------------------------------------------------------
    if _chart_type(text) == "table":
        hint = _find_hint(text, DIMENSION_SYNONYMS)
        dim_role, dim_column = resolve_dimension(schema, hint, text) if hint else (None, None)
        metric_hint = _find_hint(text, METRIC_SYNONYMS)
        metric_role, metric_column = resolve_metric(schema, metric_hint)
        if not dim_column:
            return AssistantAction("unknown", valid=False, error="A grouping column is required for a table.", suggestions=_suggestions())
        title = f"{schema.label_for(dim_column)} table"
        return AssistantAction("add_table", {"dimension": dim_column, "measure": metric_column, "title": title}, f"Add a table grouped by {schema.label_for(dim_column)}.", source="rule")

    # ---- add chart ----------------------------------------------------
    chart_type = _chart_type(text) or "bar"
    if any(word in text for word in ("add", "create", "show", "make", "plot", "display", "chart", "top")):
        # Reuse the NLP parser for entity extraction.
        from retailmind.ai.nlp import parse_question

        intent = parse_question(command, schema)
        hint = _find_hint(text, DIMENSION_SYNONYMS)
        dim_role, dim_column = resolve_dimension(schema, hint, text) if hint else (intent.dimension_role, intent.dimension_column)
        metric_hint = _find_hint(text, METRIC_SYNONYMS)
        metric_role, metric_column = resolve_metric(schema, metric_hint)
        if metric_column is None:
            metric_role, metric_column = intent.metric_role, intent.metric_column
        if dim_column is None:
            dim_column = intent.dimension_column
        if metric_column is None:
            metric_column = schema.role_column("revenue") or schema.role_column("profit") or (schema.measures[0] if schema.measures else None)
        if dim_column is None and metric_column:
            dim_column = next((schema.role_column(role) for role in ("category", "product", "region", "city", "department") if schema.role_column(role)), None)
        if dim_column is None and metric_column is None:
            return AssistantAction("unknown", valid=False, error="I need at least one column to build that visual.", suggestions=_suggestions())
        if chart_type in ("line", "area") and not (dim_column and dim_column in schema.dates):
            # A trend needs a date; fall back to the date column when possible.
            dim_column = schema.role_column("date") or dim_column
        top_n = intent.top_n or 10
        title = f"{schema.label_for(metric_column) if metric_column else 'Records'} by {schema.label_for(dim_column) if dim_column else 'records'}"
        if intent.top_n:
            title = f"Top {top_n} {schema.label_for(dim_column).lower() if dim_column else 'records'} by {schema.label_for(metric_column).lower() if metric_column else 'records'}"
        return AssistantAction(
            "add_chart",
            {"chart_type": chart_type, "dimension": dim_column, "measure": metric_column, "aggregation": "sum", "top_n": top_n, "title": title},
            f"Add a {chart_type} chart: {title}.",
            source="rule",
        )

    # ---- optional LLM fallback ---------------------------------------
    return AssistantAction("unknown", valid=False, error="I did not understand that command.", suggestions=_suggestions())


def apply_action(
    config: DashboardConfig,
    action: AssistantAction,
    schema: DatasetSchema,
    active_page: str | None = None,
) -> tuple[DashboardConfig, str]:
    """Apply a validated action to the configuration and return a message."""
    if not action.valid:
        return config, action.error or "That action is not valid."

    page_name = active_page or (config.pages[0].name if config.pages else "Overview")
    page = config.page(page_name) or config.add_page(page_name)

    if action.action == "add_kpi":
        role = action.params.get("role")
        measure = action.params.get("measure")
        if measure and measure not in schema.columns:
            return config, f"Column '{measure}' is not present in the dataset."
        if role and role not in DERIVED_KPI_ROLES and role not in schema.roles:
            return config, f"The '{role}' role is not mapped in the current dataset."
        title = action.params.get("title") or _kpi_title(role, schema, "KPI")
        component = Component(type="kpi", title=title, kpi_role=role, measure=measure, format=action.params.get("format", "number"), width=3, height=180)
        page.add(component)
        return config, f"Added the '{title}' KPI to {page.name}."

    if action.action in ("add_chart", "add_table"):
        chart_type = action.params.get("chart_type") or ("table" if action.action == "add_table" else "bar")
        dimension = action.params.get("dimension")
        measure = action.params.get("measure")
        if dimension and dimension not in schema.columns:
            return config, f"Column '{dimension}' is not present in the dataset."
        if measure and measure not in schema.columns:
            return config, f"Column '{measure}' is not present in the dataset."
        if dimension is None and measure is None:
            return config, "A chart needs at least one dataset column."
        component = Component(
            type=chart_type,
            title=action.params.get("title") or "Custom visual",
            dimension=dimension,
            measure=measure,
            aggregation=action.params.get("aggregation", "sum"),
            top_n=max(1, min(int(action.params.get("top_n", 10)), 100)),
            width=6 if chart_type != "table" else 12,
            height=340,
        )
        page.add(component)
        return config, f"Added '{component.title}' to {page.name}."

    if action.action == "set_theme":
        preset = action.params.get("preset", "dark")
        config.theme.preset = preset
        config.theme.palette = list(PALETTES.get(preset, PALETTES["dark"]))
        if preset == "light":
            config.theme.accent = config.theme.palette[0]
        return config, f"Theme changed to {preset}."

    if action.action == "set_accent":
        accent = action.params.get("accent")
        if not accent or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
            return config, "Accent colour must be a hex value such as #7c5cff."
        config.theme.accent = accent
        return config, f"Accent colour changed to {accent}."

    if action.action == "change_chart_type":
        component = config.component(action.params.get("component_id", ""))
        if component is None:
            return config, "The selected visual no longer exists."
        new_type = action.params.get("chart_type")
        if new_type not in {"bar", "line", "area", "pie", "donut", "scatter", "histogram", "table", "matrix"}:
            return config, "Unsupported chart type."
        component.type = new_type
        if new_type in ("line", "area") and schema.has("date"):
            component.dimension = schema.role_column("date")
        return config, f"'{component.title}' is now a {new_type} visual."

    if action.action == "move_component":
        component = config.component(action.params.get("component_id", ""))
        if component is None:
            return config, "The selected visual no longer exists."
        owner = config.page(component.page)
        if owner is None:
            return config, "The visual's page no longer exists."
        if action.params.get("position") == "bottom":
            moved = owner.move(component.id, 10_000)
        else:
            moved = owner.move_to_top(component.id)
        if not moved:
            return config, f"'{component.title}' is already at the {action.params.get('position', 'top')}."
        return config, f"Moved '{component.title}' to the {action.params.get('position', 'top')}."

    if action.action == "duplicate_component":
        component = config.component(action.params.get("component_id", ""))
        if component is None:
            return config, "The selected visual no longer exists."
        owner = config.page(component.page)
        clone = owner.duplicate(component.id) if owner else None
        return config, f"Duplicated '{clone.title}'." if clone else "Could not duplicate that visual."

    if action.action == "delete_component":
        component = config.component(action.params.get("component_id", ""))
        if component is None:
            return config, "The selected visual no longer exists."
        owner = config.page(component.page)
        if owner and owner.remove(component.id):
            return config, f"Deleted '{component.title}'."
        return config, "Could not delete that visual."

    if action.action == "create_page":
        name = action.params.get("name") or "Custom Report"
        if config.page(name):
            return config, f"The '{name}' page already exists."
        page = config.add_page(name)
        # Populate the new page with relevant, validated components.
        if "customer" in name.lower() and schema.has("customer"):
            measure = schema.role_column("revenue") or (schema.measures[0] if schema.measures else None)
            page.add(Component(type="bar", title="Top customers", dimension=schema.role_column("customer"), measure=measure, top_n=15))
            page.add(Component(type="table", title="Customer value table", dimension=schema.role_column("customer"), measure=measure, width=12))
        elif "profit" in name.lower() and schema.has("profit"):
            page.add(Component(type="bar", title="Profit by category", dimension=schema.role_column("category"), measure=schema.role_column("profit")))
            page.add(Component(type="line", title="Profit trend", dimension=schema.role_column("date"), measure=schema.role_column("profit"), width=12))
        else:
            measure = schema.role_column("revenue") or (schema.measures[0] if schema.measures else None)
            dimension = next((schema.role_column(role) for role in ("category", "product", "region", "city") if schema.role_column(role)), None)
            page.add(Component(type="bar", title="Custom analysis", dimension=dimension, measure=measure))
        return config, f"Created the '{name}' page with {len(page.components)} visual(s)."

    if action.action == "delete_page":
        name = action.params.get("page", "")
        existing = config.page(name)
        if existing is None:
            existing = next((page for page in config.pages if page.name.lower() == name.lower()), None)
        target_name = existing.name if existing else name
        if config.remove_page(target_name):
            return config, f"Deleted the '{target_name}' page."
        return config, f"Could not delete '{target_name}'. At least one page must remain."

    if action.action == "rename_dashboard":
        name = action.params.get("name", "").strip()
        if not name:
            return config, "Provide a new dashboard name."
        config.name = name[:120]
        return config, f"Dashboard renamed to '{config.name}'."

    if action.action == "add_filter":
        column = action.params.get("column")
        if not column or column not in schema.columns:
            return config, "That filter column is not present in the dataset."
        kind = action.params.get("kind", "category")
        if any(filter_.column == column for filter_ in config.filters):
            return config, f"A {schema.label_for(column)} filter is already configured."
        config.filters.append(FilterConfig(column=column, kind=kind))
        return config, f"Added a {schema.label_for(column)} filter to the dashboard configuration."

    if action.action == "reset_dashboard":
        return config, "Confirmation required."

    return config, "That action is not supported."


def parse_with_llm(
    command: str,
    config: DashboardConfig,
    schema: DatasetSchema,
    provider: AIProvider,
    selected_component_id: str | None = None,
) -> AssistantAction | None:
    """Ask an LLM for one allowlisted action, then validate it strictly."""
    if provider is None or not provider.available:
        return None
    columns = "\n".join(
        f"- {column} (role: {', '.join(role for role, mapped in schema.roles.items() if mapped == column) or 'none'})"
        for column in schema.columns
    )
    components = "\n".join(
        f"- {component.id}: {component.title} ({component.type}) on {component.page}"
        for page in config.pages for component in page.components
    ) or "(none)"
    prompt = (
        "You convert a dashboard command into ONE JSON object. "
        "Allowed actions: add_kpi, add_chart, add_table, set_theme, change_chart_type, move_component, "
        "duplicate_component, delete_component, create_page, delete_page, rename_dashboard, add_filter.\n"
        "Use only columns from this dataset:\n" + columns + "\n"
        "Existing visuals:\n" + components + "\n"
        f"Selected visual id: {selected_component_id or 'none'}\n"
        "Return JSON with keys: action, params, description. "
        "Never invent column names. For destructive actions set destructive=true."
    )
    payload = provider.json_chat(
        [
            {"role": "system", "content": "You are a strict dashboard action planner. Output JSON only."},
            {"role": "user", "content": prompt + f"\n\nCommand: {command}"},
        ]
    )
    if not payload:
        return None
    action_name = str(payload.get("action") or "")
    if action_name not in ALLOWED_ACTIONS:
        return None
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    # Validate every referenced column.
    for key in ("dimension", "measure", "column"):
        value = params.get(key)
        if value and value not in schema.columns:
            return None
    if action_name in ("change_chart_type", "move_component", "duplicate_component", "delete_component"):
        component_id = params.get("component_id")
        if component_id and config.component(str(component_id)) is None:
            return None
    return AssistantAction(
        action=action_name,
        params=params,
        description=str(payload.get("description") or f"AI proposed {action_name}."),
        destructive=bool(payload.get("destructive")) or action_name in ("delete_component", "delete_page"),
        valid=True,
        source="llm",
    )


def _suggestions() -> list[str]:
    return [
        "Add a total profit KPI",
        "Create a sales bar chart",
        "Show the top 10 products by revenue",
        "Change this bar chart into a pie chart",
        "Create a customer analysis page",
        "Change the dashboard theme to light",
    ]
