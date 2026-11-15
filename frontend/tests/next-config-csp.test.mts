import { test, after } from "node:test";
import assert from "node:assert/strict";

// These tests load `next.config.ts` once per case (unique query string defeats
// the module cache) because the file reads NODE_ENV and RETAILMIND_API_URL at
// module scope.

const HTTPS_BACKEND = "https://api.retailmind.example";
const LOCAL_BACKEND = "http://127.0.0.1:8000";

// `@types/node` marks NODE_ENV read-only, but these tests must exercise both
// modes; the runtime object is a plain mutable record.
const env = process.env as Record<string, string | undefined>;

const originalNodeEnv = env.NODE_ENV;
const originalApiUrl = env.RETAILMIND_API_URL;

after(() => {
  if (originalNodeEnv === undefined) delete env.NODE_ENV;
  else env.NODE_ENV = originalNodeEnv;
  if (originalApiUrl === undefined) delete env.RETAILMIND_API_URL;
  else env.RETAILMIND_API_URL = originalApiUrl;
});

type HeaderEntry = { headers: Array<{ key: string; value: string }> };

async function loadConnectSrc(options: {
  production: boolean;
  apiUrl?: string;
}): Promise<string> {
  env.NODE_ENV = options.production ? "production" : "development";
  if (options.apiUrl === undefined) delete env.RETAILMIND_API_URL;
  else env.RETAILMIND_API_URL = options.apiUrl;

  const cacheBuster = `${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const imported = await import(`../next.config.ts?case=${cacheBuster}`);
  const config = imported.default as { headers?: () => Promise<HeaderEntry[]> };

  assert.ok(config.headers, "next.config.ts must expose headers()");
  const [entry] = await config.headers();
  const csp = entry.headers.find((header) => header.key === "Content-Security-Policy");

  assert.ok(csp, "Content-Security-Policy header missing");
  const directive = csp.value
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("connect-src"));

  assert.ok(directive, "connect-src directive missing");
  return directive;
}

test("includes a valid HTTPS backend origin", async () => {
  const connectSrc = await loadConnectSrc({ production: true, apiUrl: HTTPS_BACKEND });
  assert.ok(connectSrc.includes(HTTPS_BACKEND));
});

test("includes a development HTTP localhost backend origin", async () => {
  const connectSrc = await loadConnectSrc({ production: false, apiUrl: LOCAL_BACKEND });
  assert.ok(connectSrc.includes(LOCAL_BACKEND));
});

test("excludes a production HTTP localhost backend origin", async () => {
  const connectSrc = await loadConnectSrc({ production: true, apiUrl: LOCAL_BACKEND });
  assert.ok(!connectSrc.includes(LOCAL_BACKEND));
});

test("excludes a URL containing credentials", async () => {
  const connectSrc = await loadConnectSrc({
    production: true,
    apiUrl: "https://user:secret@api.retailmind.example",
  });
  assert.ok(!connectSrc.includes("api.retailmind.example"));
  assert.ok(!connectSrc.includes("user:secret"));
});

test("excludes an invalid URL", async () => {
  const connectSrc = await loadConnectSrc({ production: true, apiUrl: "not a url" });
  assert.equal(connectSrc, "connect-src 'self'");
});

test("includes the development localhost fallback when no URL is configured", async () => {
  const connectSrc = await loadConnectSrc({ production: false });
  assert.ok(connectSrc.includes(LOCAL_BACKEND));
});

test("excludes the localhost fallback in production when no URL is configured", async () => {
  const connectSrc = await loadConnectSrc({ production: true });
  assert.ok(!connectSrc.includes(LOCAL_BACKEND));
});

test("adds only the normalized origin, not a configured path", async () => {
  const connectSrc = await loadConnectSrc({
    production: true,
    apiUrl: `${HTTPS_BACKEND}/ignored/path`,
  });
  assert.ok(connectSrc.includes(HTTPS_BACKEND));
  assert.ok(!connectSrc.includes("/ignored/path"));
});
