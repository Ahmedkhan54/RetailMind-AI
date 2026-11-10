# RetailMind AI — Safe Cleanup Report

**Date:** 8 November 2026  
**Project root:** `C:\Users\ak837\OneDrive\Desktop\Retail-Sales-Profitability-Analysis (1)\Retail-Sales-Profitability-Analysis`  
**Backup before cleanup:** `C:\Users\ak837\RetailMind_Backups\backup-20261108-162210` (885 files, taken before source changes)

---

## Classification policy

- **A — Safe generated artifacts:** reproducible caches/build outputs. Deleted after backup.
- **B — Useful project files:** source, tests, docs, config, datasets. Kept.
- **C — User-created files:** scratch/diagnostic scripts and user datasets. Kept (no deletion approval).
- **D — Unknown/ambiguous:** kept pending confirmation; listed here for review.

No `.venv`, `.env`, `.gitignore`, `requirements.txt`, source file, test, report, Power BI artifact, or user scratch file was deleted.

---

## A. Deleted generated artifacts

| Path | Reason |
|:---|:---|
| `__pycache__/` (project root) | Bytecode cache; fully reproducible by Python. |
| `tmp_pytest_final/` | Pytest baseline artifact from the final full-suite run. |
| `tmp_pytest_buttons/` | Pytest artifact from the button-audit run. |
| `tmp_pytest_render/` | Pytest artifact from table-rendering tests. |
| `tmp_pytest_render2/` | Pytest artifact (re-run after test fix). |
| `tmp_pytest_pbip/` | Pytest artifact from PBIP tests. |
| `tmp_pytest_pbip2/` | Pytest artifact (re-run after schema fixes). |

`.pytest_cache/` at the project root **could not be deleted** — `PermissionError: [WinError 5] Access is denied` (file locked by the OS, same condition that blocked the initial backup). It is a regenerable pytest cache, harmless, and excluded from backups by the project's `.gitignore` intent.

## B. Kept — useful project files

All source under `retailmind/`, `dashboard.py`, `analytics.py`, `data_sources.py`, all `tests/`, `docs/`, `data/`, `.streamlit/`, `.github/`, `requirements.txt`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `pytest.ini`, `run_dashboard.bat`, `diag_streamlit.err`, `diag_streamlit.out`, `benchmark_results.json`, `audit_*.py`, all `*.md` reports including legacy `PROJECT_AUDIT.md` and `PHASE1_PROGRESS.md` (superseded banners retained for traceability).

## C. Kept — user-created / scratch files (no deletion approval)

Per the project rules, user-created scratch files are **not** deleted without explicit approval, and audit scripts are kept until final verification:

- `scratch/benchmark_performance.py` (pre-existing)
- `scratch/repro_final_bugs.py` (this session: reproduced BUGs 1–3 before fixing)
- `scratch/validate_pbip_schema.py` (this session: validates all 24 PBIP JSON files against Microsoft's published schemas)
- `scratch/profile_ui.py` (this session: AppTest end-to-end timing harness)
- `scratch/cprof_warm.py` (this session: cProfile of a warm rerun)
- `scratch/debug_mode_radio.py` (this session: widget lookup diagnostic)
- `scratch/peek.py`, `scratch/fix_emoji.py` (this session: report-editing diagnostics)
- `debug_forecast.py`, `debug_perf.py`, `test_audit.py`, `test_sample_data.py`, `test_simple.py`, `test_retail_sales.csv` (pre-existing user scratch)

## D. Left untouched (pre-existing temp dirs; prior decision)

`tmpux6txfra/`, `tmp_apptest/`, `tmp_py311_diag/` were left untouched per the earlier project decision ("other temp dirs left untouched"). They are outside the pytest baseline pattern and may contain user diagnostics; confirm before deleting.

---

## Files removed and why

Only category-A reproducible caches listed above were removed. No source, test, dataset, report, or PBIP file was removed.

## Verification after cleanup

- Full pytest suite re-run green after cache deletion: **266 passed, 1 skipped, 0 failed**.
- `python -m compileall` (excluding `.venv`) clean.
- `git` is not initialized; no commits exist, so cleanup is uncommitted local work like everything else in this session.
