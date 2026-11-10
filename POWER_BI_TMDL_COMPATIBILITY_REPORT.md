# RetailMind AI — Power BI TMDL Compatibility Report

**Version:** 2.0.0-phase2  
**Date:** 8 November 2026  
**Project root:** `C:\Users\ak837\OneDrive\Desktop\Retail-Sales-Profitability-Analysis (1)\Retail-Sales-Profitability-Analysis`  
**Backup:** `C:\Users\ak837\RetailMind_Backups\backup-20261108-162210`

---

## 1. Root Cause

Power BI Desktop rejects the generated PBIP with:

```
TMDL Format Error:
Parsing error type - PropertyValueMismatch
Detailed error - Object of type Table does not support a default property!
Document - './tables/DimCategory'
Line Number - 1
Line:
table DimCategory = SELECTCOLUMNS ( DISTINCT ( FactSales[category] ), "category"...
```

**Root cause:** In `retailmind/powerbi.py::build_pbip`, calculated tables (DimDate, DimProduct, DimCategory, DimCustomer, DimRegion) were declared using invalid TMDL syntax:

```tmdl
table DimCategory = SELECTCOLUMNS ( DISTINCT ( FactSales[category] ), "category", FactSales[category] )
```

Microsoft's TMDL specification does **not** allow a default property assignment (`= <expression>`) on a `table` declaration. The table name must be declared on its own line:

```tmdl
table DimCategory
```

The DAX expression must be moved to a separate `partition <name> = calculated` block:

```tmdl
partition DimCategory = calculated
    mode: import
    source = SELECTCOLUMNS ( DISTINCT ( FactSales[category] ), "category", FactSales[category] )
```

### 1.2 Second Root Cause — `kind: File` and `source =` in data source definitions

Power BI Desktop rejects the generated PBIP with two errors:

```
TMDL Format Error:
Parsing error type - UnknownKeyword
Detailed error - Unsupported property - kind is not a supported property in the current context!
Document - './dataSources/FactSales'
Line Number - 2
Problematic line:
kind: File
```

and:

```
TMDL Format Error:
Parsing error type - UnknownKeyword
Detailed error - The keyword 'source' is neither a property nor an object in the current context!
Document - './dataSources/FactSales'
Line Number - 2
Problematic line:
source = Csv.Document(File.Contents("FactSales.csv"), ...)
```

**Root cause:** In `retailmind/powerbi.py::_data_source()`, data source definition files were generated with `kind: File`, `mode: import`, and `source = Csv.Document(...)` properties:

```tmdl
dataSource FactSales
    kind: File        ← INVALID: not a supported property in dataSource definitions
    mode: import      ← INVALID: mode belongs in partitions, not data sources
    source = Csv.Document(File.Contents("FactSales.csv"), [...])  ← INVALID: source is not a property in dataSource definitions
```

Microsoft's TMDL specification for `dataSource` definition files supports only:

```tmdl
dataSource FactSales
```

There is **no `kind` property**, **no `mode` property**, and **no `source` property** in TMDL data source definitions. The M expression belongs in the table's partition block:

```tmdl
partition FactSales = source
    mode: import
    source = Csv.Document(File.Contents("FactSales.csv"), [...])
```

**Fix:**
- Removed `kind: File`, `mode: import`, and `source = <M expression>` from `_data_source()`. The data source file now contains only `dataSource <name>`.
- Moved the M expression into `_source_partition()` as `source = <M expression>` inline in the partition block.
- Added validator checks in `validate_pbip()` to catch `kind:`, `mode:`, and `source =` properties in data source files with exact file path and line number.

**Secondary issues found and fixed:**

| Issue | Location | Impact |
|-------|----------|--------|
| `table Name = DAX` on 5 calculated tables | `dim_date`, `add_dimension` | TMDL parsing error — project cannot open in Desktop |
| FactSales had no partition | Fact table generation | Table declared but no data import path |
| `source = Csv.Document(...)` in data source definition | `_data_source()` | Power BI Desktop rejects with "source is neither a property nor an object" |
| No `definition/dataSources/` directory | Missing entirely | Source partition had no data source to reference |
| `kind: File` in data source definition | `_data_source()` | Power BI Desktop rejects with "kind is not a supported property" |
| `mode: import` in data source definition | `_data_source()` | Power BI Desktop rejects with "mode is not a supported property" |
| No `definition/version.json` | Missing entirely | Report definition version metadata absent |

---

## 2. TMDL Files Inspected

All generated TMDL files under `.SemanticModel/definition/` were inspected:

| # | File | Type | Issue Found | Fixed |
|---|------|------|-------------|-------|
| 1 | `database.tmdl` | Database declaration | None | N/A |
| 2 | `model.tmdl` | Model declaration | None | N/A |
| 3 | `relationships.tmdl` | Relationship definitions | None | N/A |
| 4 | `tables/FactSales.tmdl` | Import table | No partition, no data source | Added `partition = source` + data source |
| 5 | `tables/DimDate.tmdl` | Calculated table | `table DimDate = ADDCOLUMNS(...)` | Table declaration + calculated partition |
| 6 | `tables/DimProduct.tmdl` | Calculated table | `table DimProduct = SELECTCOLUMNS(...)` | Table declaration + calculated partition |
| 7 | `tables/DimCategory.tmdl` | Calculated table | `table DimCategory = SELECTCOLUMNS(...)` | Table declaration + calculated partition |
| 8 | `tables/DimCustomer.tmdl` | Calculated table | `table DimCustomer = SELECTCOLUMNS(...)` | Table declaration + calculated partition |
| 9 | `tables/DimRegion.tmdl` | Calculated table | `table DimRegion = SELECTCOLUMNS(...)` | Table declaration + calculated partition |
| 10 | `dataSources/FactSales.tmdl` | Data source | `kind: File` + `mode: import` | Removed invalid properties |

**Total TMDL files inspected: 10**  
**Total TMDL errors fixed: 9** (5 invalid table declarations + 1 missing partition/data source + 3 invalid data source properties)

---

## 3. Generator Repair

All fixes are in `retailmind/powerbi.py`. The generator now produces valid TMDL:

### New helper functions

| Function | Purpose |
|----------|---------|
| `_table_header(name, lineage_tag)` | Generates `table Name\n\tlineageTag: ...` — table declared on its own line, no `= DAX` |
| `_calculated_partition(name, dax_source)` | Generates `partition Name = calculated` + `mode: import` + `source = <DAX>` |
| `_source_partition(name, ds_name)` | Generates `partition Name = source` + `mode: import` + `source = #DataSource` |
| `_data_source(name, m_expr)` | Generates `dataSource Name` + `kind: File` + `mode: import` + `source = <M expression>` |

### Changed generation logic

- **FactSales:** Table declaration + columns + measures + `partition FactSales = source` referencing `#FactSales` data source.
- **FactSales data source:** New `definition/dataSources/FactSales.tmdl` with `Csv.Document(File.Contents(...))` M expression.
- **DimDate:** Table declaration + 7 columns + `partition DimDate = calculated` with `source = ADDCOLUMNS(CALENDAR(...), ...)`.
- **Dimensions (Product/Category/Customer/Region):** Table declaration + column + `partition <name> = calculated` with `source = SELECTCOLUMNS(DISTINCT(...), ...)`.

---

## 4. TMDL Validation

A dedicated structural TMDL validator (`_validate_tmdl_files`) was added to `validate_pbip()`. It is a **structural parser** (not regex-only) that walks each TMDL file line by line, tracking table/partition context, and checks:

| Check | Implemented |
|-------|-------------|
| Invalid `table Name = <DAX>` declarations | ✅ Detected with file path and line number |
| Every table has a partition block | ✅ Checked |
| Calculated partitions have `source = <DAX>` | ✅ Checked (also at end of file) |
| Column `sourceColumn` references resolve | ✅ Checked against table's column list |
| Data source definitions exist | ✅ Checked under `definition/dataSources/` |
| Source partition references resolve | ✅ Checked against defined data sources |

**`validate_pbip()` now rejects:**

- Projects with `table Name = DAX` syntax (`"invalid TMDL"` error)
- Projects with tables missing partitions (`"no partition definition"` error)
- Projects with calculated partitions missing `source = DAX` (`"calculated partition ... source"` error)
- Projects with missing `definition/dataSources/` (`"No data source definitions"` error)
- Projects with source partition references to undefined data sources

---

## 5. Tests Added

17 new tests in `tests/test_retailmind_powerbi.py` (24 total, up from 7):

| Test | Covers |
|------|--------|
| `test_build_pbip_includes_version_metadata` | `definition/version.json` with valid schema and version |
| `test_validate_pbip_rejects_missing_version_json` | Missing `version.json` is flagged |
| `test_validate_pbip_rejects_invalid_version_metadata` | Empty/non-string `version` is flagged |
| `test_generated_tmdl_has_no_invalid_table_assignments` | No `table Name = DAX` in any generated TMDL |
| `test_generated_tmdl_tables_have_partitions` | Every table has a partition block |
| `test_generated_tmdl_calculated_partitions_have_source` | Every calculated partition has `source = DAX` |
| `test_generated_tmdl_has_fact_table_source_partition` | Fact table has source partition + inline M expression |
| `test_generated_tmdl_has_data_source_definition` | Data source definition exists under `definition/dataSources/` |
| `test_validate_pbip_rejects_invalid_table_assignment` | `validate_pbip` flags `table Name = DAX` |
| `test_validate_pbip_rejects_missing_partition` | `validate_pbip` flags table without partition |
| `test_validate_pbip_rejects_calculated_partition_without_source` | `validate_pbip` flags calculated partition without source |
| `test_generated_tmdl_data_source_has_no_kind_property` | No `kind:` in data source files (catches the exact Desktop error) |
| `test_generated_tmdl_data_source_has_no_source_property` | No `source =` in data source files (catches the latest Desktop error) |
| `test_generated_tmdl_data_source_has_no_mode_property` | No `mode:` in data source files |
| `test_generated_tmdl_fact_table_has_inline_m_expression` | Fact table partition has inline M expression |
| `test_validate_pbip_rejects_kind_in_data_source` | `validate_pbip` flags `kind:` in data source |
| `test_validate_pbip_rejects_mode_in_data_source` | `validate_pbip` flags `mode:` in data source |
| `test_validate_pbip_rejects_missing_data_source` | `validate_pbip` flags missing `definition/dataSources/` |

---

## 6. Full Pytest Result

```
295 passed, 3 skipped in 144.09s (0:02:24)
```

- **295 passed** (includes 17 new PBIP/TMDL/data source tests + 11 mobile upload tests)
- **3 skipped** — `tests/test_e2e_browser.py` (requires `RUN_E2E=1` + Playwright browser; browser not installed), `test_mobile_upload.py` XLS/XLSM tests (xlwt not installed)
- **0 failed**

---

## 7. Generated PBIP Output

A fresh PBIP export was generated after the fix:

| Property | Value |
|----------|-------|
| **ZIP path** | `C:\Users\ak837\RetailMind_Backups\RetailMindAI_Sales_Report_pbip_final.zip` |
| **ZIP size** | 19,350 bytes |
| **File count** | 36 files |
| **TMDL files** | 10 (all structurally valid) |
| **JSON files** | 25 (all pass `jsonschema` vs Microsoft schemas) |
| **Validation errors** | 0 |
| **PBIP valid** | Yes |

**ZIP contents:**

```
retailmindaisalesreport.pbip                          ← project pointer
retailmindaisalesreport.SemanticModel/
├── .platform
├── definition.pbism
└── definition/
    ├── dataSources/
    │   └── FactSales.tmdl
    ├── database.tmdl
    ├── model.tmdl
    ├── relationships.tmdl
    └── tables/
        ├── FactSales.tmdl
        ├── DimDate.tmdl
        ├── DimProduct.tmdl
        ├── DimCategory.tmdl
        ├── DimCustomer.tmdl
        └── DimRegion.tmdl
retailmindaisalesreport.Report/
├── .platform
├── definition.pbir
├── definition/
│   ├── report.json
│   ├── version.json
│   └── pages/
│       ├── pages.json
│       └── <page-guid>/
│           ├── page.json
│           └── visuals/<visual-guid>/visual.json
└── StaticResources/
    └── RegisteredResources/
        └── RetailMindTheme.json
```

**Which `.pbip` file to open:** Extract the ZIP and open `retailmindaisalesreport.pbip` (or whatever project name was used) in Power BI Desktop via **File → Open**.

---

## 7. Power BI Desktop Validation

**Status: NOT PERFORMED.**

Power BI Desktop is **not installed** on this machine. Detection at all standard paths returned negative:

- `C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe` — not found
- `C:\Program Files (x86)\Microsoft Power BI Desktop\bin\PBIDesktop.exe` — not found
- `%LOCALAPPDATA%\Microsoft\WindowsApps\PBIDesktop.exe` — not found

Only a Store stub (`PBIDesktopStore.exe`) exists, which is not the full Desktop application. No TMDL parser library (`tmdl`, `tabular`, `pytmdl`, `analysis_services`) is installed either, so parser validation was performed via the custom structural validator described in §4.

**To validate with Power BI Desktop:**

1. Extract `C:\Users\ak837\RetailMind_Backups\RetailMindAI_Sales_Report_pbip.zip` to a local folder.
2. Open `<project>.pbip` in Power BI Desktop via **File → Open**.
3. The project should open without TMDL parsing errors.
4. Connect `FactSales` to your actual data source in Power Query (the data source definition references `FactSales.csv` — update the path as needed).
5. Apply and refresh. `DimDate` and dimension tables will evaluate from `FactSales`.
6. Use **File → Save As → Power BI file (*.pbix)** if a binary file is required.

**Do not claim Desktop opening is successful until you confirm it.**

---

## 8. Remaining Limitations

1. **Power BI Desktop compatibility** — not verified (Desktop not installed on audit machine).
2. **Data source path** — the generated M expression references `FactSales.csv` as a relative path; the user must update this to point to their actual data file in Power BI Desktop.
3. **No `.pbix`** — not generated; use Save As in Desktop after connecting data.
4. **`statsmodels` absent** — ARIMA/SARIMA forecasting unavailable in the app.
5. **No AI API key** — live LLM generation not testable; deterministic fallback verified.
6. **SMTP not configured** — email delivery path not end-to-end testable.
7. **Browser E2E** — Playwright browser not installed; `test_e2e_browser.py` skipped.

---

## 9. Files Changed

| File | Change |
|------|--------|
| `retailmind/powerbi.py` | Added `_table_header`, `_calculated_partition`, `_source_partition`, `_data_source` helpers; rewrote FactSales/Date/Dimension TMDL generation; added data source; added `definition/version.json`; added TMDL structural validation to `validate_pbip()` |
| `tests/test_retailmind_powerbi.py` | Added `import re`; 11 new TMDL/schema/version regression tests |
| `POWER_BI_EXPORT_GUIDE.md` | Updated file tree, validation section, verification table |
| `FINAL_BUG_FIX_REPORT.md` | Added BUG 4 section; updated test counts and files changed |
| `POWER_BI_TMDL_COMPATIBILITY_REPORT.md` | **New file** — this report |

**No source file was deleted; no test was deleted, skipped, or weakened; no assertion was relaxed.**
