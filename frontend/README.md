# RetailMind AI frontend

This is the separate Next.js 16 + React + TypeScript interface for RetailMind AI. The Python/Streamlit application remains at the repository root and is still available as a standalone fallback.

## Run locally

Use two terminals from the repository root.

Terminal 1 — Python analytics API:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r api-requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The Next.js server proxies `/api/retailmind/*` requests to `http://127.0.0.1:8000` by default, so browser requests do not need cross-origin access.

## Implemented API routes

- `GET /api/health`
- `POST /api/upload` — CSV/XLS/XLSX/XLSM parsing, 25 MB cap, schema mapping, and quality summary
- `GET /api/dashboard/overview/{dataset_id}` — existing KPI and grouped analytics functions
- `GET /api/analytics/{dataset_id}/{dimension}` — monthly, category, product, city, or customer breakdowns
- `POST /api/ai/chat` — existing Pandas-grounded, verified business assistant
- `GET /api/ai/insights/{dataset_id}` and `/api/ai/alerts/{dataset_id}` — rule-based observations and evidence-backed alerts
- `GET /api/segmentation/{dataset_id}` and `/api/inventory/{dataset_id}` — existing RFM/K-Means and stock recommendation modules
- `POST /api/forecast` — existing forecast engine, with a validated metric, frequency, and horizon
- `GET /api/export/{dataset_id}/{csv|xlsx|pdf|pbip}` — CSV, workbook, executive PDF, or validated PBIP ZIP

The adapter is additive; it does not modify `dashboard.py` or the Streamlit business logic. Uploaded bytes live behind the Python backend's storage backend (local filesystem by default, or a private Cloudflare R2 bucket when `RETAIL_UPLOAD_STORAGE_BACKEND=r2`), while TiDB/MySQL keeps only upload metadata. Parsed DataFrames stay in API-process memory and are re-read from storage after a restart. Set `RETAILMIND_API_URL` to a separately authenticated Python API before exposing uploaded business data publicly.

For a remote API, set `RETAILMIND_API_URL` in the Next.js server environment. If `RETAILMIND_API_TOKEN` is set on both services, the Next.js proxy sends it as a bearer token and the Python API enforces it. Keep these values server-side; do not use `NEXT_PUBLIC_` variables for the token.

### Large uploads (above Netlify's 6 MB Function limit)

Netlify Functions buffer request bodies and reject anything over 6 MB, so ordinary
API traffic stays on the same-origin proxy while **file uploads go directly to the
Python backend**:

1. The browser calls `POST /api/retailmind/upload-ticket` (same-origin; the
   existing session cookie authenticates it).
2. That route mints a short-lived, single-use ticket from the backend and returns
   the backend's `/api/upload/direct` URL derived from `RETAILMIND_API_URL`.
3. The browser uploads the multipart file to that URL with an
   `Authorization: Bearer <ticket>` header. No cookie is sent cross-origin.

Required configuration:

- `RETAILMIND_API_URL` must be present at **build time** (so the CSP `connect-src`
  allows the backend origin) and at **runtime** (so the ticket route can derive
  the direct URL).
- On the backend, set `RETAILMIND_UPLOAD_ORIGINS` to the exact production site
  origin (comma-separated, no wildcard). It falls back to
  `RETAILMIND_PUBLIC_ORIGIN`.
- `RETAIL_UPLOAD_STORAGE_DIR` must point at a durable Render disk; the default
  local path is ephemeral on Render and not suitable for production.
- For persistent production uploads set `RETAIL_UPLOAD_STORAGE_BACKEND=r2` plus
  `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and
  `R2_BUCKET_NAME` on the **backend only**. The bucket stays private; the frontend
  never receives R2 credentials or presigned URLs. If R2 configuration is
  incomplete the backend refuses to start rather than falling back to disk.
- Excel workbooks default to a 5 MB ceiling when `RENDER=true` (override with
  `RETAIL_MAX_EXCEL_UPLOAD_BYTES`). CSV uploads keep the 25 MB limit.
