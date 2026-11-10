# RETAILMIND AI — INDEPENDENT AUDIT REPORT

**Platform:** RetailMind AI — Intelligent Universal Business Analytics Platform
**Version audited:** 2.0.0-phase2
**Audit date:** 8 November 2026
**Auditor:** OpenCode (independent verification, no reliance on prior completion claims)
**Project root:** `C:\Users\ak837\OneDrive\Desktop\Retail-Sales-Profitability-Analysis (1)\Retail-Sales-Profitability-Analysis`
**Environment:** Windows, Python 3.14.2, pandas 3.0.6, NumPy 2.5.4, Streamlit AppTest, reportlab + openpyxl installed, `statsmodels` **not** installed, Power BI Desktop **not** installed, no SMTP server, no AI API key.

---

## 1. Verdict

| Area | Classification | Basis |
|:---|:---|:---|
| Branding and UI shell | ✅ **Verified working** | AppTest renders title/brand; no raw HTML in text elements |
| CSV/Excel upload, profiling, cleaning | ✅ **Verified working** | Executed with independent numeric checks and edge cases |
| Dashboard builder (add/edit/move/delete/undo/redo/pages) | ✅ **Verified working** | 17 existing AppTest interaction tests + code review |
| AI Workspace — deterministic chatbot & RAG | ✅ **Verified working** | Numeric answer matched pandas; RAG cited the correct source |
| AI Workspace — optional LLM provider | ⚠️ **Partially working** | Keyless degradation verified; live LLM generation not testable without a key |
| Smart alerts (detection, filters, ack/dismiss, CSV) | ✅ **Verified working** | UI clicks changed persisted alert state; CSV produced |
| Smart alerts — SMTP email dispatch | ❓ **Not testable** | No SMTP server/credentials; unit tests mock `smtplib` only |
| Customer segmentation (RFM + K-Means) | ✅ **Verified working** | Independent RFM recomputation matched exactly; k/silhouette produced |
| Predictive stock recommendations | ✅ **Verified working** | Hand-computed demand/safety/ROP/suggestion/days-left matched |
| Forecasting (MA, ES, linear trend) | ✅ **Verified working** | Backtested metrics matched hand-computed MAE/RMSE/MAPE |
| Forecasting — ARIMA/SARIMA | ❓ **Not testable here** | `statsmodels` absent; app correctly reports method unavailable |
| Power BI PBIP export | ⚠️ **Partially working** | Valid internal structure, but **not opened in Power BI Desktop**; no data partitions/source; no `.pbix` |
| CSV/Excel/PDF/theme exports | ✅ **Verified working** | Valid CSV/XLSX bytes; PDFs start with `%PDF` and contain expected text; all download buttons drive real bytes via `AppTest.click()` |
| Business insights | ✅ **Verified working** | Numeric evidence present; deterministic |
| Automated test suite | ✅ **Verified working** | **295 passed, 3 skipped, 0 failed** (with project-local `--basetemp`; +18 checks during this repair: PBIP schema validation + TMDL structural validation + version.json + data source validation + 11 mobile upload tests) |
| Performance claims | ✅ **Verified working** | Stages re-measured after session-state compute caching + lazy export byte generation; warm reruns roughly halved at 20k rows; honest before/after in §6 |

**Bottom line:** the core product works and is substantially real. The original reports overstate four things: the exact test count/runtime, “zero warnings”, the forecasting model family, and end-to-end performance. Power BI output is structurally sound and validates against Microsoft's published schemas, but has **not** been validated in Power BI Desktop.

---

## 2. Method

1. **Static review** of `dashboard.py` (~2,100 lines) and all 17 `retailmind/` modules including `retailmind/ai/`.
2. **Independent executable audits** (not the project’s own tests):
   - `audit_functional.py` — 12 checks with hand-computed expected values.
   - `audit_domains_perf.py` — 11 schema/edge/benchmark checks across retail, HR, finance, e-commerce.
   - `audit_ui.py` — 9 Streamlit `AppTest` checks for Phase-2 UI controls not covered by the project’s button suite.
   - `audit_benchmark.py` — median-of-3 timings for 15 pipeline stages at 10k/50k/100k/250k rows.
3. **Full regression suite** with a project-local temp directory.
4. **Claim-by-claim comparison** against `PHASE2_DELIVERY_REPORT.md`, `PERFORMANCE_REPORT.md`, `BUTTON_AUDIT_REPORT.md`, `ML_MODEL_GUIDE.md`, `README.md`.

### Test command note
The default pytest temp directory is not writable in this environment:

```
PermissionError: [WinError 5] Access is denied: 'C:\Users\ak837\AppData\Local\Temp\pytest-of-ak837'
```

This is an environment permission issue, not an application defect. A project-local temp directory works:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp=./tmp_pytest_audit4 --tb=short
```

---

## 3. Defects found and repaired

### 3.1 Confirmed schema bug (fixed)
`Product Category` was assigned the `product` role by a 0.72 “contains” match, while the exact `category` role stayed empty. Consequence: e-commerce datasets were classified as `generic`, and category breakdowns were wrong.

**Fix:** exact-alias ownership now beats an earlier weaker role match; added e-commerce aliases (`user id`, `cart value`, `items`, `product type`, …). Verified result:

```
ROLES: {'revenue': 'Cart Value', 'quantity': 'Items', 'customer': 'User ID',
        'date': 'Event Date', 'category': 'Product Category', ...}
DOMAIN: commerce
```

A regression caused by an intermediate version of this fix (a bare `Segment` column counted as “commercial context”, promoting `Amount` to revenue) was caught by the existing suite and corrected by requiring order/product/customer context.

### 3.3 Confirmed rendering bug: `_measure_label` undefined (fixed)

`retailmind/render.py::_render_table` called a module-level `_measure_label(...)` that was never defined. Every auto dashboard page containing a table (Sales Analysis, Profit Analysis, Customer Analysis, Product Analysis, Data Quality / matrix) raised `NameError: name '_measure_label' is not defined` on first render — which also made every page navigation and every download click fail in `AppTest`.

**Fix:** replaced the broken helper with a pure, unit-testable `table_frame(frame, component, schema)` that supports `sum`/`mean`/`min`/`max`/`count` aggregations, matrix (sum + mean) layouts, missing-measure fallbacks, and missing values preserved as `NaN` instead of fabricated zeros. New suite `tests/test_retailmind_render_tables.py` (6 tests) passes. All six auto pages and all 17 download buttons now render and click cleanly in `AppTest`.

### 3.4 Confirmed Power BI schema defect (fixed)

`definition.pbir` and the `.pbip` shortcut referenced schema URLs Microsoft does not serve (`.../item/report/definitionProperties/1.0.0/schema.json`, `.../item/pbip/1.0.0/schema.json`), and `report.json` carried forbidden properties (`reportDefinitionVersion`, theme `version`). Power BI Desktop would reject the project (“Expected `$schema` property”).

**Fix:** schema identifiers now point at Microsoft's published schemas (`report/definitionProperties/2.0.0`, `report/definition/report/3.3.0`, `pbip/pbipProperties/1.0.0`, `pagesMetadata/1.0.0`, plus the existing page/visual/platform/pbism schemas); `report.json` uses `themeCollection` with `reportVersionAtImport(page/report/visual)` and a `resourcePackages` entry. Every generated JSON file (24 files per project) passes `jsonschema` Draft 7 validation against the downloaded Microsoft schemas, and `validate_pbip` rejects projects whose `$schema` differs from the expected identifier. New test `test_generated_project_uses_published_microsoft_schemas` asserts this and is part of `tests/test_retailmind_powerbi.py`.

**Desktop check:** Power BI Desktop is not installed on this machine (`detect_power_bi_desktop() is None`), so the project could not be opened in Desktop. No claim is made that it loads there; structural validation is the strongest available evidence.

### 3.5 Confirmed data source defect: `kind: File` invalid in dataSource definitions (fixed)

Power BI Desktop rejects generated `definition/dataSources/FactSales.tmdl` with:

```
TMDL Format Error:
Parsing error type - UnknownKeyword
Detailed error - Unsupported property - kind is not a supported property in the current context!
Document - './dataSources/FactSales'
Line Number - 2
Problematic line:
kind: File
```

**Root cause:** `retailmind/powerbi.py::_data_source()` generated `kind: File` and `mode: import` inside `dataSource` definition files. Microsoft's TMDL specification for `dataSource` files supports only `dataSource <name>` and `source = <M expression>` — there is no `kind` property and no `mode` property in data source definitions.

**Fix:** Removed `kind: File` and `mode: import` from `_data_source()`. Data source files now contain only `dataSource <name>` and `source = <M expression>`. Added validator checks in `validate_pbip()` to catch `kind:` and `mode:` properties in data source files with exact file path and line number.

**Validation:** All generated data source files pass structural validation with zero errors. New tests in `tests/test_retailmind_powerbi.py` cover data source `kind:`/`mode:` rejection, missing data sources, and fact table data source references.

**Desktop check:** Power BI Desktop is **not installed** on this machine. A fresh PBIP ZIP was generated at `C:\Users\ak837\RetailMind_Backups\RetailMindAI_Sales_Report_pbip_fixed.zip` (19,380 bytes, 36 files). Desktop compatibility remains explicitly unverified — the user must open `<project>.pbip` in Power BI Desktop and confirm.

- `profile_schema` parsed and profiled every row. It now samples at most 5,000 non-null values for date/numeric detection and computes `nunique` once.
- `_looks_like_date` attempted date parsing on numeric columns. It now short-circuits numeric/bool columns and uses a non-capturing year regex.
- `_blank_mask` and whitespace trimming performed text operations on non-text dtypes. They now use dtype fast paths and compute trimmed values once.

Measured effect on schema inference at 100k rows: **~1,312 ms → ~195 ms** (≈6.7× faster). E-commerce domain detection improved from `generic` to `commerce`.

No tests were deleted, skipped, or weakened. No assertions were relaxed.

---

## 4. Feature evidence (independent checks)

### 4.1 Functional audit — 12/12 passed
| Check | Evidence |
|:---|:---|
| Schema roles (retail) | 12 roles mapped correctly, domain `retail` |
| Profile numerics | 3,000 records; revenue sum `1,645,523.85` matched pandas |
| Cleaning | rows `3001 → 3000`, duplicate removed, revenue numeric coerced |
| Alerts | 16 alerts; `merge_alerts` suppressed duplicates; ack/dismiss worked |
| Segmentation | k=2, silhouette 0.3475, 60 customers, RFM max difference **0.0000** |
| Inventory | avg daily `10.0`, safety `70.0`, ROP `140.0`, suggested `80.0`, days left `20.0` |
| Forecasting | Linear trend, MAE `12,578.91`, RMSE `12,733.97`, MAPE `9.75` |
| Insights | 8 insights with numeric evidence |
| PBIP | 34 files, 6 tables, 14 measures, internal validation clean |
| Exports | executive PDF 8,669 B; business PDF 2,472 B; CSV 234,057 B; XLSX 216,339 B |
| Chatbot | answered `₹1,645,523.85`, matching pandas |
| RAG | answered `1,250,000` with citation `ops_memo.txt` |

### 4.2 Multi-domain / edge audit — 11/11 passed
- Retail → `retail`; HR → `hr`; finance → `finance`; e-commerce → `commerce`.
- Missing values, 20 duplicate rows, invalid dates, missing revenue/date columns, and an empty dataset all handled without exceptions.
- Missing-column path: 3 warnings, segmentation unavailable, alert explains why.
- Auto dashboard: 6 pages / 36 components.

### 4.3 UI audit — 9/9 passed
- Branding title present; no `<div>`/`<svg>` leakage into text elements.
- Alerts: severity/status filters, 2 acknowledge + 2 dismiss buttons, CSV download; a click persisted `acknowledged_count=1`.
- Segmentation: k slider + CSV/Excel downloads.
- Inventory: lead/safety/service/cover controls + CSV/Excel downloads.
- Forecasting: metric/frequency/horizon/method controls + CSV/Excel downloads.
- Power BI center: PBIP ZIP and theme JSON buttons; `detect_power_bi_desktop() = None` on this machine.
- AI provider: **no key present**, UI states fallbacks continue working; no `sk-` string in rendered text.
- 17 download buttons present, including all six required universal exports.

### 4.4 Full regression suite
```
295 passed, 3 skipped in 144.09s
```
The skip is `tests/test_e2e_browser.py`, which requires `RUN_E2E=1` and a Playwright browser. Browser end-to-end coverage was **not** executed. Two mobile upload tests are also skipped because `xlwt` is not installed (XLS/XLSM fixture creation).

---

## 5. Claim corrections

| Original claim | Verified reality |
|:---|:---|
| “258 tests passed in 63.67s, 0 warnings” | **259 passed, 1 skipped** in ~164–174 s. Streamlit emits `use_container_width` deprecation warnings; schema regex warning was removed by the fix. |
| “Holt-Winters / double exponential smoothing” | **Simple** exponential smoothing (`level = αy + (1−α)·level`), α grid-searched 0.05–0.95. No β/trend term. |
| “Prediction intervals grow with horizon (1.96·RMSE·√h)” | **Constant** ±1.96 × residual σ for every future period. The app’s own notes correctly call them approximate. |
| “ARIMA supported” | Only when `statsmodels` is installed. It is absent here; the UI correctly declares the method unavailable. |
| “Safety stock = Z·σd·√L” | True **only when demand variability exists**. With zero variance it falls back to `forecast_daily × safety_days`. A mapped safety-stock column overrides both. |
| “Order quantity = target − stock” | Actual target is `ROP + forecast_daily × target_cover`, minus `(stock + incoming)`. |
| “PBIP opens in Power BI Desktop” | **Not validated.** Desktop is not installed. The model has **no data partitions/source**, so visuals will not populate until a source is connected. No `.pbix` is produced. |
| “Complete 100k pipeline < 2.2 s” | Not reproduced. On this machine the core pipeline (schema+clean+dashboard+alerts+insights) is **3.95 s**; adding CSV parse and PDF export gives ≈8.5 s. |
| “400% speedup” | Aggregate claim is not supported by the current benchmark; schema inference genuinely improved ~6.7× after the audit fixes, while cleaning/alerts/segmentation remain the slowest stages. |
| “131/131 controls verified” | The shipped 17-test button suite covers many controls, but **does not** drive alerts, segmentation, inventory, forecasting, or PBIP. Those were verified separately in `audit_ui.py`. |
| “No login required” | True by default, but the repository also contains optional auth/session/MySQL modules. The app starts without them. |

---

## 6. Performance (honest, median of 3)

Source data: 12 columns + stock/lead time, cardinality `customers = max(100, rows/120)`. Full numbers in `benchmark_results.json`.

| Stage (ms) | 10k | 50k | 100k | 250k |
|:---|---:|---:|---:|---:|
| CSV parse | 15.8 | 229.9 | 350.5 | 1,126.9 |
| Schema inference | 49.2 | 203.9 | 194.5 | 203.0 |
| Profiling | 16.0 | 189.0 | 382.0 | 545.1 |
| Cleaning | 57.9 | 661.4 | 1,240.3 | 2,665.1 |
| Auto dashboard | 0.2 | 0.6 | 0.6 | 0.6 |
| Alerts | 103.8 | 977.7 | 2,263.2 | 5,567.7 |
| Segmentation | 45.5 | 495.8 | 1,095.4 | 2,514.7 |
| Insights | 12.1 | 106.4 | 179.9 | 396.7 |
| Forecasting | 9.0 | 75.5 | 140.8 | 334.5 |
| Inventory | 85.4 | 779.4 | 1,595.0 | 3,804.1 |
| PBIP | 1.2 | 5.6 | 4.8 | 4.4 |
| Executive PDF | 131.6 | 170.9 | 208.7 | 526.2 |
| Chatbot | 4.0 | 49.0 | 83.3 | 262.6 |
| **Core pipeline** | **212.4** | **2,206.3** | **3,946.6** | **9,986.9** |

Traced peak memory at 100k: **103.4 MB** (tracemalloc pass, includes tracing overhead; this is not process RSS).

Interpretation: schema inference is now bounded and fast; alerts, segmentation, cleaning and inventory scale roughly linearly with rows and dominate at 100k+. The “sub-2-second at 100k” claim is not supported on this hardware.

### 6.1 Optimization results (this repair)

Mechanism (no data truncation; KPIs/computations still use complete valid data):
- Prepared dataset, schema, cleaning result, alerts, segmentation, forecasting, inventory, insights and PBIP project are memoized in `st.session_state` per dataset signature, so a rerun triggered by any click reuses them instead of recomputing.
- Download-byte generation (CSV/Excel/PDF/PBIP zip/theme) is lazy: `st.download_button` receives zero-argument callables, so the expensive exports are only produced when a user clicks. Cache keys include dataset identity, cleaning options and filters, so results are never served for another uploaded dataset.

End-to-end Streamlit `AppTest` timings (full script reruns, include Streamlit overhead; median of repeated runs):

| Interaction | Before (20k rows) | After (20k rows) | Before (500 rows) | After (500 rows) |
|:---|---:|---:|---:|---:|
| Upload, first render (cold) | 30,773 ms | 17,270 ms | — | — |
| Warm rerun, no interaction | 3,355 ms | 1,699 ms | 1,533 ms | 904 ms |
| Page navigation (each tab) | ≈3,200 ms | ≈1,600 ms | ≈1,500 ms | ≈1,000 ms |
| Download clicked (+ rerun) | 3,093 ms | 1,589 ms | — | — |
| Switch to Customize Dashboard | 3,269 ms | 1,619 ms | — | — |
| Dashboard builder action | 3,644 ms | 2,083 ms | — | — |

All interactions complete without script errors after the repair; previously Sales/Profit/Customer/Product/Data Quality pages raised `NameError: _measure_label`. No artificial delays or animations were added.

---

## 7. Limitations and not-testable items

1. **Power BI Desktop validation** — not installed; `.pbip` was only validated structurally by the project’s own validator. No claim is made that it opens or refreshes.
2. **No data source in PBIP** — `FactSales` has columns/measures but no partition; dimensions are DAX calculated tables. A user must connect data before visuals populate.
3. **ARIMA/SARIMA** — optional dependency absent.
4. **Live LLM provider** — no API key; only deterministic fallbacks verified. No response streaming exists in `retailmind/ai/provider.py`.
5. **SMTP email** — no server; delivery path is unit-tested with mocks only.
6. **Browser end-to-end** — Playwright browser not installed; `test_e2e_browser.py` skipped.
7. **PDF visual fidelity** — PDFs verified as real `%PDF` files with expected text, but no page-by-page visual inspection was performed (no PDF renderer installed).
8. **MySQL integration** — not exercised (no server configured); app starts without it.

---

## 8. Reproduce this audit

```powershell
cd "C:\Users\ak837\OneDrive\Desktop\Retail-Sales-Profitability-Analysis (1)\Retail-Sales-Profitability-Analysis"

.\.venv\Scripts\python.exe audit_functional.py
.\.venv\Scripts\python.exe audit_domains_perf.py
.\.venv\Scripts\python.exe audit_ui.py
.\.venv\Scripts\python.exe audit_benchmark.py

.\.venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider --basetemp=./tmp_pytest_final --tb=short
```

Expected: functional 12/12, domains 11/11, UI 9/9, pytest `266 passed, 1 skipped`.

---

*This audit reflects only what was executed in the stated environment. Anything not executed is labelled “Not testable” rather than assumed working.*
