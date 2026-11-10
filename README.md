# RetailMind AI

**Intelligent Universal Business Analytics Platform — Phase 2**

> Understand Your Business. Predict Your Future. Grow Smarter.

RetailMind AI turns structured business data — retail sales, finance, HR, education, operations, or a custom export — into an interactive analytics workspace inside Streamlit. Upload a CSV or Excel workbook, review cleaning suggestions, confirm semantic mapping, and use auto-generated dashboards, alerts, segmentation, inventory recommendations, forecasting, document Q&A, and exports.

No login, external database, AI API key, or SMTP server is required for the core experience.

---

## Current verification status

Independently audited on 8 November 2026 (Windows, Python 3.14.2, pandas 3.0.6):

| Check | Result |
|:---|:---|
| Full regression suite | **295 passed, 3 skipped, 0 failed** |
| Functional audit (`audit_functional.py`) | **12/12** |
| Multi-domain/edge audit (`audit_domains_perf.py`) | **11/11** |
| UI audit (`audit_ui.py`) | **9/9** |

**Not verified here:** Power BI Desktop compatibility, real SMTP delivery, ARIMA (`statsmodels` absent), live LLM generation (no key), browser E2E (Playwright skipped).

See [`OPENCODE_INDEPENDENT_AUDIT.md`](OPENCODE_INDEPENDENT_AUDIT.md) for the full evidence and corrected claims.

---

## Features

| Capability | Details | Status |
|:---|:---|:---|
| Universal upload & schema inference | CSV/XLSX/XLS/XLSM up to 25 MB; retail, finance, HR, education, e-commerce and generic roles | ✅ Verified |
| Transparent cleaning | Reviewable suggestions; non-destructive by default; opt-in duplicate/empty-row removal | ✅ Verified |
| Auto dashboards | Up to 6 pages / 36 components on a retail dataset; builder with add/edit/move/delete/undo/redo | ✅ Verified |
| Deterministic chatbot | Pandas-grounded numeric answers with verification flags | ✅ Verified |
| Document Q&A (RAG) | Local hash embeddings, extractive fallback, source citations | ✅ Verified |
| Smart alerts | Revenue/margin/outlier/stock rules, severity/status filters, acknowledge/dismiss, CSV | ✅ Verified (SMTP not live-tested) |
| Customer segmentation | RFM + log scaling + deterministic K-Means, silhouette selection, rule-based churn flag | ✅ Verified |
| Predictive stock | Demand, safety stock, reorder point, target cover, suggested order, depletion date | ✅ Verified |
| Forecasting | Moving average, simple exponential smoothing, linear trend, Auto backtest; optional ARIMA | ✅ Verified (ARIMA needs `statsmodels`) |
| Power BI export | `.pbip` + TMDL + PBIR + theme ZIP, internal validation | ⚠️ Structure verified; Desktop/data-source not |
| Exports | Cleaned CSV/Excel, markdown, executive workbook, executive PDF, business PDF, theme JSON | ✅ Verified |

> **Forecasting note:** exponential smoothing is level-only (simple ES, α grid-searched). It is **not** Holt-Winters. Prediction intervals are approximately ±1.96 × residual σ and do **not** widen with horizon.

---

## Separate Next.js frontend

The React/Next.js application lives in `frontend/`; the original Streamlit entry point and Python analytics modules remain in place. The additive FastAPI adapter in `api.py` calls the existing parser, analytics, forecasting, inventory, segmentation, assistant, RAG, and export code. Database-backed account/session, user-owned upload metadata, preferences, goals, and saved-report metadata use the existing MySQL services.

### Run both applications locally

Run the Python API from the repository root in one terminal:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r api-requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8000
```

Run the web app from `frontend/` in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The Next.js route proxies requests to `http://127.0.0.1:8000` by default. The API reads `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE` from the environment; keep those values out of source control. Before using accounts, apply the existing authentication, upload, and session SQL files (`sql/04_authentication_tables.sql`, `sql/05_persistent_user_uploads.sql`, and `sql/06_owner_admin_and_sessions.sql`) deliberately to the intended database. No migration runs automatically, and the first owner-admin assignment is intentionally not exposed as a public registration/API action.

Uploads use user-scoped metadata and a private filesystem store. Set `RETAIL_UPLOAD_STORAGE_DIR` to a durable, private volume for deployments; do not use ephemeral serverless disk for business files. RAG indexes are held in API-process memory and need to be rebuilt after an API restart. Saved report rows retain configuration/metadata, not exported file copies. The owner/security pages require an assigned owner account. Use `RETAILMIND_API_URL` when the API is hosted separately; `RETAILMIND_API_TOKEN` can add service-to-service bearer protection. Keep the API private behind the same-origin frontend proxy in production. The original Streamlit app remains available as a separate fallback.

## Quick start (Windows)

```powershell
cd "C:\Users\ak837\OneDrive\Desktop\Retail-Sales-Profitability-Analysis (1)\Retail-Sales-Profitability-Analysis"

.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run dashboard.py
```

Open `http://localhost:8501` and drag in a CSV or Excel file.

---

## Testing

Use a project-local temp directory. On this machine the default pytest temp path is not writable (`PermissionError: [WinError 5]`), which is an environment issue, not an app defect.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp=./tmp_pytest_final --tb=short
```

Latest workspace run: **296 passed, 6 skipped**. Skips: browser E2E (requires a Playwright browser), XLS/XLSM fixture generation (requires `xlwt`), optional-dependency absence checks (the PDF/DOCX readers are installed), and live MySQL integration (requires a disposable database).

Independent audit scripts:

```powershell
.\.venv\Scripts\python.exe audit_functional.py
.\.venv\Scripts\python.exe audit_domains_perf.py
.\.venv\Scripts\python.exe audit_ui.py
.\.venv\Scripts\python.exe audit_benchmark.py
```

---

## Performance (honest summary)

Median of 3 runs on synthetic retail data (`audit_benchmark.py`; full results in `benchmark_results.json`):

| Stage | 100k rows |
|:---|---:|
| Schema inference | 0.19 s |
| Cleaning | 1.24 s |
| Alerts | 2.26 s |
| Segmentation | 1.10 s |
| Inventory | 1.59 s |
| Core pipeline (schema+clean+dashboard+alerts+insights) | **3.95 s** |
| Full run incl. CSV parse + PDF | **≈8.5 s** |
| Traced peak memory | 103.4 MB |

At 250k rows the core pipeline is ≈10.0 s. The earlier “sub-2.2 s at 100k” claim is not reproducible on this hardware.

**Responsiveness after this repair (Streamlit AppTest reruns, 20k rows):** cold upload 30.8 s → 17.3 s; warm rerun 3.36 s → 1.70 s; page navigation ≈3.2 s → ≈1.6 s. All six dashboard pages and all 17 download buttons now render and click without errors.

See [`PERFORMANCE_REPORT.md`](PERFORMANCE_REPORT.md).

---

## Architecture

```
dashboard.py                       Streamlit application entrypoint & canvas
data_sources.py                    File reading, profiling, mapping helpers
retailmind/
  alerts.py                        Smart alerts, anomaly rules, SMTP notifications
  segmentation.py                  RFM, log transforms, deterministic K-Means, silhouette
  inventory.py                     Lead time, safety stock, ROP, target cover
  forecasting.py                   Moving average, simple exp smoothing, linear trend, ARIMA (optional)
  powerbi.py                       Star schema decomposition, TMDL model, PBIR reports, PBIP ZIP
  exports.py                       Executive/business PDFs, multi-sheet Excel, theme JSON
  schema.py                        Schema inference, role aliases, domain detection
  cleaning.py                      Reviewable cleaning suggestions and safe transformations
  engine.py                        Visual builder and auto-layout generator
  models.py                        Component/Page/Theme/Dashboard data models
  render.py                        KPI, chart and table rendering
  filters.py                       Multi-column filters and free-text search
  storage.py                       Local JSON persistence, autosave, undo/redo
  insights_engine.py               Statistical insight calculations
  ui.py                            CSS, SVG logo, branding, theme injection
  ai/
    chat.py                        Pandas-verified business chatbot
    assistant.py                   Allowlisted natural-language dashboard actions
    insights.py                    Deterministic factual insights
    rag.py                         Local embeddings, chunking, cited document Q&A
```

---

## Known limitations

1. **Power BI:** the PBIP has no embedded data or `FactSales` partition, and was not opened in Desktop. Connect a source and save as `.pbix` manually.
2. **SMTP:** email sending needs a configured server; only mocked tests exist.
3. **ARIMA/SARIMA:** requires the optional `statsmodels` package.
4. **LLM provider:** optional; deterministic fallbacks are the verified path. No streaming API.
5. **Forecasting:** no seasonality; intervals are approximate and constant-width.
6. **Churn:** rule-based flag, not a trained predictive model.
7. **Warnings:** Streamlit emits `use_container_width` deprecation warnings.

---

## Documentation

- [Independent Audit](OPENCODE_INDEPENDENT_AUDIT.md)
- [Phase 1 Repair Report](PHASE1_REPAIR_REPORT.md)
- [Phase 2 Progress](PHASE2_PROGRESS.md)
- [Phase 2 Delivery Report](PHASE2_DELIVERY_REPORT.md)
- [Performance Report](PERFORMANCE_REPORT.md)
- [Button & Interaction Audit](BUTTON_AUDIT_REPORT.md)
- [Power BI Export Guide](POWER_BI_EXPORT_GUIDE.md)
- [ML & Statistical Model Guide](ML_MODEL_GUIDE.md)
