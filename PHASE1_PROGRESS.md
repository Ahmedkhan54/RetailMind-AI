# RetailMind AI — Phase 1 Progress Report

> **Superseded (8 November 2026).** This is the Phase 1 snapshot at version `1.0.0-phase1`; its `201 passed` figure is historical. The current suite reports **259 passed, 1 skipped** (260 collected), and the earlier claim corrections are recorded in [`PHASE1_REPAIR_REPORT.md`](PHASE1_REPAIR_REPORT.md). See [`OPENCODE_INDEPENDENT_AUDIT.md`](OPENCODE_INDEPENDENT_AUDIT.md) and [`PHASE2_PROGRESS.md`](PHASE2_PROGRESS.md) for the current verified status.

**Project:** RetailMind AI – Intelligent Universal Business Analytics Platform
**Version:** `1.0.0-phase1`
**Date:** 2026-11-07
**Entrypoint:** `dashboard.py` (Streamlit)

> Understand Your Business. Predict Your Future. Grow Smarter.

---

## 1. Executive summary

Phase 1 upgrades the original *Retail Sales Profitability Analysis* dashboard into a universal, Power BI-inspired analytics platform. The working retail upload/filter flow is preserved, while new modules add universal schema detection, transparent cleaning, conditional dashboard generation, a custom dashboard builder, verified chat, an allowlisted AI assistant, evidence-based insights, and document RAG.

All deterministic features work without an AI provider or API key. AI is optional and cannot invent numeric answers or execute arbitrary code.

**Final verification:** `201 passed, 1 skipped` (full pytest suite).

---

## 2. What was delivered

### 2.1 Universal data ingestion

| Requirement | Status | Implementation |
| --- | --- | --- |
| CSV upload | Done | `streamlit.file_uploader` → `data_sources.read_uploaded_file` |
| XLSX / XLS / XLSM | Done | `openpyxl` / `xlrd` via preserved parser |
| Multi-sheet workbooks | Done | Sheet selector in `dashboard.py` |
| Preview before analysis | Done | Raw preview + cleaned preview |
| Validation and clear errors | Done | Empty file, encoding, schema, numeric, date checks |
| Dataset replacement | Done | New upload/clear resets dataset-scoped state |
| Upload size limit | Done | 25 MB in UI and `.streamlit/config.toml` |
| Profiling | Done | `retailmind.schema.profile_report` |
| Missing/duplicate detection | Done | Profile report + cleaning suggestions |
| Dimension/measure detection | Done | `infer_schema` → `numeric`, `categorical`, `measures`, `dimensions` |
| Manual mapping correction | Done | Mapping editor → `apply_manual_mapping` |

### 2.2 Universal semantic detection

Detected role families include:

- **Commercial:** revenue, profit, cost/expenses, quantity, unit price, discount, order ID
- **Time:** order/sales/invoice/transaction dates and generic date/timestamp columns
- **Product/customer:** product, category, customer, region, city, store, sales rep, payment method
- **Workforce:** employee ID/name, department, salary, attendance
- **Education:** student ID/name, course, grade/marks
- **Other:** gender, age

Every role records:

- the mapped column,
- a confidence score (exact alias `1.0`, token match `0.86`, substring match, weak alias),
- candidate columns,
- domain inference (`retail`, `commerce`, `finance`, `operations`, `hr`, `education`, `generic`).

Manual mapping can set a role to a real column or clear it. Detection never requires a specific industry schema.

### 2.3 Transparent cleaning

| Behaviour | Default | Notes |
| --- | --- | --- |
| Trim/collapse whitespace | On | Low risk |
| Normalise category variants | On | Preserves most frequent spelling |
| Parse dates | On | Invalid values become missing |
| Coerce numerics | On | Invalid values become **missing**, never silent zero |
| Remove duplicate rows | **Off** | High risk; explicit opt-in only |
| Remove empty rows | **Off** | Explicit opt-in only |
| Fill invalid numerics with zero | **Off** | Explicit opt-in; adds a warning |

Cleaning never mutates the caller's DataFrame. The report records rows before/after, applied operations, suggestions with counts/risk/samples, and `original_preserved=True`.

### 2.4 Automatic dashboard

`retailmind.engine.build_dashboard` only emits components whose required columns exist:

- Executive Overview: records always; revenue, profit, margin, quantity, orders, customers, AOV, salary, average salary, employees, attendance rate, cost, growth when their roles exist.
- Sales Analysis: when revenue exists (and only if domain is retail/commerce/finance).
- Profit Analysis: when profit exists.
- Customer Analysis: when customer exists.
- Product Analysis: when product exists.
- Workforce: HR domain.
- Finance: finance/operations domains.
- Education: education domain.
- Data Quality: always, with a real profile table and missingness chart.

No synthetic rows, placeholder numbers, or empty visuals are generated.

### 2.5 Dashboard customization

Implemented:

- Auto mode and Custom mode.
- Visual add/edit/duplicate/move up/down/top/bottom/delete.
- Chart type change: bar, line, area, pie, donut, scatter, histogram, table, matrix.
- Aggregation change: sum, average, count, min, max.
- Title, description, dimension, measure, secondary measure, top-N, sort.
- Width (1–12 grid span), height, colour.
- Page add, rename, reorder, duplicate, delete (last page protected).
- Theme presets (dark, light, midnight, corporate), accent colour, palette.
- Save, autosave, restore, reset, undo, redo.
- Session-first state plus JSON dashboard definitions under `~/.retailmind/dashboards` or `RETAILMIND_STATE_DIR`.

**Limitation:** free-form drag-and-drop is not implemented because Streamlit has no stable native canvas. Reliable move/reorder/resize controls are provided instead; this is documented as a Phase 2 item.

### 2.6 AI Dashboard Assistant

- Parses commands into an explicit allowlist: `add_kpi`, `add_chart`, `add_table`, `set_theme`, `set_accent`, `change_chart_type`, `move_component`, `duplicate_component`, `delete_component`, `create_page`, `delete_page`, `rename_dashboard`, `add_filter`, `reset_dashboard`.
- Validates every referenced column against the uploaded schema.
- Validates every referenced component ID against the current dashboard.
- Flags destructive actions (`delete_*`, `reset_dashboard`) for confirmation.
- Optional LLM path: the model may only propose one allowlisted action as JSON. Non-allowlisted actions, invented columns, and invented component IDs are rejected and fall back to the rule-based parser or a safe message.
- Unknown commands return actionable suggestions, not fake success.

### 2.7 Verified chatbot and NLP

Workflow:

1. Rule-based NLP extracts intent, metric, dimension, aggregation, top-N, and period.
2. pandas computes the answer from the active, filtered DataFrame.
3. Response text is composed from those computed values.
4. An optional LLM may add labelled narrative, but never the numbers.

Implemented intents: total, average, count, top-N ranking, period comparison, distribution, explain/summary, derived AOV, derived profit margin. Period parsing is relative to the dataset's latest date (month names, quarters, this/last month/year, last N days, years).

Guardrails:

- No arbitrary Python execution.
- No arbitrary SQL execution.
- No unrestricted database access.
- Unknown questions explicitly say no number will be invented and offer real follow-up questions.

### 2.8 RAG document intelligence

- Input formats: TXT, MD/Markdown, JSON, CSV-like text (built in); PDF via optional `pypdf`; DOCX via optional `python-docx`.
- Extraction, whitespace cleaning, paragraph/sentence-aware chunking with overlap.
- Deterministic local hash embeddings (512 dimensions) when no embedding provider is configured.
- Cosine retrieval with relevance threshold, document replacement without duplicate chunks.
- Citations include document name, chunk index, score, and excerpt.
- With an LLM: answers are constrained to supplied context and must cite sources.
- Without an LLM: strict extractive answer built from retrieved sentences.
- No relevant content: returns a clear "no relevant content / nothing was invented" response.
- Store serialises to/from JSON without requiring ChromaDB/FAISS.

### 2.9 Insights and quality reporting

- Evidence-based insights: top-N concentration, trend direction, margin, missingness/data quality signals.
- Periods and comparison baselines are stated when used.
- Correlation is not presented as causation.
- Data Quality page uses factual profile data.
- CSV, Excel, and executive markdown report downloads are available.

### 2.10 Branding and navigation

- App title/tab/header/sidebar/nav/reports/footer: **RetailMind AI**.
- Tagline: **Understand Your Business. Predict Your Future. Grow Smarter.**
- Dark premium theme with 12-column visual grid and Altair charts.
- AI status is shown without secrets.
- Footer states Phase 1 scope and that analytics work without AI.

---

## 3. Architecture and file map

```
dashboard.py                  Streamlit app shell
retailmind/
  __init__.py
  config.py                   Branding, limits, AI env config, state dir
  utils.py                    Formatting, dates, CSV/Excel bytes, slugify
  models.py                   Component, Page, Theme, FilterConfig, DashboardConfig
  schema.py                   Profiling, aliases, roles, domains, manual mapping
  cleaning.py                 Suggestions, transparent cleaning, report
  engine.py                   Conditional auto dashboard/page/component generation
  render.py                   KPI/chart/table/insight/quality renderers
  filters.py                  Universal filters + summary
  storage.py                  Save/load/autosave/undo/redo
  ui.py                       CSS, branding, toolbar, footer
  compat.py                   Preserved legacy helper API
  ai/
    __init__.py
    provider.py               Optional provider client + local embeddings
    nlp.py                    Intent/entity/period parser
    chat.py                   Verified pandas chatbot
    assistant.py              Allowlisted actions + LLM proposal validation
    insights.py               Evidence-based insights
    rag.py                    Extraction, chunking, vector retrieval, citations
```

Preserved and reused: `analytics.py`, `data_sources.py`, `src/business/reports.py`, legacy `src/auth`, `src/storage`, database scripts, migrations, and historical data. No destructive database migration was run.

---

## 4. Testing report

### 4.1 Command

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp="$env:TEMP\retailmind-pytest"
```

### 4.2 Result

```
201 passed, 1 skipped in ~32s
```

### 4.3 New Phase 1 test coverage

| Test file | Tests | Focus |
| --- | --- | --- |
| `tests/test_retailmind_schema.py` | 9 | Retail/HR/education/expense role detection, text-column dimensions, manual mapping, confidence/candidates, round-trip, factual profile |
| `tests/test_retailmind_cleaning.py` | 8 | Non-mutation, row preservation, invalid numerics → missing, explicit zero-fill/duplicate removal, category variants, date coercion, suggestions, Arrow-safe summary |
| `tests/test_retailmind_engine_models.py` | 11 | Conditional generation, no invented columns/pages, no-measure dataset safety, JSON round-trip, page/component ops, save/load/delete/autosave, undo/redo |
| `tests/test_retailmind_nlp_chat.py` | 20 | Intent/entity/period parsing, pandas-verified totals/average/count/top/AOV/margin/compare/distribution, unknown handling, unmapped metric fallback |
| `tests/test_retailmind_assistant.py` | 22 | Theme/accent/KPI/chart/filter/page/reset parsing, destructive flags, validation, component ops, single-page protection, LLM allowlist/column/ID validation, unavailable-provider fallback |
| `tests/test_retailmind_rag_provider.py` | 17 | Extraction/chunking/retrieval/citations, no-fabrication paths, document replace/remove/clear/serialisation, optional dependency messages, local embeddings, JSON extraction, AI config and secret safety |
| **Total new** | **87** | |

Existing suites (analytics, data sources, auth, storage, enterprise, dashboard upload/filter integration) remain green. Dashboard AppTest contracts were preserved, including the `data_upload_999` uploader key, legacy retail filter behavior, and date parsing re-export.

### 4.4 Skipped

| Test | Reason |
| --- | --- |
| `tests/test_e2e_browser.py` | Playwright browser not installed. Set `RUN_E2E=1` after installing a browser to enable |

### 4.5 Environment issue (not an application failure)

On this Windows profile, pytest's default temp directory (`C:\Users\<user>\AppData\Local\Temp\pytest-of-<user>`) can raise `PermissionError: [WinError 5]`. This affects the legacy `tests/test_upload_storage.py` fixture setup when the default base temp is used. Running with `--basetemp` in a writable directory yields the full green result above. No application code was changed to work around OS permissions.

---

## 5. Requirement-by-requirement status

| # | Requirement | Status |
| --- | --- | --- |
| 1 | Upgrade existing project, preserve functionality | Done |
| 2 | Rebrand to RetailMind AI everywhere | Done |
| 3 | CSV/XLSX/XLS/multi-sheet + preview + validation + replacement | Done |
| 4 | Profiling, missing/duplicate detection, dimension/measure detection | Done |
| 5 | Universal semantic detection with aliases and manual correction | Done |
| 6 | Transparent cleaning, originals preserved, no silent deletion | Done |
| 7 | Dynamic dashboard only from available fields | Done |
| 8 | Auto + Custom modes, full visual/page management | Done (drag-and-drop limitation documented) |
| 9 | AI Dashboard Assistant actually applies validated changes | Done |
| 10 | Chatbot computes real numbers; LLM never invents numbers | Done |
| 11 | NLP intent/entity/column/metric/date/filter parsing | Done |
| 12 | RAG extraction/chunking/embeddings/retrieval/citations | Done (optional PDF/DOCX packages) |
| 13 | AI config via env vars, no hardcoded keys, no secrets in UI/logs, works without AI | Done |
| 14 | Safe uploads, limits, session isolation, caching, cleanup, clear errors | Done |
| 15 | No destructive DB migrations | Done |
| 16 | Mandatory real test execution with pass/fail/skip reporting | Done |
| 17 | README updated | Done |
| 18 | PHASE1_PROGRESS.md created | Done |
| 19 | No fake AI/data/buttons/placeholders | Done |
| 20 | No PBIX claim (Phase 2) | Done |

---

## 6. Known limitations and Phase 2 backlog

1. **Free-form drag-and-drop layout** — Streamlit canvas limitation; move/resize controls used instead.
2. **Per-user database dashboard persistence** — deferred until authentication is integrated into the new shell.
3. **Optional document dependencies** — `pypdf` and `python-docx` are not bundled; install messages are explicit.
4. **Vector store** — local hash index in Phase 1; ChromaDB/FAISS adapters are a future upgrade.
5. **PBIX / Power BI export** — explicitly Phase 2; not claimed in Phase 1.
6. **Forecasting/what-if scenarios** — Phase 2.
7. **Live connectors and scheduled refresh** — Phase 2.

---

## 7. Backup and change safety

The project is not a Git repository, so a safe backup was created before implementation:

```
C:\Users\ak837\AppData\Local\Temp\opencode\RetailMind_backup_20261107_135704.zip
```

The backup excludes `.venv` and caches. No source file was deleted; the original Streamlit dashboard was replaced in place and legacy APIs are retained through `retailmind/compat.py`.
