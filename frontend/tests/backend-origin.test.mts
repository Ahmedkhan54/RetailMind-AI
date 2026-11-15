import { test } from "node:test";
import assert from "node:assert/strict";

import {
  BACKEND_CONFIGURATION_ERROR,
  resolveBackendOrigin,
  resolveUploadEndpoints,
} from "../src/lib/backend-origin.ts";

test("accepts an HTTPS backend URL in production", () => {
  assert.deepEqual(resolveBackendOrigin("https://api.retailmind.example", true), {
    ok: true,
    origin: "https://api.retailmind.example",
  });
});

test("accepts HTTP loopback hosts during local development", () => {
  for (const url of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
    assert.deepEqual(resolveBackendOrigin(url, false), { ok: true, origin: url });
  }
});

test("rejects HTTP in production", () => {
  assert.deepEqual(resolveBackendOrigin("http://api.retailmind.example", true), {
    ok: false,
    detail: BACKEND_CONFIGURATION_ERROR,
  });
});

test("rejects HTTP loopback in production", () => {
  assert.deepEqual(resolveBackendOrigin("http://127.0.0.1:8000", true), {
    ok: false,
    detail: BACKEND_CONFIGURATION_ERROR,
  });
});

test("rejects URLs containing a username or password", () => {
  for (const url of [
    "https://user:secret@api.retailmind.example",
    "https://user@api.retailmind.example",
    "http://user:secret@localhost:8000",
  ]) {
    assert.deepEqual(resolveBackendOrigin(url, false), {
      ok: false,
      detail: BACKEND_CONFIGURATION_ERROR,
    });
  }
});

test("normalizes the configured URL to its origin", () => {
  assert.deepEqual(
    resolveBackendOrigin("https://api.retailmind.example/some/path/?debug=1#frag", true),
    { ok: true, origin: "https://api.retailmind.example" },
  );
  assert.deepEqual(resolveBackendOrigin("  https://api.retailmind.example:8443/  ", true), {
    ok: true,
    origin: "https://api.retailmind.example:8443",
  });
});

test("rejects malformed and non-HTTP(S) URLs", () => {
  for (const url of ["not a url", "ftp://api.retailmind.example", "file:///tmp/api"]) {
    assert.deepEqual(resolveBackendOrigin(url, false), {
      ok: false,
      detail: BACKEND_CONFIGURATION_ERROR,
    });
  }
});

test("configuration errors never echo the configured value", () => {
  const configured = "https://user:totally-secret@api.retailmind.example";
  const result = resolveBackendOrigin(configured, true);

  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.detail, BACKEND_CONFIGURATION_ERROR);
  assert.ok(!result.detail.includes("totally-secret"));
  assert.ok(!result.detail.includes("api.retailmind.example"));
});

test("unset configuration falls back to the documented local backend only in development", () => {
  assert.deepEqual(resolveBackendOrigin(undefined, false), {
    ok: true,
    origin: "http://127.0.0.1:8000",
  });
  assert.deepEqual(resolveBackendOrigin("   ", false), {
    ok: true,
    origin: "http://127.0.0.1:8000",
  });
  assert.deepEqual(resolveBackendOrigin(undefined, true), {
    ok: false,
    detail: BACKEND_CONFIGURATION_ERROR,
  });
});

test("uses the normalized origin for both the ticket and upload endpoints", () => {
  const result = resolveUploadEndpoints(
    "https://api.retailmind.example/ignored/path?token=abc#frag",
    true,
  );

  assert.deepEqual(result, {
    ok: true,
    origin: "https://api.retailmind.example",
    ticketUrl: "https://api.retailmind.example/api/upload/ticket",
    uploadUrl: "https://api.retailmind.example/api/upload/direct",
  });
});

test("keeps the configured port and path-free origin for both endpoints", () => {
  const result = resolveUploadEndpoints("http://127.0.0.1:8000/proxy/", false);

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.ticketUrl, "http://127.0.0.1:8000/api/upload/ticket");
  assert.equal(result.uploadUrl, "http://127.0.0.1:8000/api/upload/direct");
});

test("rejects invalid configuration before building either endpoint", () => {
  for (const url of ["http://api.retailmind.example", "https://user:pw@api.retailmind.example"]) {
    assert.deepEqual(resolveUploadEndpoints(url, true), {
      ok: false,
      detail: BACKEND_CONFIGURATION_ERROR,
    });
  }
});
