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

The adapter is additive; it does not modify `dashboard.py` or the Streamlit business logic. Uploads are held in API-process memory and are cleared on restart. It is a local integration scaffold, not a multi-user production service: deploy a separately authenticated Python API and durable per-user dataset storage before exposing uploaded business data publicly.

For a remote API, set `RETAILMIND_API_URL` in the Next.js server environment. If `RETAILMIND_API_TOKEN` is set on both services, the Next.js proxy sends it as a bearer token and the Python API enforces it. Keep these values server-side; do not use `NEXT_PUBLIC_` variables for the token.
