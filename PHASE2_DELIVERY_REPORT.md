# RetailMind AI — Phase 2 Delivery Report

**Version:** 2.0.0-phase2
**Delivery date:** 8 November 2026
**Status:** Delivered — independently audited, with limitations stated

---

## 1. Executive summary

RetailMind AI is a working Streamlit analytics platform. It accepts CSV/Excel uploads, infers semantic roles across domains, cleans data transparently, generates dashboards, answers numeric questions with pandas, retrieves cited answers from documents, and adds Phase-2 features for alerts, segmentation, inventory, forecasting, and Power BI export.

**What was independently verified**
- Full regression suite: **295 passed, 3 skipped, 0 failed** (298 collected, 144 s).
- `audit_functional.py`: **12/12** checks with hand-computed expected values.
- `audit_domains_perf.py`: **11/11** schema/edge checks.
- `audit_ui.py`: **9/9** Streamlit interaction checks for Phase-2 panels.
- Genuine exports: PDF (`%PDF` + expected text), XLSX (openable), CSV, ZIP, theme JSON.
- Chatbot answer matched a direct pandas computation; RAG cited the correct document.

**What is not verified**
- Power BI Desktop compatibility (Desktop not installed).
- Real SMTP delivery.
- ARIMA/SARIMA (`statsmodels` absent).
- Live LLM generation (no API key).
- Browser end-to-end (Playwright browser absent).

**What was corrected**
- A real schema bug mis-mapped `Product Category` to the `product` role; e-commerce datasets were classified `generic`. Fixed and verified (`domain=commerce`).
- The prior performance report’s “2.18 s at 100k rows” and “258 tests in 63.67 s” were not reproducible. Honest numbers are in `PERFORMANCE_REPORT.md` (~3.95 s core pipeline at 100k).
- The ML guide described Holt-Winters and growing intervals; the code implements **simple** exponential smoothing and constant-width intervals. Corrected in `ML_MODEL_GUIDE.md`.
- PBIP export is structurally valid but contains **no data source/partitions**; it must be connected before visuals populate. Corrected in `POWER_BI_EXPORT_GUIDE.md`.

---

## 2. Delivered components

| Component | File | Status |
|:---|:---|:---|
| Streamlit entrypoint & UI | `dashboard.py`, `retailmind/ui.py` | ✅ Working |
| Universal schema inference | `retailmind/schema.py` | ✅ Working (fixed) |
| Profiling & ingestion | `data_sources.py` | ✅ Working |
| Cleaning engine | `retailmind/cleaning.py` | ✅ Working |
| Dashboard engine & models | `retailmind/engine.py`, `models.py` | ✅ Working |
| Filters & search | `retailmind/filters.py` | ✅ Working |
| Persistence & undo/redo | `retailmind/storage.py` | ✅ Working |
| Smart alerts | `retailmind/alerts.py` | ✅ Working (SMTP not live-tested) |
| Segmentation | `retailmind/segmentation.py` | ✅ Working |
| Inventory | `retailmind/inventory.py` | ✅ Working |
| Forecasting | `retailmind/forecasting.py` | ✅ Working (ARIMA optional, absent) |
| Power BI export | `retailmind/powerbi.py` | ⚠️ Structure validated against Microsoft's published PBIP/PBIR schemas; Desktop/data-source unverified |
| Reports & exports | `retailmind/exports.py`, `retailmind/utils.py` | ✅ Working |
| Chatbot / assistant / RAG | `retailmind/ai/` | ✅ Deterministic paths; LLM untested |
| Optional auth / MySQL | `src/auth/`, MySQL helpers | Not exercised (app runs without them) |

---

## 3. Phase 2 features

### 3.1 AI smart alerts
- Statistical/rule alerts for revenue decline, outliers, margin erosion, expense changes, and stock risk where columns exist.
- Severity/status filters, acknowledge/dismiss, CSV export.
- **Verified in UI:** a click changed persisted alert state; 2 acknowledge and 2 dismiss buttons rendered.
- **Limitation:** SMTP email requires server credentials; only mocked tests exist.

### 3.2 Customer segmentation
- RFM with snapshot `max(date)+1`, log1p + standard scaling, deterministic K-Means++ (`seed=42`, `n_init=10`), silhouette model selection (sampled ≤1,500).
- Behavioural labels and a transparent rule-based churn flag.
- **Verified:** RFM recomputed independently with `max_diff = 0.0000`; CSV/Excel exports present.

### 3.3 Predictive stock
- Mean/recent demand, safety stock (`Z·σ·√L` when variance exists, days-of-cover fallback otherwise), ROP, target cover, suggested order, days remaining, depletion date, status.
- **Verified:** constant-demand scenario matched hand math exactly.

### 3.4 Forecasting
- Moving average, simple exponential smoothing (α grid), linear trend, optional ARIMA; Auto selects by hold-out MAE.
- Time-based 80/20 split; refit on full history; MAE/RMSE/MAPE; approximate constant-width 95% intervals.
- **Verified:** metric formulas and output ranges matched independent calculations.

### 3.5 Power BI export
- Generates `.pbip`, TMDL semantic model, PBIR pages/visuals and theme; internal validator passes.
- **Observed:** 34 files, 6 tables, 14 measures on a retail dataset.
- **Not verified:** opening in Desktop; the archive has no data files or `FactSales` partition.

### 3.6 Exports
- Cleaned CSV/Excel, executive markdown, multi-sheet Excel workbook, executive PDF, business analysis PDF, theme JSON, PBIP ZIP.
- **Verified:** payload signatures and reopenability (CSV/XLSX/ZIP); PDFs contain expected text.

---

## 4. Verification evidence

```
audit_functional.py    12 passed, 0 failed
audit_domains_perf.py  11 passed, 0 failed
audit_ui.py             9 passed, 0 failed
pytest tests/         295 passed, 3 skipped, 0 failed (144.09s)
```

Workaround required for pytest on this machine:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp=./tmp_pytest_final --tb=short
```

The default temp path raises `PermissionError`; this is environmental, not an app defect.

---

## 5. Performance summary

| Scenario | 100k rows |
|:---|---:|
| Schema inference | 0.19 s |
| Cleaning | 1.24 s |
| Alerts | 2.26 s |
| Segmentation | 1.10 s |
| Inventory | 1.59 s |
| Core pipeline | 3.95 s |
| Full run incl. CSV + PDF | ≈8.5 s |
| Traced peak memory | 103.4 MB |

At 250k rows the core pipeline is ≈10.0 s. See `PERFORMANCE_REPORT.md`.

---

## 6. Known limitations

1. No `.pbix`; PBIP requires Desktop + a connected data source.
2. No seasonal forecasting; intervals are approximate and constant-width.
3. ARIMA requires an optional package.
4. Churn flag is a rule, not a trained classifier.
5. SMTP and live LLM paths are unverified.
6. Browser E2E test is skipped.
7. Streamlit emits `use_container_width` deprecation warnings.

---

## 7. Run instructions

```powershell
cd "C:\Users\ak837\OneDrive\Desktop\Retail-Sales-Profitability-Analysis (1)\Retail-Sales-Profitability-Analysis"
.\.venv\Scripts\Activate.ps1
streamlit run dashboard.py
```

Open `http://localhost:8501`, upload a CSV/Excel file (≤25 MB), and use the sidebar filters and the Advanced Business Intelligence tabs.

No login, API key, database, or SMTP server is required for the core experience.
