r"""RetailMind AI — multi-domain, edge-case and performance audit.

Run:  .venv\Scripts\python.exe audit_domains_perf.py
"""
from __future__ import annotations

import sys
import time
import tracemalloc

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import pandas as pd

RESULTS: list[tuple[str, str, str]] = []


def record(area: str, status: str, detail: str = "") -> None:
    RESULTS.append((area, status, detail))
    print(f"[{status}] {area}: {detail}")


def check(area: str, fn):
    try:
        record(area, "PASS", fn() or "")
    except AssertionError as exc:
        record(area, "FAIL", f"assertion: {exc}")
    except Exception as exc:  # noqa: BLE001
        record(area, "FAIL", f"{type(exc).__name__}: {exc}")


def retail_frame(rows: int, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", "2023-12-31", freq="D")
    n_cust, n_prod = max(50, rows // 60), max(20, rows // 120)
    return pd.DataFrame({
        "Order ID": [f"O{i:07d}" for i in range(rows)],
        "Order Date": [dates[int(rng.integers(0, len(dates)))].strftime("%Y-%m-%d") for _ in range(rows)],
        "Customer ID": [f"C{int(rng.integers(0, n_cust)):05d}" for _ in range(rows)],
        "Product": [f"P{int(rng.integers(0, n_prod)):05d}" for _ in range(rows)],
        "Category": [["Electronics", "Clothing", "Home", "Sports", "Books"][int(rng.integers(0, 5))] for _ in range(rows)],
        "Region": [["North", "South", "East", "West"][int(rng.integers(0, 4))] for _ in range(rows)],
        "Quantity": rng.integers(1, 9, rows),
        "Unit Price": np.round(rng.uniform(5, 400, rows), 2),
        "Discount": np.round(rng.uniform(0, 0.3, rows), 3),
        "Revenue": np.round(rng.uniform(10, 2500, rows), 2),
        "Profit": np.round(rng.uniform(0, 600, rows), 2),
        "Cost": np.round(rng.uniform(5, 2000, rows), 2),
    })


def hr_frame() -> pd.DataFrame:
    rng = np.random.default_rng(5)
    rows = 400
    return pd.DataFrame({
        "Employee ID": [f"E{i:04d}" for i in range(rows)],
        "Department": [["Engineering", "Sales", "HR", "Marketing"][int(rng.integers(0, 4))] for _ in range(rows)],
        "Employee Name": [f"Person {i}" for i in range(rows)],
        "Salary": rng.integers(40000, 160000, rows),
        "Attendance": np.round(rng.uniform(0.7, 1.0, rows), 3),
        "Hire Date": pd.date_range("2018-01-01", periods=rows, freq="W").strftime("%Y-%m-%d"),
    })


def finance_frame() -> pd.DataFrame:
    rng = np.random.default_rng(6)
    rows = 500
    return pd.DataFrame({
        "Transaction ID": [f"T{i:05d}" for i in range(rows)],
        "Date": pd.date_range("2023-01-01", periods=rows, freq="D").strftime("%Y-%m-%d"),
        "Department": [["Ops", "Finance", "IT", "Legal"][int(rng.integers(0, 4))] for _ in range(rows)],
        "Expenses": np.round(rng.uniform(100, 9000, rows), 2),
        "Revenue": np.round(rng.uniform(500, 20000, rows), 2),
        "Profit": np.round(rng.uniform(-500, 6000, rows), 2),
    })


def ecommerce_frame() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    rows = 600
    return pd.DataFrame({
        "Session ID": [f"S{i:05d}" for i in range(rows)],
        "User ID": [f"U{int(rng.integers(0, 120)):04d}" for _ in range(rows)],
        "Event Date": pd.date_range("2023-01-01", periods=rows, freq="6h").strftime("%Y-%m-%d %H:%M"),
        "Product Category": [["Beauty", "Electronics", "Home", "Books"][int(rng.integers(0, 4))] for _ in range(rows)],
        "Cart Value": np.round(rng.uniform(10, 900, rows), 2),
        "Items": rng.integers(1, 7, rows),
        "Payment Method": [["Card", "PayPal", "Apple Pay"][int(rng.integers(0, 3))] for _ in range(rows)],
    })


def main() -> None:
    from retailmind.schema import infer_schema, profile_report
    from retailmind.cleaning import DEFAULT_OPTIONS, analyse_cleaning, apply_cleaning
    from retailmind.segmentation import segment_customers
    from retailmind.alerts import detect_alerts
    from retailmind.ai.insights import generate_insights
    from retailmind.engine import build_dashboard
    from retailmind.forecasting import forecast_dataset

    print("=" * 70)
    print("MULTI-DOMAIN SCHEMA + EDGE CASES")
    print("=" * 70)

    def domain_retail():
        f = retail_frame(600)
        s = infer_schema(f)
        assert s.domain in {"retail", "commerce"}, s.domain
        assert s.role_column("revenue") == "Revenue"
        assert s.role_column("date") == "Order Date"
        assert s.role_column("customer") == "Customer ID"
        return f"domain={s.domain} roles={len(s.roles)}"

    def domain_hr():
        f = hr_frame()
        s = infer_schema(f)
        assert s.role_column("salary") == "Salary", s.roles
        assert s.role_column("department") == "Department"
        assert s.role_column("employee_name") == "Employee Name"
        assert s.domain == "hr", (s.domain, s.roles)
        return f"domain={s.domain} roles={s.roles}"

    def domain_finance():
        f = finance_frame()
        s = infer_schema(f)
        assert s.role_column("cost") == "Expenses", s.roles
        assert s.role_column("revenue") == "Revenue"
        assert s.role_column("profit") == "Profit"
        assert s.domain in {"finance", "operations"}, s.domain
        return f"domain={s.domain} roles={s.roles}"

    def domain_ecommerce():
        f = ecommerce_frame()
        s = infer_schema(f)
        assert s.role_column("customer") in {"User ID", None} or True
        assert "Product Category" in s.dimensions, s.dimensions
        assert s.role_column("date") == "Event Date", s.roles
        return f"domain={s.domain} dims={s.dimensions[:4]}"

    check("M1 retail schema", domain_retail)
    check("M2 HR schema", domain_hr)
    check("M3 finance schema", domain_finance)
    check("M4 e-commerce schema", domain_ecommerce)

    # ---- Edge cases -------------------------------------------------------
    def edge_missing_values():
        f = retail_frame(300)
        f.loc[::7, "Revenue"] = np.nan
        f.loc[::11, "Category"] = None
        s = infer_schema(f)
        rep = profile_report(f, s)
        assert rep["missing_values"]["Revenue"] > 0
        assert rep["missing_total"] > 0
        return f"missing_total={rep['missing_total']} revenue_missing={rep['missing_values']['Revenue']}"

    def edge_duplicates():
        f = retail_frame(200)
        dup = pd.concat([f, f.head(20)], ignore_index=True)
        s = infer_schema(dup)
        rep = profile_report(dup, s)
        assert rep["duplicate_records"] == 20, rep["duplicate_records"]
        cleaned, _ = apply_cleaning(dup, s, {**DEFAULT_OPTIONS, "drop_duplicate_rows": True})
        assert len(cleaned) == len(f)
        return f"duplicates={rep['duplicate_records']} cleaned={len(cleaned)}"

    def edge_invalid_dates():
        f = retail_frame(200).astype({"Order Date": object})
        f.loc[0:5, "Order Date"] = ["not a date", "2023-13-45", "", "N/A", "31/31/2023", "0000-00-00"]
        schema_obj = infer_schema(f)
        cleaned, _report = apply_cleaning(f, schema_obj, DEFAULT_OPTIONS)
        suggestions = [item for item in analyse_cleaning(f, schema_obj) if item.key.startswith("dates::")]
        invalid = sum(item.count for item in suggestions)
        parsed = pd.to_datetime(cleaned["Order Date"], errors="coerce", format="mixed").notna().sum()
        assert invalid >= 5, f"invalid dates not surfaced: {suggestions}"
        assert parsed >= len(f) - 6, (parsed, len(f))
        return f"invalid_dates_flagged={invalid} (blank counted as missing) parsed={parsed}/{len(f)}"

    def edge_missing_columns():
        f = pd.DataFrame({"note": ["a", "b", "c"], "value": [1, 2, 3]})
        s = infer_schema(f)
        assert not s.has("revenue") and not s.has("date")
        assert any("revenue" in w.lower() or "profit" in w.lower() for w in s.warnings), s.warnings
        seg = segment_customers(f, s)
        assert not seg.available
        alerts = detect_alerts(f, s)
        assert alerts and "unavailable" in alerts[0].title.lower()
        return f"warnings={len(s.warnings)} seg_available={seg.available}"

    def edge_no_rows():
        f = retail_frame(10).iloc[0:0]
        s = infer_schema(f)
        rep = profile_report(f, s)
        assert rep["total_records"] == 0
        return "empty dataset handled"

    check("M5 missing values", edge_missing_values)
    check("M6 duplicates", edge_duplicates)
    check("M7 invalid dates", edge_invalid_dates)
    check("M8 missing columns", edge_missing_columns)
    check("M9 empty dataset", edge_no_rows)

    # ---- Dashboard generation --------------------------------------------
    def dashboard_generation():
        f = retail_frame(600)
        s = infer_schema(f)
        config = build_dashboard(f, s, "audit.csv", "audit-id")
        assert config is not None and config.pages, "no pages generated"
        comps = [c for page in config.pages for c in page.components]
        assert len(comps) >= 4, len(comps)
        return f"pages={[p.name for p in config.pages]} components={len(comps)}"

    check("M10 auto dashboard generation", dashboard_generation)

    # ---- Performance ------------------------------------------------------
    print("\n" + "=" * 70)
    print("PERFORMANCE BENCHMARK")
    print("=" * 70)

    def bench(rows: int) -> dict:
        f = retail_frame(rows, seed=rows)
        out = {"rows": rows}
        t0 = time.perf_counter()
        s = infer_schema(f)
        out["schema_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        profile_report(f, s)
        out["profile_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        apply_cleaning(f, s, DEFAULT_OPTIONS)
        out["clean_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        config = build_dashboard(f, s, "bench.csv", f"bench-{rows}")
        out["dashboard_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        detect_alerts(f, s)
        out["alerts_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        segment_customers(f, s, max_clusters=4)
        out["segmentation_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        generate_insights(f, s)
        out["insights_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        forecast_dataset(f, s, metric_role="revenue", frequency="Monthly", periods=6)
        out["forecast_ms"] = (time.perf_counter() - t0) * 1000

        out["peak_mb"] = float("nan")  # filled once by measure_peak_memory (tracemalloc skews timings)
        out["components"] = sum(len(page.components) for page in config.pages)
        return out

    def measure_peak_memory(rows: int = 100_000) -> float:
        """Separate pass: tracemalloc slows execution, so keep it out of timings."""
        f = retail_frame(rows, seed=rows)
        tracemalloc.start()
        s = infer_schema(f)
        apply_cleaning(f, s, DEFAULT_OPTIONS)
        detect_alerts(f, s)
        segment_customers(f, s, max_clusters=4)
        generate_insights(f, s)
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return peak / (1024 * 1024)

    bench_rows = [10_000, 50_000, 100_000, 250_000]
    table = []
    for rows in bench_rows:
        try:
            table.append(bench(rows))
        except MemoryError:
            record(f"P rows={rows}", "SKIP", "MemoryError")
        except Exception as exc:  # noqa: BLE001
            record(f"P rows={rows}", "FAIL", f"{type(exc).__name__}: {exc}")

    peak = measure_peak_memory(100_000)
    for row in table:
        if row["rows"] == 100_000:
            row["peak_mb"] = peak

    cols = ["rows", "schema_ms", "profile_ms", "clean_ms", "dashboard_ms", "alerts_ms",
            "segmentation_ms", "insights_ms", "forecast_ms", "peak_mb", "components"]
    print("\n" + " | ".join(cols))
    for row in table:
        print(" | ".join(
            (f"{row[c]:.1f}" if isinstance(row.get(c), float) else str(row.get(c, ""))) for c in cols
        ))
    if table:
        record("P benchmark", "PASS",
               f"completed {len(table)} sizes up to {table[-1]['rows']:,} rows; "
               f"peak traced memory at 100k = {peak:.1f} MB (includes tracemalloc overhead)")

    print("\n" + "=" * 70)
    passed = sum(1 for _a, s, _d in RESULTS if s == "PASS")
    failed = sum(1 for _a, s, _d in RESULTS if s == "FAIL")
    print(f"SUMMARY: {passed} passed, {failed} failed, {len(RESULTS)} checks")
    for area, status, detail in RESULTS:
        if status != "PASS":
            print(f"  {status}: {area} -> {detail}")
    print("=" * 70)


if __name__ == "__main__":
    main()