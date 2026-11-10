"""Universal dataset profiling and semantic role detection.

The goal is to understand *any* structured business dataset, not only retail
sales.  Detection is deliberately explainable: every detected role records the
column and a confidence score, and users can override any mapping manually.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from data_sources import normalise_name, profile_schema


# Strong aliases are unambiguous.  Weak aliases ("amount", "total", "value")
# only become revenue when the dataset has other commercial context.
ROLE_ALIASES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "revenue": (
        ("revenue", "sales", "net sales", "gross sales", "turnover", "total revenue", "total sales", "sales amount", "sales value", "billed amount"),
        ("amount", "total", "value", "income", "billing", "cart value", "order value", "basket value", "gmv"),
    ),
    "profit": (
        ("profit", "net profit", "gross profit", "profit amount", "earnings", "net income", "operating profit"),
        ("margin", "margin amount", "p l"),
    ),
    "cost": (
        ("cost", "expenses", "expense", "total cost", "total expenses", "cogs", "cost of goods sold", "spend"),
        ("expenditure", "overhead"),
    ),
    "quantity": (
        ("quantity", "qty", "units", "units sold", "unit quantity", "volume", "pieces", "items", "item count"),
        ("count", "number of units"),
    ),
    "unit_price": (
        ("unit price", "price per unit", "price", "rate", "selling price", "mrp"),
        ("unit cost",),
    ),
    "discount": (
        ("discount", "discount pct", "discount percent", "discount percentage", "discount rate", "markdown"),
        ("rebate",),
    ),
    "order_id": (
        ("order id", "order number", "invoice id", "invoice number", "transaction id", "bill id", "receipt id", "order no"),
        ("reference", "transaction", "invoice"),
    ),
    "date": (
        ("order date", "sales date", "invoice date", "transaction date", "purchase date", "created at", "date", "timestamp", "period", "month", "year", "day"),
        ("time", "week", "quarter"),
    ),
    "product": (
        ("product name", "product", "item name", "item", "sku", "sku name", "goods", "article", "service"),
        ("description", "title"),
    ),
    "category": (
        ("category", "product category", "item category", "sub category", "subcategory", "segment", "type", "class",
         "product type", "item type", "product segment", "product group"),
        ("group", "family"),
    ),
    "department": (
        ("department", "dept", "division", "business unit", "team"),
        ("function",),
    ),
    "customer": (
        ("customer id", "customer name", "customer", "client id", "client name", "client", "buyer", "account name", "account id",
         "user id", "user", "buyer id", "shopper", "shopper id"),
        ("account", "consumer"),
    ),
    "region": (
        ("region", "area", "zone", "territory", "state", "province", "country"),
        ("location", "geo"),
    ),
    "city": (
        ("city", "town", "store city", "location", "branch city"),
        ("place",),
    ),
    "store": (
        ("store", "store name", "branch", "outlet", "shop", "location name"),
        ("site", "facility"),
    ),
    "sales_rep": (
        ("sales rep", "sales representative", "salesperson", "representative", "account manager", "agent"),
        ("owner", "executive"),
    ),
    "payment_method": (
        ("payment method", "payment type", "payment", "payment mode", "tender"),
        ("method",),
    ),
    "employee_id": (
        ("employee id", "employee number", "staff id", "employee code", "emp id"),
        ("staff", "employee", "worker"),
    ),
    "employee_name": (
        ("employee name", "staff name", "worker name", "name"),
        ("person",),
    ),
    "salary": (
        ("salary", "base salary", "monthly salary", "annual salary", "wage", "wages", "compensation", "pay", "hourly rate"),
        ("remuneration", "stipend"),
    ),
    "attendance": (
        ("attendance", "attendance status", "present", "absent", "attendance rate", "attendance percentage"),
        ("status", "presence"),
    ),
    "student_id": (
        ("student id", "student number", "roll number", "enrollment id"),
        ("student", "learner"),
    ),
    "student_name": (
        ("student name", "learner name"),
        ("pupil",),
    ),
    "course": (
        ("course", "course name", "subject", "program", "programme", "class"),
        ("module",),
    ),
    "grade": (
        ("grade", "marks", "score", "result", "percentage", "gpa", "cgpa"),
        ("rating", "performance"),
    ),
    "gender": (("gender", "sex"), ()),
    "age": (("age", "years"), ()),
}

ROLE_LABELS = {
    "revenue": "Revenue",
    "profit": "Profit",
    "cost": "Expenses",
    "quantity": "Quantity",
    "unit_price": "Unit price",
    "discount": "Discount",
    "order_id": "Order",
    "date": "Date",
    "product": "Product",
    "category": "Category",
    "department": "Department",
    "customer": "Customer",
    "region": "Region",
    "city": "City",
    "store": "Store",
    "sales_rep": "Sales representative",
    "payment_method": "Payment method",
    "employee_id": "Employee",
    "employee_name": "Employee name",
    "salary": "Salary",
    "attendance": "Attendance",
    "student_id": "Student",
    "student_name": "Student name",
    "course": "Course",
    "grade": "Grade",
    "gender": "Gender",
    "age": "Age",
}

MEASURE_ROLES = {"revenue", "profit", "cost", "quantity", "unit_price", "discount", "salary", "grade", "age"}
DIMENSION_ROLES = {"product", "category", "department", "customer", "region", "city", "store", "sales_rep", "payment_method", "employee_name", "course", "gender", "attendance"}
IDENTIFIER_ROLES = {"order_id", "employee_id", "student_id"}


@dataclass
class DatasetSchema:
    columns: list[str]
    dtypes: dict[str, str]
    numeric: list[str]
    categorical: list[str]
    dates: list[str]
    identifiers: list[str]
    boolean: list[str]
    roles: dict[str, str] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    candidates: dict[str, list[str]] = field(default_factory=dict)
    domain: str = "generic"
    domain_label: str = "General business"
    warnings: list[str] = field(default_factory=list)

    # ---- convenience --------------------------------------------------
    @property
    def measures(self) -> list[str]:
        seen: list[str] = []
        for role in ("revenue", "profit", "cost", "quantity", "unit_price", "salary", "grade", "age", "discount"):
            column = self.roles.get(role)
            if column and column in self.columns and column not in seen:
                seen.append(column)
        for column in self.numeric:
            if column not in seen and column not in self.identifiers:
                seen.append(column)
        return seen

    @property
    def dimensions(self) -> list[str]:
        seen: list[str] = []
        for role in ("product", "category", "department", "customer", "region", "city", "store", "sales_rep", "payment_method", "employee_name", "course", "gender", "attendance"):
            column = self.roles.get(role)
            if column and column in self.columns and column not in seen:
                seen.append(column)
        for column in self.categorical:
            if column not in seen:
                seen.append(column)
        return seen

    def role_column(self, role: str) -> str | None:
        column = self.roles.get(role)
        return column if column in self.columns else None

    def label_for(self, column: str | None) -> str:
        if not column:
            return ""
        for role, mapped in self.roles.items():
            if mapped == column:
                return ROLE_LABELS.get(role, column.replace("_", " ").title())
        return str(column).replace("_", " ").title()

    def has(self, role: str) -> bool:
        return bool(self.role_column(role))

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": list(self.columns),
            "dtypes": dict(self.dtypes),
            "numeric": list(self.numeric),
            "categorical": list(self.categorical),
            "dates": list(self.dates),
            "identifiers": list(self.identifiers),
            "boolean": list(self.boolean),
            "roles": dict(self.roles),
            "confidence": dict(self.confidence),
            "candidates": {key: list(value) for key, value in self.candidates.items()},
            "domain": self.domain,
            "domain_label": self.domain_label,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DatasetSchema":
        payload = payload or {}
        return cls(
            columns=list(payload.get("columns") or []),
            dtypes=dict(payload.get("dtypes") or {}),
            numeric=list(payload.get("numeric") or []),
            categorical=list(payload.get("categorical") or []),
            dates=list(payload.get("dates") or []),
            identifiers=list(payload.get("identifiers") or []),
            boolean=list(payload.get("boolean") or []),
            roles=dict(payload.get("roles") or {}),
            confidence=dict(payload.get("confidence") or {}),
            candidates={key: list(value) for key, value in (payload.get("candidates") or {}).items()},
            domain=str(payload.get("domain") or "generic"),
            domain_label=str(payload.get("domain_label") or "General business"),
            warnings=list(payload.get("warnings") or []),
        )


def _score_alias(column: str, aliases: tuple[str, ...], weak: tuple[str, ...]) -> tuple[float, str]:
    normalised = normalise_name(column)
    tokens = set(normalised.split())
    for alias in aliases:
        if normalised == normalise_name(alias):
            return 1.0, "exact"
    for alias in aliases:
        alias_tokens = set(normalise_name(alias).split())
        if alias_tokens and alias_tokens.issubset(tokens):
            return 0.86, "token"
    for alias in aliases:
        if normalise_name(alias) in normalised:
            return 0.72, "contains"
    for alias in weak:
        if normalised == normalise_name(alias):
            return 0.48, "weak-exact"
    for alias in weak:
        if normalise_name(alias) in normalised:
            return 0.38, "weak-contains"
    return 0.0, ""


def _looks_like_date(values: pd.Series, name: str) -> bool:
    normalised = normalise_name(name)
    non_null = values.dropna()
    if non_null.empty:
        return False
    if pd.api.types.is_datetime64_any_dtype(values):
        return True
    if pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values):
        # Numeric columns are measures; do not spend time parsing them as dates.
        return False
    named = any(token in normalised for token in ("date", "time", "month", "year", "day", "period", "week", "quarter"))
    sample = non_null.astype("string").head(200)
    parsed = pd.to_datetime(sample, format="mixed", errors="coerce")
    ratio = float(parsed.notna().mean())
    if named and ratio >= 0.6:
        return True
    # A high parse rate with a 4-digit year pattern is a strong signal.
    if ratio >= 0.9 and sample.str.contains(r"\b(?:19|20)\d{2}\b", regex=True).mean() >= 0.8:
        return True
    return False


def _role_dtype_ok(role: str, column: str, numeric: set[str], dates: set[str], categorical: set[str]) -> bool:
    if role in MEASURE_ROLES:
        return column in numeric
    if role == "date":
        return column in dates
    if role in ("order_id", "employee_id", "student_id"):
        return True
    return column in categorical or column in dates or column in numeric


def infer_schema(frame: pd.DataFrame) -> DatasetSchema:
    """Infer dtypes, roles, dimensions, measures and a likely business domain."""
    base = profile_schema(frame)
    numeric = list(base["numeric_columns"])
    categorical = list(base["categorical_columns"])
    identifiers = list(base["identifier_columns"])
    boolean: list[str] = []
    dates: list[str] = []

    for column in frame.columns:
        values = frame[column]
        if pd.api.types.is_bool_dtype(values):
            boolean.append(str(column))
            continue
        if _looks_like_date(values, str(column)):
            dates.append(str(column))
    dates = list(dict.fromkeys(dates + list(base["date_columns"])))

    # Numeric-looking columns that profile_schema missed (heavy missingness).
    for column in frame.columns:
        if str(column) in numeric or str(column) in dates:
            continue
        non_null = frame[column].dropna()
        if non_null.empty:
            continue
        sample = non_null.iloc[:5000] if len(non_null) > 5000 else non_null
        converted = pd.to_numeric(sample, errors="coerce")
        if converted.notna().mean() >= 0.78 and not pd.api.types.is_bool_dtype(frame[column]):
            numeric.append(str(column))

    # Low-cardinality text columns are dimensions even if numeric-ish IDs.
    rows = max(len(frame), 1)
    for column in frame.columns:
        name = str(column)
        if name in numeric or name in dates or name in categorical:
            continue
        non_null = frame[column].dropna()
        if non_null.empty:
            continue
        sample = non_null.iloc[:5000] if len(non_null) > 5000 else non_null
        unique = sample.astype("string").nunique()
        if unique <= 60 and (unique / len(sample)) < 0.95:
            categorical.append(name)

    numeric = list(dict.fromkeys(numeric))
    categorical = list(dict.fromkeys(categorical))
    identifiers = list(dict.fromkeys([*identifiers, *[column for column in numeric if any(token in normalise_name(column) for token in ("id", "code", "number", "reference"))]]))

    # A numeric ID should not be offered as a measure.
    identifiers = [column for column in identifiers if column in frame.columns]
    numeric_measures = [column for column in numeric if column not in identifiers]

    # Any text-like column can legitimately be a semantic dimension (for
    # example a product name that happens to be unique in a small dataset).
    # Keep the public ``categorical`` list curated, but allow role detection to
    # consider all text columns.
    text_columns = {
        str(column)
        for column in frame.columns
        if pd.api.types.is_object_dtype(frame[column])
        or pd.api.types.is_string_dtype(frame[column])
        or isinstance(frame[column].dtype, pd.CategoricalDtype)
    }

    numeric_set = set(numeric)
    date_set = set(dates)
    categorical_set = set(categorical) | text_columns
    roles: dict[str, str] = {}
    confidence: dict[str, float] = {}
    candidates: dict[str, list[str]] = {}
    used: set[str] = set()

    # Role priority matters: a "Sales" column must not be claimed as a generic
    # identifier, and an order date must not be claimed by a generic date role.
    priority = [
        "revenue", "profit", "cost", "salary", "quantity", "unit_price", "discount",
        "order_id", "employee_id", "student_id", "customer", "date",
        "product", "category", "department", "region", "city", "store",
        "sales_rep", "payment_method", "employee_name", "student_name", "course",
        "attendance", "grade", "gender", "age",
    ]

    # A column whose name *exactly* matches another role must not be stolen by
    # an earlier, weaker (token/contains) match.  For example "Product Category"
    # is an exact match for ``category`` and only a contains match for
    # ``product``, so ``category`` owns it even though ``product`` is earlier in
    # the priority list.
    exact_owner: dict[str, str] = {}
    for role in priority:
        strong, weak = ROLE_ALIASES.get(role, ((), ()))
        for column in frame.columns:
            name = str(column)
            if name in exact_owner:
                continue
            if _score_alias(name, strong, weak)[0] >= 1.0:
                exact_owner[name] = role

    # Commercial context is evaluated up front because revenue is the first role
    # in the priority list; it cannot rely on roles that are assigned later.
    # A bare "Segment" category is deliberately *not* enough context: it would
    # promote an otherwise generic "Amount" column to revenue.
    commercial_context = any(
        _score_alias(str(column), *ROLE_ALIASES.get(context_role, ((), ())))[0] >= 0.6
        for context_role in ("order_id", "product", "customer")
        for column in frame.columns
    )

    for role in priority:
        strong, weak = ROLE_ALIASES.get(role, ((), ()))
        scored: list[tuple[float, str]] = []
        for column in frame.columns:
            name = str(column)
            if name in used:
                continue
            score, _kind = _score_alias(name, strong, weak)
            if score <= 0:
                continue
            if score < 1.0 and exact_owner.get(name, role) != role:
                # This column is an exact match for a different, more specific role.
                continue
            if not _role_dtype_ok(role, name, numeric_set, date_set, categorical_set):
                # Allow numeric dimensions such as age/grade; allow attendance text.
                if role in ("attendance", "gender", "grade", "age"):
                    pass
                elif role == "date":
                    continue
                else:
                    continue
            scored.append((score, name))
        scored.sort(key=lambda item: (-item[0], frame.columns.get_loc(item[1]) if not isinstance(frame.columns, pd.RangeIndex) else 0))
        candidates[role] = [name for score, name in scored[:5] if score >= 0.38]
        if not scored:
            continue
        best_score, best_column = scored[0]
        # A weak revenue alias needs commercial context.
        if role == "revenue" and best_score < 0.6 and not commercial_context:
            continue
        roles[role] = best_column
        confidence[role] = round(best_score, 2)
        used.add(best_column)

    # Revenue fallback: if no explicit revenue column, use the strongest
    # non-identifier numeric measure only when the dataset is commercial.
    if "revenue" not in roles and "profit" in roles:
        roles["revenue"] = roles["profit"]
        confidence["revenue"] = 0.2
        roles.pop("profit", None)  # a single column should not be both
        candidates.pop("profit", None)

    domain, domain_label = detect_domain(roles, frame)
    warnings = _schema_warnings(frame, numeric, dates, categorical, roles)

    return DatasetSchema(
        columns=[str(column) for column in frame.columns],
        dtypes={str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        numeric=numeric,
        categorical=categorical,
        dates=dates,
        identifiers=identifiers,
        boolean=boolean,
        roles=roles,
        confidence=confidence,
        candidates=candidates,
        domain=domain,
        domain_label=domain_label,
        warnings=warnings,
    )


def detect_domain(roles: dict[str, str], frame: pd.DataFrame) -> tuple[str, str]:
    has = lambda role: bool(roles.get(role))
    if (has("employee_id") or has("salary") or has("attendance")) and (has("employee_id") or has("department")) and not has("product"):
        return "hr", "Human resources"
    if has("student_id") or has("course") or (has("grade") and has("student_name")):
        return "education", "Education"
    if has("product") and (has("revenue") or has("order_id") or has("quantity")):
        return "retail", "Retail & commerce"
    if has("revenue") and (has("profit") or has("cost")):
        return "finance", "Finance & profitability"
    if has("cost") and (has("department") or has("date")):
        return "operations", "Operations"
    if has("salary") or has("expenses") or has("cost"):
        return "finance", "Finance"
    if has("revenue") or has("sales"):
        return "commerce", "Commerce"
    return "generic", "General business"


def _schema_warnings(frame: pd.DataFrame, numeric: list[str], dates: list[str], categorical: list[str], roles: dict[str, str]) -> list[str]:
    warnings: list[str] = []
    if frame.empty:
        warnings.append("The dataset has no rows.")
    if not numeric:
        warnings.append("No numeric measures were detected; KPI totals will be limited to record counts.")
    if not dates:
        warnings.append("No reliable date column was detected; time-series and period comparisons are unavailable.")
    if not categorical and not roles:
        warnings.append("No grouping dimensions were detected; charts will be limited to distributions.")
    missing_columns = [column for column in frame.columns if frame[column].isna().mean() >= 0.5]
    if missing_columns:
        warnings.append("High missingness (>=50%): " + ", ".join(map(str, missing_columns[:6])) + ".")
    if not roles.get("revenue") and not roles.get("profit"):
        warnings.append("No revenue or profit column was confidently detected. You can map it manually below.")
    return warnings


def profile_report(frame: pd.DataFrame, schema: DatasetSchema) -> dict[str, Any]:
    """Build a factual, JSON-friendly profile report (no invented values)."""
    report: dict[str, Any] = {
        "total_records": int(len(frame)),
        "total_columns": int(len(frame.columns)),
        "dtypes": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        "missing_values": {str(column): int(frame[column].isna().sum()) for column in frame.columns},
        "missing_total": int(frame.isna().sum().sum()),
        "duplicate_records": int(frame.duplicated().sum()),
        "unique_values": {str(column): int(frame[column].nunique(dropna=True)) for column in frame.columns},
        "numeric_summary": {},
        "categorical_summary": {},
        "date_ranges": {},
        "warnings": list(schema.warnings),
    }
    for column in schema.numeric:
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        if series.empty:
            continue
        report["numeric_summary"][column] = {
            "count": int(series.count()),
            "mean": float(series.mean()),
            "min": float(series.min()),
            "max": float(series.max()),
            "sum": float(series.sum()),
        }
    for column in schema.categorical[:12]:
        series = frame[column].dropna().astype("string")
        if series.empty:
            continue
        top = series.value_counts().head(5)
        report["categorical_summary"][column] = {str(index): int(value) for index, value in top.items()}
    for column in schema.dates:
        parsed = pd.to_datetime(frame[column], format="mixed", errors="coerce").dropna()
        if parsed.empty:
            continue
        report["date_ranges"][column] = {
            "min": parsed.min().date().isoformat(),
            "max": parsed.max().date().isoformat(),
            "valid": int(parsed.count()),
        }
    return report


def apply_manual_mapping(schema: DatasetSchema, mapping: dict[str, str | None]) -> DatasetSchema:
    """Return a copy of the schema with user-selected role mappings."""
    updated = DatasetSchema.from_dict(schema.to_dict())
    for role, column in mapping.items():
        if column and column in updated.columns:
            updated.roles[role] = column
            updated.confidence[role] = 1.0
        elif column is None or column == "":
            updated.roles.pop(role, None)
            updated.confidence.pop(role, None)
    updated.domain, updated.domain_label = detect_domain(updated.roles, pd.DataFrame(columns=updated.columns))
    updated.warnings = list(schema.warnings)
    return updated
