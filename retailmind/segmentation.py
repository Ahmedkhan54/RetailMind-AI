"""Customer segmentation: RFM analysis and NumPy K-Means.

The module deliberately avoids a hard dependency on scikit-learn.  Standard
scaling, K-Means++ initialisation and the silhouette score are implemented with
NumPy so the feature works in the same environment as the rest of RetailMind AI.
When scikit-learn *is* installed it is still not required; results are
deterministic because every random step uses a fixed seed.

Labels are behavioural, not raw cluster numbers.  A cluster is named from its
recency/frequency/monetary profile relative to the other clusters, and the
rule-based churn flag is explicitly documented as a rule, not a validated
future-churn prediction model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import math
from typing import Any

import numpy as np
import pandas as pd

from retailmind.schema import DatasetSchema


SEGMENTS = (
    "Loyal Customers",
    "Big Spenders",
    "Potential Loyalists",
    "New Customers",
    "At-Risk Customers",
    "Churn Risk Customers",
)


@dataclass
class SegmentationResult:
    available: bool
    rfm: pd.DataFrame = field(default_factory=pd.DataFrame)
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)
    k: int = 0
    silhouette: float | None = None
    method: str = "rfm-kmeans"
    notes: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)

    def to_csv_bytes(self) -> bytes:
        return self.rfm.to_csv(index=False).encode("utf-8-sig")

    def to_excel_bytes(self) -> bytes:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            self.rfm.to_excel(writer, sheet_name="Customer RFM", index=False)
            if not self.summary.empty:
                self.summary.to_excel(writer, sheet_name="Segment Summary", index=False)
        return output.getvalue()


def _find_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    for column in frame.columns:
        normalised = str(column).strip().lower().replace("_", " ").replace("-", " ")
        if normalised in aliases:
            return column
    for column in frame.columns:
        normalised = str(column).strip().lower().replace("_", " ").replace("-", " ")
        if any(alias in normalised for alias in aliases):
            return column
    return None


def detect_customer_columns(frame: pd.DataFrame, schema: DatasetSchema) -> dict[str, str | None]:
    """Resolve the columns required for RFM without inventing any of them."""
    customer = schema.role_column("customer") or _find_column(
        frame, ("customer id", "customer", "cust id", "cust_id", "cust", "client id", "client", "buyer", "account id", "account")
    )
    order = schema.role_column("order_id") or _find_column(
        frame, ("order id", "invoice", "invoice id", "transaction id", "receipt", "order number")
    )
    date = schema.role_column("date") or (schema.dates[0] if schema.dates else None)
    revenue = schema.role_column("revenue")
    quantity = schema.role_column("quantity")
    unit_price = schema.role_column("unit_price")
    profit = schema.role_column("profit")
    if revenue is None and unit_price and quantity:
        # The caller can derive revenue; record both source columns instead.
        revenue = None
    return {
        "customer": customer,
        "order": order,
        "date": date,
        "revenue": revenue,
        "quantity": quantity,
        "unit_price": unit_price,
        "profit": profit,
    }


def _rfm_frame(frame: pd.DataFrame, columns: dict[str, str | None]) -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    customer, order, date = columns["customer"], columns["order"], columns["date"]
    revenue, quantity, unit_price = columns["revenue"], columns["quantity"], columns["unit_price"]
    working = pd.DataFrame(index=frame.index)
    working["customer_id"] = frame[customer].astype("string")
    working["order_date"] = pd.to_datetime(frame[date], format="mixed", errors="coerce")
    if revenue:
        working["monetary_value"] = pd.to_numeric(frame[revenue], errors="coerce")
    elif quantity and unit_price:
        working["monetary_value"] = (
            pd.to_numeric(frame[quantity], errors="coerce")
            * pd.to_numeric(frame[unit_price], errors="coerce")
        )
        notes.append("Revenue was derived as quantity × unit price because no revenue column was mapped.")
    else:
        working["monetary_value"] = np.nan
    if order:
        working["order_id"] = frame[order].astype("string")
    else:
        working["order_id"] = pd.Series(range(len(frame)), index=frame.index).astype("string")
        notes.append("No order identifier was mapped; each row is treated as one order for frequency.")
    if columns["profit"]:
        working["profit_value"] = pd.to_numeric(frame[columns["profit"]], errors="coerce")

    working = working.dropna(subset=["customer_id", "order_date"])
    working = working[working["customer_id"].str.strip() != ""]
    working = working.dropna(subset=["monetary_value"])
    if working.empty:
        return pd.DataFrame(), ["No rows contain a valid customer, date and monetary value."]

    snapshot = working["order_date"].max() + pd.Timedelta(days=1)
    grouped = working.groupby("customer_id", dropna=True)
    rfm = grouped.agg(
        recency=("order_date", lambda values: int((snapshot - values.max()).days)),
        first_purchase=("order_date", "min"),
        last_purchase=("order_date", "max"),
        monetary=("monetary_value", "sum"),
        frequency=("order_id", "nunique"),
        total_rows=("order_id", "size"),
    ).reset_index()
    rfm["frequency"] = rfm["frequency"].clip(lower=1)
    rfm["total_orders"] = rfm["frequency"]
    rfm["avg_purchase_value"] = rfm["monetary"] / rfm["frequency"].replace(0, np.nan)
    rfm["tenure_days"] = (rfm["last_purchase"] - rfm["first_purchase"]).dt.days
    rfm["monetary"] = rfm["monetary"].astype(float)
    rfm = rfm.sort_values("monetary", ascending=False).reset_index(drop=True)
    return rfm, notes


def _standardize(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    std = np.where(std == 0, 1.0, std)
    return (matrix - mean) / std, mean, std


def _kmeans_plus_plus(matrix: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    centers = [matrix[rng.integers(len(matrix))]]
    for _ in range(1, k):
        distances = np.min(
            ((matrix[:, None, :] - np.array(centers)[None, :, :]) ** 2).sum(axis=2), axis=1
        )
        probabilities = distances / distances.sum() if distances.sum() > 0 else None
        index = rng.choice(len(matrix), p=probabilities) if probabilities is not None else rng.integers(len(matrix))
        centers.append(matrix[index])
    return np.array(centers)


def kmeans_numpy(
    matrix: np.ndarray,
    k: int,
    *,
    n_init: int = 10,
    max_iter: int = 150,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Deterministic K-Means with K-Means++ seeding and empty-cluster repair."""
    if len(matrix) == 0:
        raise ValueError("K-Means needs at least one row.")
    k = max(1, min(int(k), len(matrix)))
    rng = np.random.default_rng(seed)
    best_labels = np.zeros(len(matrix), dtype=int)
    best_centers = matrix[:k].copy()
    best_inertia = math.inf
    for _ in range(max(1, n_init)):
        centers = _kmeans_plus_plus(matrix, k, rng)
        labels = np.zeros(len(matrix), dtype=int)
        for _iteration in range(max_iter):
            distances = ((matrix[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            new_labels = distances.argmin(axis=1)
            if np.array_equal(new_labels, labels) and _iteration > 0:
                labels = new_labels
                break
            labels = new_labels
            for cluster in range(k):
                members = matrix[labels == cluster]
                if len(members):
                    centers[cluster] = members.mean(axis=0)
                else:  # repair an empty cluster by splitting the largest one
                    largest = int(np.bincount(labels).argmax())
                    members = matrix[labels == largest]
                    if len(members) > 1:
                        centers[cluster] = members[rng.integers(len(members))]
        inertia = float(((matrix - centers[labels]) ** 2).sum())
        if inertia < best_inertia:
            best_inertia, best_labels, best_centers = inertia, labels.copy(), centers.copy()
    return best_labels, best_centers, best_inertia


def silhouette_score_numpy(matrix: np.ndarray, labels: np.ndarray, *, sample: int = 1500, seed: int = 42) -> float | None:
    """Silhouette score on a deterministic sample (O(n²) is avoided for big data)."""
    unique = np.unique(labels)
    if len(unique) < 2 or len(matrix) < 3:
        return None
    if len(matrix) > sample:
        rng = np.random.default_rng(seed)
        indices = rng.choice(len(matrix), size=sample, replace=False)
        matrix, labels = matrix[indices], labels[indices]
    distances = np.sqrt(((matrix[:, None, :] - matrix[None, :, :]) ** 2).sum(axis=2))
    scores: list[float] = []
    for index in range(len(matrix)):
        own = labels == labels[index]
        own_count = int(own.sum())
        if own_count <= 1:
            scores.append(0.0)
            continue
        a = distances[index, own].sum() / (own_count - 1)
        b = min(
            distances[index, labels == cluster].mean()
            for cluster in unique
            if cluster != labels[index]
        )
        denominator = max(a, b)
        scores.append((b - a) / denominator if denominator else 0.0)
    return float(np.mean(scores)) if scores else None


def _choose_k(matrix: np.ndarray, max_k: int, seed: int = 42) -> tuple[int, float | None, np.ndarray]:
    n = len(matrix)
    if n <= 2:
        labels = np.zeros(n, dtype=int)
        return 1, None, labels
    candidates = list(range(2, min(max_k, n - 1) + 1))
    best = (2, None, np.zeros(n, dtype=int))
    for k in candidates:
        labels, _centers, _inertia = kmeans_numpy(matrix, k, seed=seed)
        if len(np.unique(labels)) < 2:
            continue
        score = silhouette_score_numpy(matrix, labels, seed=seed)
        if score is not None and (best[1] is None or score > best[1]):
            best = (k, score, labels)
    return best


def _normalise(series: pd.Series) -> pd.Series:
    minimum, maximum = series.min(), series.max()
    if not math.isfinite(float(minimum)) or not math.isfinite(float(maximum)) or maximum == minimum:
        return pd.Series(0.5, index=series.index)
    return (series - minimum) / (maximum - minimum)


def _behavioural_labels(rfm: pd.DataFrame, labels: np.ndarray) -> dict[int, str]:
    """Map cluster numbers to documented behavioural labels.

    The profile of each cluster is compared with the other clusters using
    recency (lower is better), frequency and monetary value.  No label is based
    on the cluster number itself.
    """
    profile = rfm.copy()
    profile["cluster"] = labels
    grouped = profile.groupby("cluster").agg(
        recency=("recency", "mean"),
        frequency=("frequency", "mean"),
        monetary=("monetary", "mean"),
        customers=("customer_id", "size"),
    )
    if len(grouped) == 1:
        return {int(grouped.index[0]): "Loyal Customers"}
    grouped["r_score"] = 1 - _normalise(grouped["recency"])
    grouped["f_score"] = _normalise(grouped["frequency"])
    grouped["m_score"] = _normalise(grouped["monetary"])
    grouped["value"] = (grouped["r_score"] + grouped["f_score"] + grouped["m_score"]) / 3

    remaining = list(grouped.index)
    mapping: dict[int, str] = {}

    def take(label: str, selector) -> None:
        candidates = [index for index in remaining if selector(grouped.loc[index])]
        if not candidates:
            return
        chosen = max(candidates, key=lambda index: (grouped.loc[index, "value"], grouped.loc[index, "customers"]))
        mapping[int(chosen)] = label
        remaining.remove(chosen)

    # Highest monetary cluster first: big spenders.
    take("Big Spenders", lambda row: row["m_score"] >= 0.75)
    # Strong frequency with acceptable recency.
    take("Loyal Customers", lambda row: row["f_score"] >= 0.6 and row["r_score"] >= 0.4)
    # Recent but not frequent: new customers.
    take("New Customers", lambda row: row["r_score"] >= 0.7 and row["f_score"] <= 0.45)
    # Recent and moderately frequent.
    take("Potential Loyalists", lambda row: row["r_score"] >= 0.5 and row["f_score"] >= 0.35)
    # Stale but historically valuable.
    take("At-Risk Customers", lambda row: row["r_score"] <= 0.45 and (row["m_score"] >= 0.4 or row["f_score"] >= 0.4))
    # Everything else is churn risk.
    for index in remaining:
        mapping[int(index)] = "Churn Risk Customers"
    return mapping


def segment_customers(
    frame: pd.DataFrame,
    schema: DatasetSchema,
    *,
    max_clusters: int = 6,
    random_state: int = 42,
) -> SegmentationResult:
    columns = detect_customer_columns(frame, schema)
    missing = [name for name in ("customer", "date") if not columns.get(name)]
    if missing:
        return SegmentationResult(
            available=False,
            notes=[
                "Customer segmentation needs a customer identifier and an order date. "
                f"Missing: {', '.join(missing)}. Map these columns in the column-mapping review."
            ],
        )
    if not columns.get("revenue") and not (columns.get("quantity") and columns.get("unit_price")):
        return SegmentationResult(
            available=False,
            notes=[
                "Customer segmentation needs a revenue column (or quantity + unit price) to calculate monetary value."
            ],
        )

    rfm, notes = _rfm_frame(frame, columns)
    if rfm.empty:
        return SegmentationResult(available=False, notes=notes or ["No valid customer transactions were found."])
    if len(rfm) < 2:
        return SegmentationResult(available=False, rfm=rfm, notes=["At least two customers are required for segmentation."])

    features = np.column_stack(
        [
            np.log1p(rfm["recency"].astype(float).to_numpy()),
            np.log1p(rfm["frequency"].astype(float).to_numpy()),
            np.log1p(rfm["monetary"].astype(float).to_numpy()),
        ]
    )
    scaled, _mean, _std = _standardize(features)
    k, silhouette, labels = _choose_k(scaled, max_clusters, seed=random_state)
    if k < 2:
        labels = np.zeros(len(rfm), dtype=int)
        silhouette = None
    mapping = _behavioural_labels(rfm, labels)
    rfm["cluster"] = labels
    rfm["segment"] = [mapping.get(int(label), f"Segment {int(label) + 1}") for label in labels]

    # Rule-based risk flag: transparent, not a trained churn probability.
    median_recency = float(rfm["recency"].median())
    median_frequency = float(rfm["frequency"].median())
    rfm["churn_risk_rule"] = np.where(
        (rfm["recency"] > 2 * median_recency) & (rfm["frequency"] <= median_frequency),
        "High rule-based risk",
        np.where(rfm["recency"] > median_recency, "Monitor", "Low rule-based risk"),
    )
    rfm["is_rule_based_churn_risk"] = rfm["churn_risk_rule"].eq("High rule-based risk")
    rfm = rfm.rename(columns={"recency": "recency_days", "monetary": "monetary_value"})

    summary = (
        rfm.groupby("segment", dropna=False)
        .agg(
            customers=("customer_id", "size"),
            revenue=("monetary_value", "sum"),
            avg_recency_days=("recency_days", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_monetary_value=("monetary_value", "mean"),
            avg_purchase_value=("avg_purchase_value", "mean"),
            rule_based_risk_customers=("is_rule_based_churn_risk", "sum"),
        )
        .reset_index()
    )
    total_customers = max(1, int(len(rfm)))
    total_revenue = float(rfm["monetary_value"].sum())
    summary["customer_share"] = summary["customers"] / total_customers
    summary["revenue_share"] = summary["revenue"] / total_revenue if total_revenue else 0.0
    summary = summary.sort_values("revenue", ascending=False).reset_index(drop=True)
    notes.append(
        "Segments are behavioural RFM clusters (log-transformed, standard-scaled, K-Means). "
        "The churn-risk flag is a transparent rule, not a validated future-churn prediction."
    )
    if silhouette is not None:
        notes.append(f"Silhouette score for k={k}: {silhouette:.3f} (sampled at most 1,500 customers).")
    return SegmentationResult(
        available=True,
        rfm=rfm,
        summary=summary,
        k=k,
        silhouette=silhouette,
        notes=notes,
        mapping={str(key): value for key, value in mapping.items()},
    )
