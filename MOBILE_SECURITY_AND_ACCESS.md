# Mobile Security & Access (Problem 61)

This document records the root causes, the code changes that were made, the
verification evidence, and the exact remaining deployment steps for secure
mobile access to RetailMind AI. It is deliberately honest about what could not
be executed in this environment (no domain, no TLS certificate, no physical
Android/iOS device).

---

## 1. Problem statement

The app must be usable from Android Chrome and other mobile browsers over a
secure connection without disabling SSL, without bypassing authentication, and
without weakening session handling.

Reported/likely failure modes:

| Symptom | Root cause |
|---|---|
| Sign-in works on desktop but not on a phone / session is lost | `Secure` cookie forced on an HTTP origin (browser silently drops it), or cookie not forwarded by the same-origin proxy |
| Browser blocks API calls as “mixed content” | Frontend loaded over HTTPS while calling `http://` API directly from the browser |
| CORS errors when the API is opened from another origin | No CORS policy is configured (calls are expected through the same-origin proxy) — the fix is to keep traffic same-origin rather than enabling credentialed wildcard CORS |
| Charts/tables overflow or are unusable on small screens | Missing responsive rules and viewport safe-area handling |
| CSV/Excel upload fails on Android | Android Chrome reports inconsistent MIME types for spreadsheets; validation keyed on MIME type only |
| Session cookie readable by scripts | Cookie not `HttpOnly` |

---

## 2. What was implemented

### 2.1 HTTPS / secure cookies

- `src/auth/api.py`
  - Session cookie remains `HttpOnly`, `SameSite=Lax`, `Path=/`, with an 8-hour
    lifetime.
  - `Secure` is now decided by `_cookie_secure()`:
    1. explicit `RETAILMIND_COOKIE_SECURE=true|false` wins;
    2. otherwise `VERCEL_ENV=production|preview` enables it;
    3. otherwise a `RETAILMIND_PUBLIC_ORIGIN` starting with `https://` enables it;
    4. otherwise it stays off so local HTTP development still works.
  - This prevents the classic “login succeeds but the session disappears”
    failure on plain HTTP while guaranteeing `Secure` in production.
- `.env.example` documents `RETAILMIND_COOKIE_SECURE`,
  `RETAILMIND_PUBLIC_ORIGIN`, `RETAILMIND_API_TOKEN`, and
  `RETAILMIND_API_URL`.

### 2.2 No mixed content, no cross-origin credentials

- The browser talks only to Next.js same-origin routes under
  `/api/retailmind/...` (`frontend/src/app/api/retailmind/[...path]/route.ts`).
  That route proxies to the Python API server-side and forwards the session
  cookie. The Python API stays private.
- No CORS middleware is added to the Python app, and no wildcard
  `Access-Control-Allow-Origin` with credentials is introduced. Same-origin
  traffic means CORS is not needed.
- `RETAILMIND_API_TOKEN` (optional) is attached server-side by the proxy; it is
  never exposed to the browser.

### 2.3 Security headers and CSP

`frontend/next.config.ts` sets, for `/:path*`:

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security: max-age=63072000`
- `X-Frame-Options: SAMEORIGIN`
- `X-DNS-Prefetch-Control: off`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Content-Security-Policy`:
  - `default-src 'self'`, `base-uri 'self'`, `object-src 'none'`,
    `frame-ancestors 'self'`, `form-action 'self'`
  - `img-src 'self' data: blob:`, `font-src 'self' data:`
  - `style-src 'self' 'unsafe-inline'` (required by Next.js runtime styles)
  - `script-src 'self' 'unsafe-inline'`; `'unsafe-eval'`/`blob:` only in
    development
  - `connect-src 'self'`; `ws:`/`wss:` only in development
  - `worker-src 'self' blob:`, `manifest-src 'self'`, `media-src 'self'`
  - `upgrade-insecure-requests` in production

`'unsafe-inline'` for scripts is a deliberate, documented trade-off: Next.js
injects inline hydration/bootstrap scripts without a per-request nonce. The
policy still blocks third-party script origins and keeps `connect-src`
same-origin. If a nonce-based policy is added later, it must be implemented in
middleware together with Next.js nonce support; do not simply remove
`'unsafe-inline'` or hydration will break.

### 2.4 Mobile viewport and responsive layout

- `frontend/src/app/layout.tsx`: `viewportFit: "cover"` so safe-area insets are
  available on notched devices; `width=device-width`, `initialScale: 1`.
- Existing responsive rules collapse the sidebar into a sheet, stack grids, and
  make tables horizontally scrollable (`.table-wrap`).
- Chart containers use `ResponsiveContainer`, so charts re-measure on
  orientation change and resize.
- The reference-video work (see `RETAILMIND_VIDEO_ANALYSIS.md`) added mobile
  stacking for the donut/gauge/analytics layouts.

### 2.5 Mobile CSV/Excel upload

- `frontend/src/components/feature-pages.tsx`: the dataset file input now
  accepts extensions **and** MIME types:
  `.csv,.xlsx,.xls,.xlsm,text/csv,` plus the three Excel MIME types.
- Backend validation is content/extension based rather than trusting the
  browser MIME string, which is what Android Chrome frequently reports
  incorrectly. `tests/test_mobile_upload.py` covers Android-style MIME
  variations.

---

## 3. Verification evidence

| Check | Result | Evidence |
|---|---|---|
| Frontend lint | Pass | `node node_modules/eslint/bin/eslint.js src` → no output |
| Frontend types | Pass | `node node_modules/typescript/bin/tsc --noEmit` → no output |
| Production build | Pass | `next build --webpack` → compiled, TypeScript, 41/41 static pages |
| Python regression suite | **Pass** — 319 passed, 5 skipped, 0 failed | `pytest tests/ -q` (44.36 s) |
| Cookie flags and HTTPS logic | **Pass** | `tests/test_api_adapter_security.py` asserts HttpOnly, session secret never returned, and `Secure` follows `RETAILMIND_COOKIE_SECURE`/HTTPS/VERCEL configuration |
| Android-style MIME uploads | Covered by `tests/test_mobile_upload.py` | simulated MIME types + content sniffing |
| CSP / headers emitted at runtime | Pass | `next start` + request to `/login` returned `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`, `Permissions-Policy`, `X-DNS-Prefetch-Control`. A build with `RETAILMIND_PUBLIC_ORIGIN=https://…` also adds `upgrade-insecure-requests`. |
| Responsive behaviour | Code review + CSS breakpoints | **not** verified on a physical device |

### Known limitations (must be closed before signing off)

- **No physical Android/iOS device** was available. Responsive CSS, viewport
  config and the simulated upload tests are the only automated evidence.
- **No deployment/domain/certificate access**, so TLS, HSTS on a real host,
  and real-device cookie behaviour were not exercised end-to-end.
- **Live MySQL-backed sign-in** may be unavailable in this environment, so the
  authenticated browser flow could not always be reproduced.

These are environment constraints, not code claims. Do not mark the physical
device check as complete until someone runs the checklist in section 5.

---

## 4. Production deployment steps (exact)

### 4.1 DNS

1. Create an `A` (IPv4) and/or `AAAA` (IPv6) record for the app host, e.g.
   `app.example.com`, pointing at the reverse proxy / load balancer.
2. Wait for propagation (`nslookup app.example.com`).

### 4.2 TLS certificate

Use a managed certificate (e.g. Let's Encrypt via Caddy/certbot, or the
platform's managed certificate).

Caddy example:

```caddy
app.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:3000
}
```

Nginx example:

```nginx
server {
    listen 443 ssl http2;
    server_name app.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    client_max_body_size 50m;   # dataset uploads

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

server {
    listen 80;
    server_name app.example.com;
    return 301 https://$host$request_uri;
}
```

> The browser must only ever see HTTPS. Keep the Python API bound to
> `127.0.0.1:8000` (or a private network) and let the Next.js proxy reach it.

### 4.3 Environment variables

Production frontend/API environment:

```env
# HTTPS is in use, so the session cookie must be Secure
RETAILMIND_COOKIE_SECURE=true
RETAILMIND_PUBLIC_ORIGIN=https://app.example.com

# Server-side proxy target (private); do NOT expose this to the browser
RETAILMIND_API_URL=http://127.0.0.1:8000

# Optional service-to-service token shared by proxy and API
RETAILMIND_API_TOKEN=<long-random-value>

# Existing database and upload storage settings
MYSQL_HOST=...
MYSQL_PORT=3306
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DATABASE=retail_sales_db
RETAIL_UPLOAD_STORAGE_DIR=/var/lib/retail-user-uploads
```

Notes:

- Never commit the real `.env`.
- `RETAILMIND_COOKIE_SECURE=false` only for plain-HTTP local development.
- `RETAILMIND_PUBLIC_ORIGIN` is evaluated when the frontend is **built**,
  because Next.js writes the CSP into `.next/routes-manifest.json`. Set it
  before `npm run build` and keep it in the runtime environment (the Python API
  also uses it as a cookie fallback). Rebuild after changing it. If it is unset,
  the app still emits CSP and HSTS, but omits `upgrade-insecure-requests`.
- Put `RETAIL_UPLOAD_STORAGE_DIR` on durable, private storage (not serverless
  ephemeral disk).

### 4.4 Start commands

```bash
# Python API (private)
uvicorn api:app --host 127.0.0.1 --port 8000

# Next.js (public via reverse proxy)
cd frontend
RETAILMIND_PUBLIC_ORIGIN=https://app.example.com npm run build
npm run start        # binds :3000 by default
```

### 4.5 Post-deploy smoke checks

```bash
curl -I https://app.example.com/overview
# Expect: 200/307, Strict-Transport-Security, Content-Security-Policy,
#         X-Content-Type-Options, Referrer-Policy, X-Frame-Options

curl -I http://app.example.com/
# Expect: 301 redirect to https://
```

In the browser devtools on the phone:

1. Application → Cookies → the session cookie must show **Secure**, **HttpOnly**,
   **SameSite=Lax**, `Path=/`.
2. Console must show **no** mixed-content or CSP violations.
3. Network must show all API calls going to `https://app.example.com/api/...`
   (same origin), never to `http://...:8000`.

---

## 5. Android Chrome manual test checklist

Run this on a real device before declaring Problem 61 verified.

- [ ] Open `https://app.example.com` — padlock present, no certificate warning.
- [ ] Sign in; reload the page; stay signed in.
- [ ] Navigate between Overview, Analytics, Upload, Datasets, Preferences.
- [ ] Rotate portrait ↔ landscape; no horizontal page overflow.
- [ ] Open the menu; the navigation opens as a sheet and closes after selecting.
- [ ] KPI cards, donut, gauge, bar/area charts render and resize correctly.
- [ ] Tables scroll horizontally inside their card, not the whole page.
- [ ] Upload a small CSV from device storage.
- [ ] Upload an `.xlsx` from device storage (Google Drive/Files picker).
- [ ] Confirm the uploaded dataset appears and the dashboard recalculates.
- [ ] Open devtools remote debugging; confirm no CSP/mixed-content errors.
- [ ] Toggle “Animate charts and KPI counters” in Preferences; confirm it
      applies and persists after reload.
- [ ] Enable the OS “Remove animations” setting; reload; confirm charts do not
      animate.
- [ ] Sign out; confirm the session cookie is cleared and protected pages
      redirect to sign-in.

Record the device model, Android version, Chrome version, and date with the
result.

---

## 6. Rollback / troubleshooting

| Symptom | Check |
|---|---|
| Login loops back to sign-in | Is the site HTTPS? Set `RETAILMIND_COOKIE_SECURE=true` only when HTTPS is actually in use. |
| Cookie missing after login | Proxy must forward `Set-Cookie` (the Next route already does). Check the reverse proxy is not stripping it. |
| 503 from `/api/retailmind/...` | `RETAILMIND_API_URL` unreachable, or Python API not running. |
| 401 despite valid session | `RETAILMIND_API_TOKEN` mismatch between proxy and API. |
| CSP blocks a resource | Prefer same-origin bundling. Do not add `*` to `script-src`/`connect-src`. |
| Upload rejected on phone | Confirm the file is CSV/XLSX and the backend parser accepts the content; MIME type alone is not used. |
