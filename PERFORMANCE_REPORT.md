# RetailMind AI — Performance Report (Independent Re-benchmark)

**Version:** 2.0.0-phase2
**Date:** 8 November 2026
**Status:** Measured on the audit machine; supersedes the earlier optimistic claims

---

## 1. Executive summary

RetailMind AI is usable and responsive on datasets up to 100,000 rows, but the earlier claim of a **sub-2.2-second full pipeline at 100k rows is not reproducible** on this machine. The honest figures are:

- **Schema inference:** ~195 ms at 100k rows (bounded by a 5,000-value sample).
- **Core pipeline** (schema + cleaning + dashboard + alerts + insights): **3.95 s** at 100k rows.
- **Full one-shot run** including CSV parse and PDF generation: **≈8.5 s** at 100k rows.
- **At 250k rows:** core pipeline **10.0 s**; traced peak memory **103 MB**.
- The dominant costs are **alerts**, **cleaning**, **inventory** and **segmentation**, all of which scale roughly linearly with row count.

The audit also removed a genuine bottleneck: schema inference was ~1,312 ms at 100k before the fix and is now ~195 ms (**≈6.7× faster**).

No mock data, cached results, or fabricated timings were used.

---

## 2. Method

- Script: `audit_benchmark.py` (kept in the repository).
- **Median of 3 runs** per stage (2 runs for the composite pipeline; 1 run for dashboard/PDF, which are effectively constant-time).
- `tracemalloc` is **not** active during timing loops; memory is measured in a separate pass and labelled as traced peak.
- Datasets are synthetic but realistic: `customers = max(100, rows/120)`, `products = max(50, rows/400)`, 14 columns (including `Current Stock`, `Lead Time`), dates spanning 2022–2024.
- Raw results: `benchmark_results.json`.
- Environment: Windows, Python 3.14.2, pandas 3.0.6, NumPy 2.5.4.

Reproduce:

```powershell
.\.venv\Scripts\python.exe audit_benchmark.py
```

---

## 3. Results (milliseconds unless stated)

| Stage | 10,000 | 50,000 | 100,000 | 250,000 |
|:---|---:|---:|---:|---:|
| CSV size (MB) | 0.9 | 4.4 | 8.8 | 22.1 |
| CSV parse | 15.8 | 229.9 | 350.5 | 1,126.9 |
| Schema inference | 49.2 | 203.9 | 194.5 | 203.0 |
| Profiling | 16.0 | 189.0 | 382.0 | 545.1 |
| Cleaning | 57.9 | 661.4 | 1,240.3 | 2,665.1 |
| Auto dashboard | 0.2 | 0.6 | 0.6 | 0.6 |
| Smart alerts | 103.8 | 977.7 | 2,263.2 | 5,567.7 |
| Customer segmentation | 45.5 | 495.8 | 1,095.4 | 2,514.7 |
| Business insights | 12.1 | 106.4 | 179.9 | 396.7 |
| Forecasting (monthly) | 9.0 | 75.5 | 140.8 | 334.5 |
| Inventory recommendations | 85.4 | 779.4 | 1,595.0 | 3,804.1 |
| PBIP generation | 1.2 | 5.6 | 4.8 | 4.4 |
| Executive PDF | 131.6 | 170.9 | 208.7 | 526.2 |
| Chatbot answer | 4.0 | 49.0 | 83.3 | 262.6 |
| **Core pipeline** | **212.4** | **2,206.3** | **3,946.6** | **9,986.9** |

Core pipeline = schema inference + cleaning + dashboard build + alerts + insights. It excludes CSV parsing and PDF export.

### Derived end-to-end estimates

| Scenario | 100k rows |
|:---|---:|
| CSV parse + core pipeline | ≈4.30 s |
| + PDF export | ≈4.51 s |
| + segmentation + inventory + forecast + PBIP | ≈7.77 s |
| + insights duplicated in PDF path (observed full audit run) | ≈8.5 s |

---

## 4. Memory

| Metric | Value |
|:---|:---|
| Traced peak, 100k-row analysis pass | **103.4 MB** |
| CSV size at 100k rows | 8.8 MB |
| CSV size at 250k rows | 22.1 MB |

`tracemalloc` inflates memory use and is not equivalent to process RSS. The earlier claim of “below 75 MB” could not be reproduced; treat 100k as roughly **100 MB of traced allocations** under this workload.

---

## 5. Optimizations applied during this audit

### 5.1 Schema inference
- Date/numeric detection now uses a **≤5,000 non-null value sample**.
- Numeric/bool columns no longer attempt date parsing.
- Date regex is non-capturing (`(?:19|20)`), removing a pandas warning.
- `nunique` is computed once per column.
- **Measured:** ~1,312 ms → ~195 ms at 100k rows.

### 5.2 Profiling
- `profile_schema` reuses the same bounded sample instead of scanning all rows for type heuristics. Exact statistics (sum/min/max/missing) still come from the full frame in `profile_report`.

### 5.3 Cleaning fast paths
- `_blank_mask` returns `isna()` immediately for non-text dtypes.
- Whitespace trimming computes stripped values once and compares them once.

- `dashboard.py` uses `@st.cache_data` for file reads and session-state memoisation keyed by dataset identity + cleaning signature. Measured end-to-end with Streamlit `AppTest` (full script reruns, 20k rows):

| Interaction | Before lazy exports | After lazy exports |
|:---|---:|---:|
| Upload, first render (cold) | 30,773 ms | 17,270 ms |
| Warm rerun, no interaction | 3,355 ms | 1,699 ms |
| Page navigation (each tab) | ≈3,200 ms | ≈1,600 ms |
| Download clicked (+ rerun) | 3,093 ms | 1,589 ms |
| Switch to Customize Dashboard | 3,269 ms | 1,619 ms |
| Dashboard builder action | 3,644 ms | 2,083 ms |

(500 rows: warm rerun 1,533 ms → 904 ms; navigation ≈1,500 ms → ≈1,000 ms.)
These are full Streamlit script reruns and therefore include Streamlit overhead; they are honest end-to-end figures, not raw pipeline stage timings. KPIs and all computations still use complete valid data — nothing was truncated, sampled for calculation, or replaced with mock data.

### 5.5 Result
Warm reruns and page navigation are roughly halved at 20k rows; cold upload is ~44% faster. The dominant remaining costs are linear-in-rows stages (alerts, cleaning, inventory, segmentation), which now run once per dataset/filter combination and are reused across reruns.


---

## 6. Scalability observations

- **Schema inference is effectively flat** from 50k to 250k because of sampling.
- **Alerts** are the most expensive stage: each check aggregates across the filtered frame and compares periods.
- **Cleaning** and **inventory** grow linearly and are the next largest.
- **Segmentation** depends on customer cardinality; this benchmark intentionally raises customer count with row count, which is a harder workload than a fixed customer base.
- **Dashboard generation is O(1)** with respect to rows (configuration only).
- **PBIP generation is metadata-bound** and flat (~1–6 ms).
- At 250k rows the app remains functional but an interactive rerun performs several seconds of work unless results are cached.

---

## 7. Corrections to the previous report

| Previous claim | Independent result |
|:---|:---|
| Schema inference 497.7 ms at 100k | **194.5 ms** after fixes (before fixes: ~1,312 ms) |
| Cleaning 657.6 ms at 100k | **1,240.3 ms** |
| Alerts 213.0 ms at 100k | **2,263.2 ms** |
| Segmentation 187.7 ms at 100k | **1,095.4 ms** |
| Inventory 227.2 ms at 100k | **1,595.0 ms** |
| Forecasting 27.0 ms at 100k | **140.8 ms** |
| End-to-end 2.18 s at 100k | **≈3.95 s core**, **≈8.5 s including CSV + PDF** |
| Peak memory below 75 MB | **103.4 MB traced** at 100k |
| “400% improvement” | Not reproduced as a single claim; schema inference alone improved ~6.7× |

Differences may partly reflect dataset shape (the original benchmark dataset is not included with the timing script), but they cannot be reconciled with the claimed end-to-end time under this workload.

---

## 8. Recommendations

1. Cache alerts, segmentation, inventory and forecast results per dataset/filter signature (they are deterministic).
2. Avoid recomputing all alerts on every Streamlit rerun; compute on demand or invalidate by filter hash.
3. Consider vectorising the alert period comparisons for large frames.
4. Keep the 25 MB upload guard; 250k-row frames already take ~10 s for the core pipeline.
5. Re-run `audit_benchmark.py` on the deployment hardware before publishing any SLA.
