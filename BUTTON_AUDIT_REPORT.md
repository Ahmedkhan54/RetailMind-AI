# RetailMind AI — Button & Interaction Audit

**Version:** 2.0.0-phase2
**Audit date:** 8 November 2026
**Entrypoint:** `dashboard.py`
**Method:** Streamlit `AppTest` interaction tests + source inspection + independent UI audit (`audit_ui.py`)

---

## 1. Summary

- **Catalogued controls:** ~131 (uploads, filters, builder, pages, themes, assistant, chat, RAG, alerts, segmentation, inventory, forecasting, Power BI, exports).
- **Controls driven end-to-end in AppTest:** every page navigation (all 6 auto pages), all 17 download buttons, and the majority of interactive controls — `tests/test_button_audit.py` passes **17/17** and the repro harness clicked every download button and every page tab without script errors.
- **Controls found broken:** **0** among those exercised (the `NameError: _measure_label` that previously errored table pages on click is fixed).
- **Controls inspected but not clicked:** page reorder, apply-appearance, save-as-new, dashboard rename. Their handlers exist and are wired to the same persistence helpers as tested controls.
- **Controls not testable in this environment:** SMTP email send, live LLM provider, Power BI Desktop open/save.

The earlier report claimed “131/131 verified”. That was too strong: its 17-test suite does **not** drive the alerts, segmentation, inventory, forecasting, or Power BI panels. Those were covered by the additional `audit_ui.py` harness (9 checks, all passing).

---

## 2. Verification tiers

### Tier A — driven end-to-end in Streamlit AppTest

| Area | Interactions actually exercised |
|:---|:---|
| Upload | CSV upload, Excel upload, worksheet switch, empty upload error path |
| Cleaning | Duplicate-row toggle; cleaning suggestions/rebuild |
| Mapping | Manual revenue mapping + apply; role selectboxes present |
| Filters | Category/city multiselect, universal search, reset filters, dataset removal |
| Builder | Add visual; edit title/type/dimension/measure/width/height/colour; duplicate; delete with confirmation; move-up boundary warning; undo; redo |
| Pages | Add, rename, duplicate, delete; last page protected; navigation clicks on all 6 auto pages render without error |
| Persistence | Save, autosave, restore snapshot, reset to original |
| Assistant | Add KPI, add region filter, reset with confirmation, unknown-command rejection |
| Chatbot | Ask question (verified numeric answer), clear conversation, empty-question warning |
| RAG | Upload/index document, ask document question (citation shown), clear knowledge base |
| AI status | Connection test with no provider → graceful warning |
| Alerts | Severity filter, status filter, acknowledge click persisted, CSV download rendered |
| Segmentation | k slider (2–6), CSV/Excel download buttons |
| Inventory | Lead, safety days, service level, target cover; CSV/Excel downloads |
| Forecasting | Metric, frequency, horizon, method; CSV/Excel downloads |
| Power BI | PBIP ZIP and theme JSON download buttons |
| Exports | Cleaned CSV/Excel, markdown, executive workbook, executive PDF, business PDF, PBIP quick downloads; all 17 download buttons clicked via `AppTest` |

**Evidence**
- `tests/test_button_audit.py` — 17 tests.
- `tests/test_dashboard_upload.py` / `test_dashboard_filters.py` — upload and filter behaviour.
- `audit_ui.py` — 9/9 independent checks (alerts, segmentation, inventory, forecasting, PBIP, provider, downloads).

### Tier B — source-inspected, not clicked

| Control | Why not clicked | Assessment |
|:---|:---|:---|
| Move page left / right | No dedicated AppTest | Same `move_page` helper used by tested visual move logic; appears wired |
| Apply appearance | No dedicated AppTest | Sets theme in session state; CSS injection tested indirectly by rendering |
| Save as new dashboard | No dedicated AppTest | Uses same storage helpers as tested save/restore |
| Rename dashboard | No dedicated AppTest | Form handler updates config name |
| Notification preferences | Inputs render | Only the email send path is blocked (see Tier C) |

These are **not** claimed as executed; they are code-reviewed only.

### Tier C — not testable here

| Control | Reason |
|:---|:---|
| Send test alert email | No SMTP server/credentials. Unit tests mock `smtplib` only. |
| Use LLM fallback / live provider | No API key; deterministic fallback tested instead. |
| Open in Power BI Desktop / Save as `.pbix` | Power BI Desktop is not installed. |

---

## 3. Corrections to the previous button report

| Previous claim | Reality |
|:---|:---|
| "258 passed in 63.67 s" | **266 passed, 1 skipped** in 123.91 s (project-local `--basetemp` required). |
| “Zero warnings” | Streamlit emits `use_container_width` deprecation warnings. |
| “All 131 controls verified” | 131 catalogued; most driven, 4 inspected only, 3 not testable. |
| “17 end-to-end tests cover every control” | The 17 tests do not cover Phase-2 alert/segmentation/inventory/forecasting/PBIP widgets; these required `audit_ui.py`. |
| “SMTP email dispatch verified” | Not verified end-to-end; only mocked unit tests. |

---

## 4. Findings

1. **No broken buttons** were found among the controls exercised. Click handlers update session state and rerun as expected.
2. **Download buttons** produce real payloads. Independently checked: CSV (BOM + parseable), XLSX (`PK` + openable via pandas/openpyxl), PDF (`%PDF` + expected text), ZIP (`PK`).
3. **Safety gates work**: delete visual/page and reset/restore require confirmation; the last page cannot be deleted.
4. **Boundary feedback works**: moving the first visual up produces an explicit warning instead of failing silently.
5. **Alerts state persists** across reruns via session state; acknowledging changes the stored alert status.
6. **Missing-data paths are handled**: segmentation/inventory/forecast show explanatory messages rather than errors when required columns are absent.

---

## 5. Reproduce

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_button_audit.py tests/test_dashboard_upload.py tests/test_dashboard_filters.py -q -p no:cacheprovider --basetemp=./tmp_buttons --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_retailmind_powerbi.py tests/test_retailmind_render_tables.py -q -p no:cacheprovider --basetemp=./tmp_buttons2 --tb=short
.\.venv\Scripts\python.exe audit_ui.py
```

Expected: button/upload/filter suites pass; `audit_ui.py` reports **9 passed, 0 failed**.
