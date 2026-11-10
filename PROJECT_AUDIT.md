# Retail Sales Profitability Analysis — Local Audit

> **Superseded (8 November 2026).** This document is a point-in-time audit of the earlier `1.0.0-phase1` codebase. At that time Streamlit AppTest could not run in this environment, and forecasting, anomaly detection and authentication did not exist. Those limitations have since been resolved or changed: the current suite reports **259 passed, 1 skipped**, AppTest exercises upload/filters/builder and the Phase-2 panels, and optional auth/session modules exist. Use [`OPENCODE_INDEPENDENT_AUDIT.md`](OPENCODE_INDEPENDENT_AUDIT.md) and [`PHASE2_PROGRESS.md`](PHASE2_PROGRESS.md) for the current verified status. The historical statements below are retained for traceability only.

Audit scope: local source, tests, documentation, SQL, and safe static checks only. No files were uploaded externally, no credentials were exposed, no database writes were performed, and `python/load_to_mysql.py` was not executed.

Status meanings:

- **Verified in code**: the implementation and/or deterministic tests demonstrate the behavior.
- **Partially implemented**: some support exists, but important limitations or unverified paths remain.
- **Missing**: no implementation was found.
- **Requires actual runtime/browser verification**: source code is present, but correctness depends on Streamlit, browser, MySQL, or deployment behavior that was not verified here.

## Executive summary

The project has a functioning analytics core and a substantial upload/dashboard implementation. CSV/Excel parsing, semantic mapping, dynamic filters, KPI calculations, exports, and supported Excel chart extraction are implemented and covered by deterministic tests. The upload-to-dashboard transition is explicitly represented by session-state identities and `st.rerun()`.

The most important unresolved limitation is runtime verification. Streamlit 1.66.0 stops after `Starting new event loop for server` in this environment, including with `streamlit hello`; no browser session could connect. Four Streamlit AppTest tests are therefore opt-in/skipped. MySQL connectivity and row-count verification were also unavailable.

The existing MySQL loader remains destructive (`DELETE FROM sales`) and is not a safe production import workflow. New non-destructive staging/validation primitives and mock-tested transaction guards exist in `python/safe_import.py`, but the database migration, staging load, permissions review, and live MySQL behavior remain unimplemented and unverified.

## Feature audit

| Requirement | Status | Evidence and relevant paths |
|---|---|---|
| CSV upload | **Verified in code**; **requires runtime/browser verification** | `dashboard.py` uses `st.file_uploader` and `data_sources.read_uploaded_file`; `tests/test_data_sources.py` verifies CSV parsing; `tests/test_dashboard_upload.py` contains an AppTest fixture but is skipped because the local AppTest runner hangs. |
| Excel upload | **Verified in code**; **requires runtime/browser verification** | `data_sources.py` supports `.xls`, `.xlsx`, `.xlsm`, worksheet inspection, preferred worksheet selection, and `pd.read_excel`; deterministic Excel parsing tests pass. Browser selection/upload was not verified. |
| Worksheet selection | **Verified in code**; **requires runtime/browser verification** | `dashboard.py` creates a worksheet selector for multi-sheet workbooks; `preferred_excel_worksheet` and worksheet scoring are tested. |
| Semantic column mapping | **Verified in code** | `data_sources.detect_column_mapping` uses normalized case-insensitive aliases for order ID/date, customer, city, region, category, product, sales representative, payment method, sales, profit, and numeric fields. Requested mapping tests pass. |
| Optional/missing columns | **Verified in code** | `map_to_canonical`, `OPTIONAL_DEFAULTS`, `profile_data`, `kpi_availability`, and conditional dashboard sections handle absent optional dimensions. Deterministic missing-column tests pass. |
| Generate Dashboard state transition | **Verified in code**; **requires runtime/browser verification** | `dashboard.py` computes `upload_generation_identity`, stores `generated_dataset_identity`, calls `st.rerun()`, and bypasses setup after generation. This path is covered structurally, but not in a live browser. |
| KPI cards | **Verified in code**; **requires runtime/browser verification** | `analytics.calculate_kpis` implements total sales, total profit, distinct orders, order-level AOV, margin, row-average sales, and quantity. `dashboard.py` renders `st.metric` cards. Analytics tests pass; live rendering is unverified. |
| Charts and breakdowns | **Verified in code**; **requires runtime/browser verification** | Monthly trend, flexible dimension breakdown, product, category, and city charts are rendered in `dashboard.py`; `grouped_performance` and monthly tests pass. Browser rendering is unverified. |
| Dynamic filters | **Verified in code**; **requires runtime/browser verification** | `analytics.filter_defaults`, `products_for_categories`, `apply_filters`, and dataset-scoped widget keys use active mapped values. Tests cover each mapped filter and KPI changes. Browser interaction is unverified. |
| Filter reset | **Verified in code**; **requires runtime/browser verification** | `reset_filters` and dataset-scoped defaults are wired to the reset button. Deterministic state tests pass; live widget reset is unverified. |
| Filter effects on KPIs/charts/data/exports | **Verified in code**; **requires runtime/browser verification** | `filtered` is used for KPIs, comparison filters, charts, insights, preview, and CSV/TXT exports. AppTest fixtures cover this intent but are skipped locally. |
| CSV export | **Verified in code** | `dataframe_to_csv` and `st.download_button` are present; deterministic export tests pass. Actual browser download was not verified. |
| Text summary export | **Verified in code** | `build_summary_report` and `st.download_button` are present; active extra and numeric filters are included in the report dictionary. Actual browser download was not verified. |
| Excel chart import | **Partially implemented** | `extract_excel_chart_data` supports direct-range bar, line, area, pie, and doughnut charts and tests cover a bar chart. Formatting, pivot charts, and unsupported drawings are not reproduced. |
| Excel map visuals | **Partially implemented** | `inspect_excel_visuals` detects map-like charts and the UI explains that direct map-chart import is unsupported. No native Excel map reproduction exists. |
| MySQL dashboard mode | **Partially implemented**; **requires runtime verification** | `dashboard.load_data` performs a read-only schema-aligned `SELECT` including region and payment method; mapping to canonical fields and in-memory filtering are implemented. Local MySQL connectivity and the expected 5,000-row result were not verified. |
| MySQL safe import | **Partially implemented** | `python/safe_import.py` validates candidates, creates staging DDL text, produces preview/reconciliation reports, checks batch/existing IDs, and requires an exact confirmation phrase plus batch-scoped parameterized insert-only merge. No staging table has been created and no database behavior has been tested. `python/load_to_mysql.py` remains destructive. |
| MySQL rollback | **Partially implemented** | `safe_import.merge_staging_into_sales` calls `start_transaction`, `commit`, and `rollback` behind explicit confirmation and is mock-tested. The existing loader still deletes production rows before insertion; live engine behavior is unverified. |
| SQL KPI consistency | **Partially implemented** | `analytics.py`, `sql/02_analysis_queries.sql`, and `python/sales_analysis.py` now use distinct orders and order-level AOV for overall reports. Live SQL/dashboard reconciliation was not possible without MySQL. |
| SQL performance | **Partially implemented** | The dashboard caches the MySQL load for 60 seconds, but reads the full table and filters in Pandas. SQL-side filtering, pagination, indexes, and large-dataset aggregation are not implemented. |
| Large datasets | **Partially implemented** | Current design is appropriate for the 5,000-row learning dataset and a synthetic 20,000-row calculation benchmark was fast locally. No realistic multi-user or million-row test exists. |
| Secrets handling | **Partially implemented** | `.gitignore` excludes `.env` and `.env.*`; `.env.example` contains placeholders; logging avoids passwords. The app still relies on a local `.env` and has no managed secret provider or deployment secret policy. |
| Authentication | **Missing** | No login or role-based authorization exists. This is acceptable for a local portfolio demo but not for shared production use. |
| Database permissions | **Partially implemented** | The dashboard query is read-only, but configuration examples use a root-style account and no restricted application user is provisioned. |
| Scheduled reports | **Missing** | No scheduler, report job, notification, or delivery integration exists. |
| Forecasting | **Missing** | No forecasting model or forecast evaluation workflow exists. |
| Anomaly detection | **Missing** | No anomaly detection implementation or validation exists. |
| AI-generated summaries | **Missing** | The project has deterministic rule-based insights in `analytics.build_insights`; it does not use AI-generated summaries. |
| Automated analytics tests | **Verified in code** | `tests/test_analytics.py` and `tests/test_data_sources.py` cover KPI definitions, filtering, state identities, mappings, data quality, Excel parsing, and exports. |
| Streamlit integration tests | **Partially implemented**; **requires compatible runtime verification** | `tests/test_dashboard_filters.py` and `tests/test_dashboard_upload.py` use `streamlit.testing.v1.AppTest`, but four tests are skipped by default because AppTest hangs before `SHUTDOWN` in this environment. |
| README/portfolio documentation | **Partially implemented** | `README.md` documents architecture, setup, KPI definitions, limitations, and resume wording. It does not document the current AppTest/runtime blocker, staging-import requirement, or verified browser evidence. |

## KPI and calculation review

`analytics.py` defines the principal business calculations consistently:

- Total sales and profit are sums over filtered rows.
- Distinct orders are counted from unique `order_id` values.
- Average order value aggregates sales by order before averaging.
- Profit margin is total profit divided by total sales, with safe zero handling.
- Prior-period comparisons retain active non-date and numeric filters.

The SQL overall report was corrected to use order totals, and payment-method counts use `COUNT(DISTINCT order_id)`. The project still needs a live read-only reconciliation query against `retail_sales_db.sales` before SQL/dashboard agreement can be marked verified.

## Runtime and verification limitations

The following were not claimed as working because they were not verified:

- Browser CSV upload and Generate Dashboard.
- Browser Excel upload and worksheet selection.
- Browser filter/reset interactions.
- Browser downloads.
- Streamlit server reachability from the available browser surface.
- MySQL connection and 5,000-row count.

Safe test command and latest result:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Ran 49 tests
OK (skipped=4)
```

Compilation checks passed for the application modules, database helper scripts, and tests. The four skipped tests are the Streamlit AppTest tests described above.

## Security and operational findings

1. Do not run `python/load_to_mysql.py` against an existing database; it contains `DELETE FROM sales`.
2. Create a separate staging table and restricted import account before implementing any replacement/merge workflow.
3. Add validation previews, duplicate checks, aggregate reconciliation, explicit confirmation, and transaction/rollback semantics.
4. Use a read-only database account for the dashboard and a separately controlled write account for approved imports.
5. Add authentication and role-based access before exposing the dashboard beyond a trusted local user.
6. Keep `.env` out of source control and use deployment-managed secrets for hosted environments.

## Portfolio readiness

The project is suitable as a college project and a resume/portfolio demonstration of Pandas, Streamlit, MySQL integration, schema mapping, and testable KPI logic. It is not yet production-ready because browser/runtime evidence, authentication, safe imports, database least privilege, SQL-side scaling, monitoring, and deployment recovery have not been demonstrated.

## Top five next steps

1. Run the dashboard from a normal host PowerShell session where the Streamlit process and browser share a localhost network namespace; complete CSV/Excel upload, generation, filtering, reset, and download verification.
2. Add a reviewed staging-table import migration with validation preview, duplicate checks, explicit confirmation, transaction, rollback, and reconciliation. Obtain approval before any production-data operation.
3. Provision separate read-only dashboard and controlled import database accounts; document secret management and add authentication for shared deployment.
4. Add a compatible, non-hanging Streamlit integration-test environment and make CSV/Excel AppTest workflows pass without MySQL.
5. Benchmark larger datasets and move filtering/aggregation to parameterized SQL with appropriate indexes and pagination before adding scheduled reports, forecasting, anomaly detection, or AI summaries.

