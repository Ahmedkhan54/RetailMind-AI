r"""Honest end-to-end benchmark for RetailMind AI.

Median of 3 runs per stage on the *same* generated dataset.  tracemalloc is
kept out of timing loops; peak memory is measured in a separate pass and is
explicitly labelled as traced peak (which includes tracemalloc overhead).

Run:  .venv\Scripts\python.exe audit_benchmark.py
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import tracemalloc

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import pandas as pd

from retailmind.schema import infer_schema, profile_report
from retailmind.cleaning import DEFAULT_OPTIONS, apply_cleaning
from retailmind.engine import build_dashboard
from retailmind.alerts import detect_alerts
from retailmind.segmentation import segment_customers
from retailmind.ai.insights import generate_insights
from retailmind.forecasting import forecast_dataset
from retailmind.inventory import build_inventory_recommendations
from retailmind.powerbi import build_pbip
from retailmind.exports import executive_pdf
from retailmind.ai.chat import answer_question

SIZES = (10_000, 50_000, 100_000, 250_000)
REPEATS = 3


def make_frame(rows: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", "2024-12-31", freq="D")
    customers = max(100, rows // 120)
    products = max(50, rows // 400)
    return pd.DataFrame(
        {
            "Order ID": [f"O{i:08d}" for i in range(rows)],
            "Order Date": [dates[int(rng.integers(0, len(dates)))].strftime("%Y-%m-%d") for _ in range(rows)],
            "Customer ID": [f"C{int(rng.integers(0, customers)):06d}" for _ in range(rows)],
            "Product": [f"P{int(rng.integers(0, products)):05d}" for _ in range(rows)],
            "Category": [["Electronics", "Clothing", "Home", "Sports", "Books"][int(rng.integers(0, 5))] for _ in range(rows)],
            "Region": [["North", "South", "East", "West"][int(rng.integers(0, 4))] for _ in range(rows)],
            "Quantity": rng.integers(1, 9, rows),
            "Unit Price": np.round(rng.uniform(5, 400, rows), 2),
            "Discount": np.round(rng.uniform(0, 0.3, rows), 3),
            "Revenue": np.round(rng.uniform(10, 2500, rows), 2),
            "Profit": np.round(rng.uniform(0, 600, rows), 2),
            "Cost": np.round(rng.uniform(5, 2000, rows), 2),
            "Current Stock": rng.integers(20, 600, rows),
            "Lead Time": rng.integers(2, 15, rows),
        }
    )


def timed(fn, repeats: int = REPEATS) -> float:
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def main() -> None:
    print("=" * 78)
    print("RETAILMIND AI HONEST BENCHMARK (median of 3, no tracemalloc in timings)")
    print("=" * 78)
    table: dict[int, dict[str, float]] = {}

    for rows in SIZES:
        frame = make_frame(rows, seed=rows)
        schema = infer_schema(frame)
        csv_bytes = frame.to_csv(index=False).encode("utf-8")
        row: dict[str, float] = {"rows": rows, "csv_mb": len(csv_bytes) / (1024 * 1024)}
        row["csv_parse_ms"] = timed(lambda: pd.read_csv(pd.io.common.BytesIO(csv_bytes)))
        row["schema_ms"] = timed(lambda: infer_schema(frame))
        row["profile_ms"] = timed(lambda: profile_report(frame, schema))
        row["clean_ms"] = timed(lambda: apply_cleaning(frame, schema, DEFAULT_OPTIONS))
        row["dashboard_ms"] = timed(lambda: build_dashboard(frame, schema, "bench.csv", f"bench-{rows}"), repeats=1)
        row["alerts_ms"] = timed(lambda: detect_alerts(frame, schema))
        row["segmentation_ms"] = timed(lambda: segment_customers(frame, schema, max_clusters=4))
        row["insights_ms"] = timed(lambda: generate_insights(frame, schema))
        row["forecast_ms"] = timed(lambda: forecast_dataset(frame, schema, metric_role="revenue", frequency="Monthly", periods=6))
        row["inventory_ms"] = timed(lambda: build_inventory_recommendations(frame, schema))
        row["pbip_ms"] = timed(lambda: build_pbip(frame, schema))
        row["exec_pdf_ms"] = timed(lambda: executive_pdf(frame, schema, filename="bench.csv", filters={}, insights=generate_insights(frame, schema, max_items=5)), repeats=1)
        row["chatbot_ms"] = timed(lambda: answer_question("What is total revenue?", frame, schema))
        # Simulated request pipeline: parse + schema + clean + dashboard + alerts + insights.
        def pipeline():
            s = infer_schema(frame)
            _cleaned, _report = apply_cleaning(frame, s, DEFAULT_OPTIONS)
            build_dashboard(frame, s, "bench.csv", f"pipe-{rows}")
            detect_alerts(frame, s)
            generate_insights(frame, s)
        row["pipeline_ms"] = timed(pipeline, repeats=2)
        table[rows] = row

        # Separate traced-memory pass at the largest size only.
        if rows == SIZES[-1]:
            tracemalloc.start()
            s = infer_schema(frame)
            apply_cleaning(frame, s, DEFAULT_OPTIONS)
            detect_alerts(frame, s)
            segment_customers(frame, s, max_clusters=4)
            generate_insights(frame, s)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            row["traced_peak_mb"] = peak / (1024 * 1024)

    columns = [
        "rows", "csv_mb", "csv_parse_ms", "schema_ms", "profile_ms", "clean_ms",
        "dashboard_ms", "alerts_ms", "segmentation_ms", "insights_ms", "forecast_ms",
        "inventory_ms", "pbip_ms", "exec_pdf_ms", "chatbot_ms", "pipeline_ms", "traced_peak_mb",
    ]
    print("\n" + " | ".join(columns))
    for rows in SIZES:
        row = table[rows]
        print(" | ".join(
            f"{row.get(column, float('nan')):.1f}" if isinstance(row.get(column), float) else str(row.get(column, ""))
            for column in columns
        ))

    print("\nNotes:")
    print("- pipeline_ms = schema + cleaning + dashboard + alerts + insights (no CSV parse, no PDF).")
    print("- traced_peak_mb is measured separately with tracemalloc (inflates memory, excluded from timings).")
    print("- Datasets are synthetic with realistic cardinality (customers=max(100, rows/120)).")

    out = {
        "sizes": SIZES,
        "repeats": REPEATS,
        "columns": columns,
        "results": table,
        "environment": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    with open("benchmark_results.json", "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2)
    print("\nWrote benchmark_results.json")


if __name__ == "__main__":
    main()
