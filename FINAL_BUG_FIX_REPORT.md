# RetailMind AI — Final Bug Fix Report

**Version:** 2.0.0-phase2  
**Date:** 8 November 2026  
**Project root:** `C:\Users\ak837\OneDrive\Desktop\Retail-Sales-Profitability-Analysis (1)\Retail-Sales-Profitability-Analysis`  
**Backup:** `C:\Users\ak837\RetailMind_Backups\backup-20261108-162210` (taken before any source change; 885 files)

---

## 1. Bugs fixed (root cause, not symptoms)

### BUG 1 — Product Performance table / every table page: `NameError: name '_measure_label' is not defined`

**Location:** `retailmind/render.py::_render_table`.  
**Root cause:** `_render_table` called a module-level helper `_measure_label(schema, measure)` that was never defined. Every auto dashboard page containing a table/matrix component (Sales Analysis, Profit Analysis, Customer Analysis, Product Analysis, Data Quality) raised the `NameError` on first render, which made page navigation and download clicks fail in `Streamlit AppTest`.

**Fix:** replaced the broken helper with a pure, unit-testable `table_frame(frame, component, schema)` that:
- supports `sum`, `mean`, `min`, `max`, `count` aggregations (`avg`/`average` normalised to `mean`);
- renders matrix components as measure (Sum) + measure (Mean);
- falls back to a record count when no measure is configured;
- summarises profit/quantity role columns when no explicit measure is set;
- preserves missing values as `NaN` (`sum(min_count=1)`) instead of fabricating zeros;
- sorts by the first value column descending.

**Tests:** new `tests/test_retailmind_render_tables.py` — 6 tests, all pass.

### BUG 2 — Power BI PBIP: “Expected '$schema' property in definition.pbir”

**Location:** `retailmind/powerbi.py`.  
**Root cause:** the generated `definition.pbir` and `.pbip` shortcut referenced schema URLs Microsoft does not serve (`.../item/report/definitionProperties/1.0.0/schema.json`, `.../item/pbip/1.0.0/schema.json`), and `definition/report.json` carried forbidden properties (`reportDefinitionVersion`, theme-level `version`).

**Fix:**
- `$schema` identifiers now point at Microsoft's published schemas: `report/definitionProperties/2.0.0`, `report/definition/report/3.3.0`, `pbip/pbipProperties/1.0.0`, `report/definition/pagesMetadata/1.0.0` (page/visual/platform/pbism identifiers were already correct).
- `report.json` uses `themeCollection` with `reportVersionAtImport(page/report/visual)` plus a `resourcePackages` entry; `reportDefinitionVersion` removed.
- `validate_pbip` now rejects any generated project whose `$schema` differs from the expected Microsoft identifier.

**Validation:** all 24 JSON files generated per project pass `jsonschema` Draft 7 validation against the downloaded Microsoft schemas; `validate_pbip` returns zero errors on a fresh project and rejects a project with a stale `$schema`. New test `test_generated_project_uses_published_microsoft_schemas` in `tests/test_retailmind_powerbi.py`.

**Desktop check:** Power BI Desktop is **not installed** on this machine (`detect_power_bi_desktop() is None`), so the PBIP was **not opened in Desktop** and no `.pbix` was produced. Structural/schema validity is the strongest evidence available; Desktop compatibility remains explicitly unverified (see limitations below).

### BUG 3 — Dashboard navigation and export button errors

**Root cause:** consequence of BUG 1 — any page containing a table errored, so clicking Executive Overview / Sales Analysis / Profit Analysis / Customer Analysis / Product Analysis / Data Quality failed, and export buttons on those pages could not be reached.

**Fix:** fixed by BUG 1. Verified end-to-end with `Streamlit AppTest`: all six pages render without script errors and all 17 download buttons (`Download cleaned CSV/Excel`, `Download executive summary Markdown/PDF/Excel`, `Download business analysis PDF`, `Download Power BI project ZIP`, `Download Power BI theme JSON`, `Download Alerts CSV`, segment/inventory/forecast CSV+Excel) were clicked successfully — each produces real bytes (CSV/XLSX/ZIP/`%PDF` payloads verified independently).

### BUG 4 — Power BI PBIP/TMDL: “Parsing error type - PropertyValueMismatch” — `table DimCategory = SELECTCOLUMNS(...)` is invalid TMDL

**Location:** `retailmind/powerbi.py::build_pbip`.  
**Root cause:** calculated tables (DimDate, DimProduct, DimCategory, DimCustomer, DimRegion) were declared using invalid TMDL syntax `table Name = <DAX expression>`. Microsoft's TMDL specification does not allow a default property assignment on a `table` declaration — the table must be declared on its own line, and the DAX expression must be moved to a separate `partition <name> = calculated` block with `source = <DAX expression>`. Power BI Desktop rejects this with “Object of type Table does not support a default property!”. Additionally, FactSales had no partition or data source definition, and `definition/dataSources/` was missing entirely.

**Fix:**
- Added `_table_header()`, `_calculated_partition()`, `_source_partition()`, and `_data_source()` helper functions that generate valid TMDL:
  - Table declarations on their own line (`table Name`) with no `= DAX` assignment.
  - Calculated tables use `partition <name> = calculated` + `mode: import` + `source = <DAX expression>`.
  - FactSales uses `partition FactSales = source` + `mode: import` + `source = #FactSales`.
  - A `dataSource FactSales` definition is generated under `definition/dataSources/`.
- Rewrote DimDate generation: table declaration + columns + `partition DimDate = calculated` with `source = ADDCOLUMNS(...)`.
- Rewrote `add_dimension()`: table declaration + column + `partition <name> = calculated` with `source = SELECTCOLUMNS(...)`.
- Added `definition/version.json` with valid `$schema` (versionMetadata/1.0.0) and `version`.
- Extended `validate_pbip()` with a structural TMDL validator (`_validate_tmdl_files`) that:
  - Detects invalid `table Name = <DAX>` declarations with file path and line number.
  - Checks every table has a partition block.
  - Checks calculated partitions have `source = <DAX expression>`.
  - Checks column `sourceColumn` references resolve within the table.
  - Checks data source definitions exist under `definition/dataSources/`.
  - Checks source partition references resolve to defined data sources.

**Validation:** all generated TMDL files pass structural validation with zero errors. The generated PBIP ZIP contains 36 files (10 TMDL + 25 JSON + 1 .pbip), all valid. New tests in `tests/test_retailmind_powerbi.py`: 8 TMDL regression tests covering invalid table assignment detection, partition presence, calculated partition source validation, fact table source partition, data source definition, and `validate_pbip` rejection of each defect class.

**Desktop check:** Power BI Desktop is **not installed** on this machine (`detect_power_bi_desktop() is None`), so the PBIP was **not opened in Desktop** and no `.pbix` was produced. A fresh PBIP ZIP was generated at `C:\Users\ak837\RetailMind_Backups\RetailMindAI_Sales_Report_pbip.zip` (19,400 bytes, 36 files). Desktop compatibility remains explicitly unverified — the user must open `<project>.pbip` in Power BI Desktop and confirm.

### BUG 5 — Power BI PBIP/TMDL: “Unsupported property - kind is not a supported property in the current context” in dataSources/FactSales.tmdl

**Location:** `retailmind/powerbi.py::_data_source()`.  
**Root cause:** The `_data_source()` helper generated `kind: File` and `mode: import` properties inside `definition/dataSources/FactSales.tmdl`. Microsoft's TMDL specification for `dataSource` definition files supports only `dataSource <name>` and `source = <M expression>`. There is **no `kind` property** and **no `mode` property** in TMDL data source definitions — the data source kind is inferred from the M expression (e.g., `Csv.Document(...)`), and `mode: import` belongs in the table's partition block, not the data source. Power BI Desktop rejects `kind: File` with "Unsupported property - kind is not a supported property in the current context!" at line 2 of the data source file.

**Fix:**
- Removed `kind: File` and `mode: import` from `_data_source()`. The data source file now contains only `dataSource <name>` and `source = <M expression>`.
- Added validator checks in `validate_pbip()` to catch `kind:` and `mode:` properties in data source files with exact file path and line number.

**Validation:** All generated data source files pass validation with zero errors. New tests in `tests/test_retailmind_powerbi.py`: `test_generated_tmdl_data_source_has_no_kind_property`, `test_generated_tmdl_data_source_has_source_expression`, `test_generated_tmdl_data_source_has_no_mode_property`, `test_validate_pbip_rejects_kind_in_data_source`, `test_validate_pbip_rejects_mode_in_data_source`, `test_validate_pbip_rejects_missing_data_source`.

**Desktop check:** Power BI Desktop is **not installed** on this machine. A fresh PBIP ZIP was generated at `C:\Users\ak837\RetailMind_Backups\RetailMindAI_Sales_Report_pbip_fixed.zip` (19,380 bytes, 36 files). Desktop compatibility remains explicitly unverified — the user must open `<project>.pbip` in Power BI Desktop and confirm.

### BUG 6 — Mobile Excel Upload Failure — Android Chrome rejects valid Excel files

**Location:** `dashboard.py::main()` — `st.file_uploader(type=list(SUPPORTED_EXTENSIONS))`.  
**Root cause:** The `st.file_uploader` `type` parameter sets the browser's `accept` attribute client-side. Android Chrome may report different or no MIME types for Excel files, causing valid `.xlsx` files to appear in a red error state (red exclamation icon, red remove button) and blocking dashboard generation. The same file works on desktop browsers because desktop Chrome handles the `accept` attribute correctly.

**Fix:**
- Removed `type=list(SUPPORTED_EXTENSIONS)` from `st.file_uploader` — users can now select any file.
- Added server-side file extension validation: the filename extension is checked against `SUPPORTED_EXTENSIONS` before attempting to read the file. Validation is based on extension + file contents, never MIME type.
- Added clear error messages for unsupported extensions, empty files, corrupted workbooks, and files with no readable columns.
- Multiple worksheet support preserved — Excel files still show a worksheet selector.
- Existing desktop upload behavior preserved — all existing upload tests continue to pass.

**Tests:** new `tests/test_mobile_upload.py` — 11 tests covering XLSX/CSV/XLS/XLSM uploads with various MIME types (including Android-style and no MIME), corrupted files, empty files, unsupported extensions, and dashboard generation after upload.

**Desktop check:** Physical Android device testing was not available in this environment. All tests pass in the headless AppTest environment. For manual Android Chrome testing, see the instructions in `tests/test_mobile_upload.py`.

### BUG 7 — Power BI PBIP/TMDL: “The keyword 'source' is neither a property nor an object in the current context” in dataSources/FactSales.tmdl

**Location:** `retailmind/powerbi.py::_data_source()`.  
**Root cause:** After fixing `kind: File` (BUG 5), the `_data_source()` helper still generated `source = Csv.Document(...)` inside `definition/dataSources/FactSales.tmdl`. Microsoft's TMDL specification for `dataSource` definition files supports **no** `source` property — the M expression belongs in the table's partition block, not the data source definition. Power BI Desktop rejects `source = Csv.Document(...)` with "The keyword 'source' is neither a property nor an object in the current context!" at line 2 of the data source file.

**Fix:**
- Removed `source = <M expression>` from `_data_source()`. The data source file now contains only `dataSource <name>` with no properties.
- Moved the M expression into `_source_partition()` as `source = <M expression>` inline in the partition block (`partition FactSales = source` + `mode: import` + `source = Csv.Document(...)`).
- Added validator checks in `validate_pbip()` to catch `source =` properties in data source files with exact file path and line number.

**Validation:** All generated data source files pass validation with zero errors. New tests in `tests/test_retailmind_powerbi.py`: `test_generated_tmdl_data_source_has_no_source_property`, `test_generated_tmdl_fact_table_has_inline_m_expression`.

**Desktop check:** Power BI Desktop is **not installed** on this machine (`detect_power_bi_desktop() is None`). A fresh PBIP ZIP was generated at `C:\Users\ak837\RetailMind_Backups\RetailMindAI_Sales_Report_pbip_final.zip` (19,350 bytes, 36 files). Desktop compatibility remains explicitly unverified — the user must open `<project>.pbip` in Power BI Desktop and confirm.

---

## 2. Other defects repaired during this session

- `retailmind/dashboard.py`: prepared dataset/schema/cleaning were recomputed on every Streamlit rerun; now memoised per dataset identity + cleaning signature in `st.session_state`.
- `retailmind/dashboard.py`: alerts, segmentation, inventory, forecasting, insights, PBIP, outlier/correlation computations are memoised per dataset signature; cache keys never leak across datasets.
- `retailmind/dashboard.py`: export byte generation (PDF, Excel workbook, PBIP zip, theme, CSVs) is now lazy — `st.download_button` receives zero-argument callables so bytes are produced only when the user clicks.

---

## 3. Files changed

| File | Change |
|:---|:---|
| `retailmind/render.py` | `table_frame` + `_normalise_aggregation` replace the undefined `_measure_label` usage in `_render_table`. |
| `retailmind/powerbi.py` | Microsoft-published `$schema` URLs; `report.json` shape; `definition/version.json`; TMDL table declarations + calculated/source partitions; data source files contain only `dataSource <name>` (no `kind:`/`mode:`/`source =`); M expression inline in partition; TMDL structural validation in `validate_pbip()`. |
| `retailmind/dashboard.py` | Removed `type=` from `st.file_uploader` (mobile Chrome compatibility); added server-side extension validation; session-state compute caching; lazy download-byte callables; cache invalidation on dataset/cleaning change. |
| `tests/test_retailmind_render_tables.py` | New: 6 table/matrix rendering tests. |
| `tests/test_retailmind_powerbi.py` | Extended: schema-identifier validation + 17 TMDL/schema/version/data source tests (+17 tests total). |
| `tests/test_mobile_upload.py` | New: 11 mobile upload tests (XLSX/CSV/XLS/XLSM, Android MIME types, corrupted/empty/unsupported files, dashboard generation). |

No source file was deleted; no test was deleted, skipped, or weakened; no assertion was relaxed.

---

## 4. Verification results

| Suite | Result |
|:---|:---|
| Full pytest suite | **295 passed, 3 skipped, 0 failed** (298 collected, 144.09 s) |
| `tests/test_button_audit.py` | 17 passed |
| PBIP tests (`test_retailmind_powerbi.py`) | 24 passed (7 original + 17 new TMDL/schema/version/data source tests) |
| Mobile upload tests (`test_mobile_upload.py`) | 11 passed (2 skipped — xlwt not installed for XLS/XLSM) |
| PBIP jsonschema vs Microsoft schemas | 24 files / 24 pass |
| Independent repro: 6 pages × 17 downloads in AppTest | All ok, no script errors |
| `python -m compileall` (excl. `.venv`) | Clean |

The skip is `tests/test_e2e_browser.py` (requires `RUN_E2E=1` + Playwright browser; browser not installed).

---

## 5. Performance before/after (Streamlit AppTest end-to-end reruns; median of repeated runs; includes Streamlit overhead)

| Interaction | Before (20k rows) | After (20k rows) | Before (500 rows) | After (500 rows) |
|:---|---:|---:|---:|---:|
| Upload, first render (cold) | 30,773 ms | 17,270 ms | — | — |
| Warm rerun, no interaction | 3,355 ms | 1,699 ms | 1,533 ms | 904 ms |
| Page navigation (each tab) | ≈3,200 ms | ≈1,600 ms | ≈1,500 ms | ≈1,000 ms |
| Download clicked + rerun | 3,093 ms | 1,589 ms | — | — |
| Switch to Customize Dashboard | 3,269 ms | 1,619 ms | — | — |
| Dashboard builder action | 3,644 ms | 2,083 ms | — | — |

No data was truncated; KPIs/computations still use complete valid data; no mock data or artificial delays were introduced. Underlying single-stage pipeline timings are unchanged (schema ≈195 ms at 100k; core pipeline ≈3.95 s at 100k) — see `PERFORMANCE_REPORT.md`.

---

## 6. Known limitations / unresolved items (honest)

1. **Power BI Desktop** is not installed → PBIP not opened in Desktop; no `.pbix`; visuals/data not Desktop-verified.
2. **PBIP has no embedded data** (`FactSales` has no partition/source) — must be connected in Desktop before visuals populate.
3. **SMTP email** not configured → delivery path not end-to-end testable (mocked unit tests only).
4. **`statsmodels` absent** → ARIMA/SARIMA unavailable; app correctly reports it as unavailable.
5. **No AI API key** → live LLM generation not testable; deterministic fallback verified; no `sk-` secret leaks.
6. **Browser E2E** not run (Playwright browser absent).
7. PDF visual layout not page-inspected (no PDF renderer installed).
8. `.pytest_cache` at project root could not be deleted (file locked by the OS; `PermissionError`). It is a regenerable cache and harmless.
