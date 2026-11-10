"""Serializable dashboard configuration models.

A dashboard stores *definitions only* (column names, aggregations, layout,
titles, colours).  The uploaded dataset is never embedded in a saved layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import uuid
from typing import Any


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Component:
    """One visual on a dashboard page."""

    id: str = field(default_factory=_new_id)
    type: str = "bar"  # kpi | bar | line | area | pie | donut | scatter | histogram | table | matrix | insights | profile_table | missing_bar
    title: str = ""
    page: str = "Overview"
    dimension: str | None = None
    measure: str | None = None
    measure_y: str | None = None
    aggregation: str = "sum"
    top_n: int = 10
    sort: str = "desc"
    color: str | None = None
    width: int = 6  # 1..12 grid span
    height: int = 320
    kpi_role: str | None = None
    format: str | None = None  # currency | number | percent
    description: str = ""
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Component":
        allowed = {field_.name for field_ in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        clean = {key: value for key, value in (payload or {}).items() if key in allowed}
        component = cls(**clean)
        component.type = str(component.type or "bar")
        component.aggregation = str(component.aggregation or "sum").lower()
        component.top_n = max(1, min(int(component.top_n or 10), 100))
        component.width = max(1, min(int(component.width or 6), 12))
        component.height = max(180, min(int(component.height or 320), 900))
        return component


@dataclass
class Page:
    name: str = "Overview"
    description: str = ""
    components: list[Component] = field(default_factory=list)
    order: int = 0

    def add(self, component: Component) -> Component:
        component.page = self.name
        component.order = len(self.components)
        self.components.append(component)
        return component

    def remove(self, component_id: str) -> bool:
        before = len(self.components)
        self.components = [component for component in self.components if component.id != component_id]
        self._reindex()
        return len(self.components) != before

    def get(self, component_id: str) -> Component | None:
        return next((component for component in self.components if component.id == component_id), None)

    def move(self, component_id: str, offset: int) -> bool:
        index = next((i for i, c in enumerate(self.components) if c.id == component_id), None)
        if index is None:
            return False
        target = max(0, min(index + offset, len(self.components) - 1))
        if target == index:
            return False
        self.components.insert(target, self.components.pop(index))
        self._reindex()
        return True

    def move_to_top(self, component_id: str) -> bool:
        return self.move(component_id, -10_000)

    def duplicate(self, component_id: str) -> Component | None:
        source = self.get(component_id)
        if source is None:
            return None
        clone = Component.from_dict(source.to_dict())
        clone.id = _new_id()
        clone.title = f"{source.title} (copy)"
        self.add(clone)
        return clone

    def _reindex(self) -> None:
        for index, component in enumerate(self.components):
            component.order = index

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "order": self.order,
            "components": [component.to_dict() for component in self.components],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Page":
        payload = payload or {}
        page = cls(
            name=str(payload.get("name") or "Overview"),
            description=str(payload.get("description") or ""),
            order=int(payload.get("order") or 0),
        )
        for item in payload.get("components") or []:
            page.add(Component.from_dict(item))
        return page


@dataclass
class Theme:
    preset: str = "dark"
    accent: str = "#7c5cff"
    font: str = "Inter, Segoe UI, sans-serif"
    palette: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Theme":
        payload = payload or {}
        return cls(
            preset=str(payload.get("preset") or "dark"),
            accent=str(payload.get("accent") or "#7c5cff"),
            font=str(payload.get("font") or "Inter, Segoe UI, sans-serif"),
            palette=list(payload.get("palette") or []),
        )


@dataclass
class FilterConfig:
    column: str
    kind: str  # date | category | numeric
    selected: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FilterConfig":
        return cls(
            column=str(payload.get("column") or ""),
            kind=str(payload.get("kind") or "category"),
            selected=payload.get("selected"),
        )


@dataclass
class DashboardConfig:
    id: str = field(default_factory=_new_id)
    name: str = "RetailMind Dashboard"
    dataset_id: str = ""
    dataset_name: str = ""
    domain: str = "generic"
    pages: list[Page] = field(default_factory=list)
    theme: Theme = field(default_factory=Theme)
    filters: list[FilterConfig] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    version: int = 1
    mode: str = "auto"  # auto | custom

    # ---- page helpers -------------------------------------------------
    def page(self, name: str) -> Page | None:
        return next((page for page in self.pages if page.name == name), None)

    def page_names(self) -> list[str]:
        return [page.name for page in self.pages]

    def add_page(self, name: str, description: str = "") -> Page:
        existing = self.page(name)
        if existing is not None:
            return existing
        page = Page(name=name, description=description, order=len(self.pages))
        self.pages.append(page)
        return page

    def remove_page(self, name: str) -> bool:
        if len(self.pages) <= 1:
            return False
        before = len(self.pages)
        self.pages = [page for page in self.pages if page.name != name]
        for index, page in enumerate(self.pages):
            page.order = index
        return len(self.pages) != before

    def rename_page(self, old: str, new: str) -> bool:
        new = new.strip()
        if not new or old == new or self.page(new) is not None:
            return False
        page = self.page(old)
        if page is None:
            return False
        page.name = new
        for component in page.components:
            component.page = new
        return True

    def move_page(self, name: str, offset: int) -> bool:
        index = next((i for i, page in enumerate(self.pages) if page.name == name), None)
        if index is None:
            return False
        target = max(0, min(index + offset, len(self.pages) - 1))
        if target == index:
            return False
        self.pages.insert(target, self.pages.pop(index))
        for order, page in enumerate(self.pages):
            page.order = order
        return True

    def duplicate_page(self, name: str) -> Page | None:
        source = self.page(name)
        if source is None:
            return None
        clone = Page(name=f"{name} copy", description=source.description, order=len(self.pages))
        for component in source.components:
            copied = Component.from_dict(component.to_dict())
            copied.id = _new_id()
            clone.add(copied)
        self.pages.append(clone)
        return clone

    def component(self, component_id: str) -> Component | None:
        for page in self.pages:
            found = page.get(component_id)
            if found is not None:
                return found
        return None

    def find_component(self, text: str) -> Component | None:
        """Find a component by a fuzzy title match (used by the AI assistant)."""
        needle = text.strip().lower()
        if not needle:
            return None
        for page in self.pages:
            for component in page.components:
                if needle in component.title.lower() or needle in component.id.lower():
                    return component
        return None

    def find_chart(self) -> Component | None:
        for page in self.pages:
            for component in reversed(page.components):
                if component.type in ("bar", "line", "area", "pie", "donut", "scatter", "histogram"):
                    return component
        return None

    def counts(self) -> dict[str, int]:
        return {
            "pages": len(self.pages),
            "components": sum(len(page.components) for page in self.pages),
            "kpis": sum(1 for page in self.pages for c in page.components if c.type == "kpi"),
            "charts": sum(1 for page in self.pages for c in page.components if c.type in ("bar", "line", "area", "pie", "donut", "scatter", "histogram")),
        }

    # ---- serialization ------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "domain": self.domain,
            "pages": [page.to_dict() for page in self.pages],
            "theme": self.theme.to_dict(),
            "filters": [filter_.to_dict() for filter_ in self.filters],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DashboardConfig":
        payload = payload or {}
        config = cls(
            id=str(payload.get("id") or _new_id()),
            name=str(payload.get("name") or "RetailMind Dashboard"),
            dataset_id=str(payload.get("dataset_id") or ""),
            dataset_name=str(payload.get("dataset_name") or ""),
            domain=str(payload.get("domain") or "generic"),
            theme=Theme.from_dict(payload.get("theme") or {}),
            created_at=str(payload.get("created_at") or _utcnow()),
            updated_at=str(payload.get("updated_at") or _utcnow()),
            version=int(payload.get("version") or 1),
            mode=str(payload.get("mode") or "auto"),
        )
        for item in payload.get("pages") or []:
            config.pages.append(Page.from_dict(item))
        if not config.pages:
            config.pages.append(Page(name="Overview"))
        config.filters = [FilterConfig.from_dict(item) for item in payload.get("filters") or []]
        return config

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, default=str)

    @classmethod
    def from_json(cls, text: str) -> "DashboardConfig":
        return cls.from_dict(json.loads(text))

    def clone(self) -> "DashboardConfig":
        clone = DashboardConfig.from_dict(self.to_dict())
        clone.id = _new_id()
        clone.name = f"{self.name} (copy)"
        clone.created_at = _utcnow()
        for page in clone.pages:
            for component in page.components:
                component.id = _new_id()
        return clone

    def touch(self) -> None:
        self.updated_at = _utcnow()
        self.version += 1
