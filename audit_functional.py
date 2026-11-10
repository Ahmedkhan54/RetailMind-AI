r"""Independent functional audit for RetailMind AI (no UI required).

Run:  .venv\Scripts\python.exe audit_functional.py
"""
from __future__ import annotations

import math
import sys
import time
import traceback
from io import BytesIO

try:  # Windows consoles default to cp1252 and cannot print currency glyphs
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
        detail = fn()
        record(area, "PASS", detail or "")
    except AssertionError as exc:
        record(area, "FAIL", f"assertion: {exc}")
    except Exception as exc:  # noqa: BLE001
        record(area, "FAIL", f"{type(exc).__name__}: {exc}")
        traceback.print_exc()


def build_retail(rows: int = 3000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
    customers = [f"C{i:03d}" for i in range(1, 61)]
    products = [f"P{i:03d}" for i in range(1, 26)]
    categories = ["Electronics", "Clothing", "Home", "Sports", "Books"]
    records = []
    for i in range(rows):
        qty = int(rng.integers(1, 8))
        price = float(round(rng.uniform(10, 300), 2))
        discount = float(round(rng.uniform(0, 0.25), 3))
        revenue = qty * price * (1 - discount)
        margin = float(rng.uniform(0.2, 0.45))
        records.append({
            "Order ID": f"O{i:06d}",
            "Order Date": dates[int(rng.integers(0, len(dates)))].strftime("%Y-%m-%d"),
            "Customer ID": customers[int(rng.integers(0, len(customers)))],
            "Product": products[int(rng.integers(0, len(products)))],
            "Category": categories[int(rng.integers(0, len(categories)))],
            "Region": ["North", "South", "East", "West"][int(rng.integers(0, 4))],
            "Quantity": qty,
            "Unit Price": price,
            "Discount": discount,
            "Revenue": round(revenue, 2),
            "Profit": round(revenue * margin, 2),
            "Cost": round(revenue - revenue * margin, 2),
        })
    return pd.DataFrame(records)


def build_inventory(seed: int = 11) -> pd.DataFrame:
    """Deterministic inventory scenario with known hand-computed answers."""
    dates = pd.date_range("2023-01-01", periods=28, freq="D")
    rows = []
    for d in dates:
        rows.append({"Product": "Widget", "Date": d.strftime("%Y-%m-%d"), "Quantity": 10})
    # Current stock 200, lead 7 days, constant demand 10/day
    for row in rows:
        row["Current Stock"] = 200
        row["Lead Time"] = 7
    return pd.DataFrame(rows)


def main() -> None:
    print("=" * 70)
    print("RETAILMIND AI INDEPENDENT FUNCTIONAL AUDIT")
    print("=" * 70)

    from retailmind.schema import infer_schema, profile_report
    from retailmind.cleaning import DEFAULT_OPTIONS, analyse_cleaning, apply_cleaning
    from retailmind.alerts import detect_alerts, merge_alerts, acknowledge, dismiss, alerts_csv_bytes
    from retailmind.segmentation import segment_customers
    from retailmind.inventory import build_inventory_recommendations
    from retailmind.forecasting import forecast_dataset, prepare_series, _metrics
    from retailmind.ai.insights import generate_insights
    from retailmind.powerbi import build_pbip, validate_pbip
    from retailmind.exports import executive_pdf, business_analysis_pdf, theme_json_bytes, workbook_bytes
    from retailmind.utils import dataframe_to_csv_bytes
    from retailmind.ai.rag import RAGStore, extract_text
    from retailmind.ai.chat import answer_question
    from retailmind.ai.nlp import parse_question

    frame = build_retail()
    print(f"\nRetail dataset: {len(frame):,} rows x {len(frame.columns)} columns\n")

    # ---- B. Schema / cleaning ------------------------------------------------
    schema_holder = {}

    def schema_check():
        schema = infer_schema(frame)
        schema_holder["schema"] = schema
        assert schema.role_column("revenue") == "Revenue", schema.roles
        assert schema.role_column("profit") == "Profit"
        assert schema.role_column("date") == "Order Date"
        assert schema.role_column("customer") == "Customer ID"
        assert schema.role_column("order_id") == "Order ID"
        assert schema.role_column("product") == "Product"
        assert schema.domain in {"retail", "commerce"}, schema.domain
        return f"roles={schema.roles} domain={schema.domain}"

    check("B1 schema role detection (retail)", schema_check)

    def profile_check():
        rep = profile_report(frame, schema_holder["schema"])
        assert rep["total_records"] == len(frame)
        assert abs(rep["numeric_summary"]["Revenue"]["sum"] - frame["Revenue"].sum()) < 0.01
        return f"records={rep['total_records']} revenue_sum={rep['numeric_summary']['Revenue']['sum']:.2f}"

    check("B2 profile report numerics", profile_check)

    def cleaning_check():
        dirty = frame.copy()
        dirty["Revenue"] = dirty["Revenue"].astype(object)
        dirty.loc[0, "Category"] = "  electronics "
        dirty.loc[1, "Revenue"] = "not-a-number"
        options = dict(DEFAULT_OPTIONS)
        options["drop_duplicate_rows"] = True
        dup = dirty.iloc[[2]].copy()
        dirty = pd.concat([dirty, dup], ignore_index=True)
        before = len(dirty)
        cleaned, report = apply_cleaning(dirty, infer_schema(dirty), options)
        assert len(cleaned) == before - 1, (len(cleaned), before)
        assert pd.api.types.is_numeric_dtype(cleaned["Revenue"])
        return f"rows {before}->{len(cleaned)}, revenue numeric={pd.api.types.is_numeric_dtype(cleaned['Revenue'])}"

    check("B3 cleaning (dupes + coercion)", cleaning_check)

    # ---- E. Alerts -----------------------------------------------------------
    def alerts_check():
        alerts = detect_alerts(frame, schema_holder["schema"])
        assert len(alerts) > 0, "no alerts produced"
        processed = [acknowledge(a) for a in alerts[:1]]
        dismissed = [dismiss(a) for a in alerts[1:2]]
        merged = merge_alerts(alerts, alerts)  # duplicates must be suppressed
        csv_bytes = alerts_csv_bytes(alerts)
        assert csv_bytes.startswith(b"\xef\xbb\xbf") or b"title" in csv_bytes.lower()
        assert len(merged) == len(alerts), f"duplicate prevention failed {len(merged)} vs {len(alerts)}"
        return f"alerts={len(alerts)} merged={len(merged)} ack/dismiss ok"

    check("E1 smart alerts + dedupe + export", alerts_check)

    # ---- F. Segmentation with independent RFM verification -------------------
    def segmentation_check():
        seg = segment_customers(frame, schema_holder["schema"], max_clusters=4)
        assert seg.available, seg.notes
        assert seg.rfm["customer_id"].is_unique
        # Independent RFM recomputation
        work = frame.copy()
        work["Order Date"] = pd.to_datetime(work["Order Date"])
        snapshot = work["Order Date"].max() + pd.Timedelta(days=1)
        manual = work.groupby("Customer ID").agg(
            recency_manual=("Order Date", lambda s: (snapshot - s.max()).days),
            frequency_manual=("Order ID", "nunique"),
            monetary_manual=("Revenue", "sum"),
        )
        merged = seg.rfm.set_index("customer_id").join(manual.rename_axis("customer_id"))
        rec_diff = (merged["recency_days"] - merged["recency_manual"]).abs().max()
        freq_diff = (merged["frequency"] - merged["frequency_manual"]).abs().max()
        mon_diff = (merged["monetary_value"] - merged["monetary_manual"]).abs().max()
        assert rec_diff == 0, f"recency mismatch {rec_diff}"
        assert freq_diff == 0, f"frequency mismatch {freq_diff}"
        assert mon_diff < 0.01, f"monetary mismatch {mon_diff}"
        assert set(seg.rfm["segment"]).issubset({
            "Loyal Customers", "Big Spenders", "Potential Loyalists",
            "New Customers", "At-Risk Customers", "Churn Risk Customers",
        })
        assert isinstance(seg.to_csv_bytes(), bytes) and len(seg.to_csv_bytes()) > 0
        assert isinstance(seg.to_excel_bytes(), bytes) and len(seg.to_excel_bytes()) > 0
        return (f"k={seg.k} silhouette={seg.silhouette} customers={len(seg.rfm)} "
                f"rfm_max_diff={max(rec_diff, freq_diff, mon_diff):.4f}")

    check("F1 segmentation RFM math verified", segmentation_check)

    # ---- G. Inventory formulas verified against hand math --------------------
    def inventory_check():
        inv = build_inventory(seed=11)
        schema = infer_schema(inv)
        res = build_inventory_recommendations(
            inv, schema, lead_time_days=7, safety_days=7, service_level=0.95,
            history_window=28, target_cover_days=14, method="Moving average",
        )
        assert res.available, res.notes
        assert res.stock_available, "stock column not detected"
        row = res.table.iloc[0]
        # Constant demand 10/day -> std=0 -> safety = forecast_daily * safety_days = 70
        assert abs(row["forecast_daily_demand"] - 10.0) < 1e-6, row["forecast_daily_demand"]
        assert abs(row["safety_stock"] - 70.0) < 1e-6, row["safety_stock"]
        assert abs(row["reorder_point"] - (10 * 7 + 70)) < 1e-6, row["reorder_point"]
        expected_suggested = (10 * 7 + 70) + 10 * 14 - 200
        assert abs(row["suggested_reorder_quantity"] - expected_suggested) < 1e-6, row["suggested_reorder_quantity"]
        assert abs(row["days_remaining"] - 20.0) < 1e-6, row["days_remaining"]
        return (f"avg_daily={row['avg_daily_sales']} safety={row['safety_stock']} "
                f"ROP={row['reorder_point']} suggest={row['suggested_reorder_quantity']} "
                f"days_left={row['days_remaining']} status={row['status']}")

    check("G1 inventory formulas verified", inventory_check)

    # ---- H. Forecasting ------------------------------------------------------
    def forecast_check():
        series, notes = prepare_series(frame, schema_holder["schema"], "revenue", frequency="Monthly")
        assert not series.empty, notes
        result = forecast_dataset(frame, schema_holder["schema"], metric_role="revenue",
                                  frequency="Monthly", periods=3, method="Auto (backtest)")
        assert result.available, f"available=False notes={result.notes}"
        assert result.train_size > 0 and result.test_size > 0, (result.train_size, result.test_size)
        assert set(result.metrics) == {"mae", "rmse", "mape"}, result.metrics
        assert result.metrics["mae"] is not None, result.metrics
        assert (result.forecast["lower_bound"] <= result.forecast["forecast"]).all(), result.forecast
        assert (result.forecast["forecast"] <= result.forecast["upper_bound"]).all(), result.forecast
        # Metric definitions verified independently
        m = _metrics(np.array([10.0, 20.0]), np.array([8.0, 25.0]))
        assert abs(m["mae"] - 3.5) < 1e-9
        assert abs(m["rmse"] - math.sqrt((4 + 25) / 2)) < 1e-9
        assert abs(m["mape"] - ((2 / 10 + 5 / 20) / 2) * 100) < 1e-9
        # Insufficient data warning (five consecutive days only)
        short = frame.copy()
        short["Order Date"] = pd.to_datetime(short["Order Date"])
        short = short.sort_values("Order Date").head(5).copy()
        short["Order Date"] = pd.date_range("2023-01-01", periods=5, freq="D").strftime("%Y-%m-%d")
        short_res = forecast_dataset(short, infer_schema(short), metric_role="revenue", frequency="Daily")
        assert not short_res.available and short_res.notes, (short_res.available, short_res.notes)
        return (f"method={result.method} MAE={result.metrics['mae']:.2f} "
                f"RMSE={result.metrics['rmse']:.2f} MAPE={result.metrics['mape']:.2f}")

    check("H1 forecasting + metrics + intervals", forecast_check)

    # ---- J. Business insights ------------------------------------------------
    def insights_check():
        insights = generate_insights(frame, schema_holder["schema"], max_items=8)
        assert insights, "no insights"
        text = " ".join(i.text for i in insights)
        assert any(ch.isdigit() for ch in text), "no numeric evidence"
        return f"insights={len(insights)} first='{insights[0].title}'"

    check("J1 insights with factual evidence", insights_check)

    # ---- K. Power BI ---------------------------------------------------------
    def powerbi_check():
        project = build_pbip(frame, schema_holder["schema"], project_name="Audit Report")
        errors = validate_pbip(project)
        assert not errors, errors
        names = set(project.files)
        assert any(n.endswith(".pbip") for n in names), sorted(names)[:10]
        assert any(n.endswith("database.tmdl") for n in names)
        assert any("tables/" in n and n.endswith(".tmdl") for n in names)
        assert any(n.endswith("report.json") for n in names)
        assert any(n.endswith(".pbir") for n in names)
        zip_bytes = project.to_zip_bytes()
        assert zip_bytes[:2] == b"PK"
        joined = "\n".join(project.files.values())
        assert "Total Sales" in joined and "Profit Margin" in joined
        return f"files={len(names)} tables={project.tables} measures={project.measures} zip={len(zip_bytes)}B"

    check("K1 PBIP structure + validation", powerbi_check)

    # ---- L. Exports ----------------------------------------------------------
    def exports_check():
        schema = schema_holder["schema"]
        bundle = executive_pdf(
            frame, schema,
            filename="data.csv",
            filters={"Region": "All"},
            insights=generate_insights(frame, schema, max_items=5),
        )
        assert bundle.data[:4] == b"%PDF", bundle.data[:8]
        assert bundle.mime == "application/pdf"
        bundle2 = business_analysis_pdf(
            frame, schema,
            filename="data.csv",
            insights=generate_insights(frame, schema, max_items=5),
        )
        assert bundle2.data[:4] == b"%PDF", bundle2.data[:8]
        csv_bytes = dataframe_to_csv_bytes(frame)
        assert csv_bytes.startswith(b"\xef\xbb\xbf")
        xlsx = workbook_bytes({"Data": frame})
        assert xlsx[:2] == b"PK"
        theme = theme_json_bytes("Audit")
        import json as _json
        assert _json.loads(theme)["name"] == "Audit"
        return (f"exec_pdf={len(bundle.data)}B biz_pdf={len(bundle2.data)}B "
                f"csv={len(csv_bytes)}B xlsx={len(xlsx)}B theme ok")

    check("L1 CSV/Excel/PDF/theme exports", exports_check)

    # ---- D. Chat numeric grounding ------------------------------------------
    def chat_check():
        schema = schema_holder["schema"]
        question = "What is the total revenue?"
        intent = parse_question(question, schema, frame)
        response = answer_question(question, frame, schema, provider=None)
        text = response.text
        expected = float(frame["Revenue"].sum())
        # find the formatted number in the answer
        digits = "".join(ch if (ch.isdigit() or ch in ".,") else " " for ch in text)
        numbers = []
        for token in digits.split():
            token = token.strip(".,")
            if token:
                try:
                    numbers.append(float(token.replace(",", "")))
                except ValueError:
                    pass
        assert numbers, f"no numeric answer in: {text[:200]}"
        assert any(abs(n - expected) <= max(1.0, expected * 1e-6) for n in numbers), (
            f"expected ~{expected:.2f}, got {numbers[:5]}"
        )
        return f"question='{question}' answer='{text[:90]}'"

    check("D1 chatbot numeric answer grounded in pandas", chat_check)

    # ---- D2. RAG retrieval with citations ------------------------------------
    def rag_check():
        store = RAGStore()
        doc = (
            "Quarterly Operations Memo\n\n"
            "Our flagship product is the Aurora Widget. The Aurora Widget generated "
            "1,250,000 dollars of revenue in Q3 2023, which was 24 percent above the target.\n\n"
            "Supplier lead times for the Aurora Widget average 12 days. Safety stock policy "
            "requires 21 days of cover for all flagship products.\n\n"
            "The returns rate for the Aurora Widget was 1.8 percent, below the 3 percent threshold.\n"
        ).encode("utf-8")
        n = store.add_document("ops_memo.txt", doc, provider=None)
        assert n >= 1, "no chunks"
        answer = store.answer("What was the revenue of the Aurora Widget in Q3?", provider=None)
        assert answer.sources, "no citations"
        assert "1,250,000" in answer.text or "1250000" in answer.text, answer.text
        assert any("ops_memo.txt" == s.doc_name for s in answer.sources)
        return f"chunks={n} sources={len(answer.sources)} answer='{answer.text[:70]}'"

    check("D2 RAG retrieval with source citations", rag_check)

    # ---- Summary -------------------------------------------------------------
    print("\n" + "=" * 70)
    passed = sum(1 for _a, s, _d in RESULTS if s == "PASS")
    failed = sum(1 for _a, s, _d in RESULTS if s == "FAIL")
    print(f"SUMMARY: {passed} passed, {failed} failed, {len(RESULTS)} checks")
    for area, status, detail in RESULTS:
        if status == "FAIL":
            print(f"  FAILED: {area} -> {detail}")
    print("=" * 70)


if __name__ == "__main__":
    main()