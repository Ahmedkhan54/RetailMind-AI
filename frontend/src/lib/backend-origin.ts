// Server-only helper for the direct-upload flow. It is deliberately framework
// free so it can be unit tested without a Next.js runtime.

/** Safe, generic message: never echoes the configured value or any secret. */
export const BACKEND_CONFIGURATION_ERROR =
  "The upload service is not configured correctly. Contact your administrator.";

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1"]);
const LOCAL_DEVELOPMENT_BACKEND = "http://127.0.0.1:8000";

export type BackendOriginResult =
  | { ok: true; origin: string }
  | { ok: false; detail: string };

function isLoopbackHost(hostname: string): boolean {
  // URL keeps IPv6 literals bracketed, e.g. "[::1]"; only the two documented
  // development hosts are accepted, so no IPv6 special-casing is needed.
  return LOOPBACK_HOSTS.has(hostname.toLowerCase());
}

/**
 * Validate `RETAILMIND_API_URL` and normalize it to its origin.
 *
 * Rules:
 * - HTTPS is always allowed.
 * - HTTP is allowed only for `localhost` / `127.0.0.1` outside production.
 * - Any other scheme, malformed value, or embedded username/password is rejected.
 *
 * Returning `url.origin` means a configured path, query, or fragment can never
 * change the ticket or upload target.
 */
export function resolveBackendOrigin(
  rawUrl: string | undefined,
  isProduction: boolean,
): BackendOriginResult {
  const candidate = rawUrl?.trim() || LOCAL_DEVELOPMENT_BACKEND;

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    return { ok: false, detail: BACKEND_CONFIGURATION_ERROR };
  }

  // Credentials in the URL would be forwarded with the ticket request.
  if (parsed.username || parsed.password) {
    return { ok: false, detail: BACKEND_CONFIGURATION_ERROR };
  }

  if (parsed.protocol === "https:") {
    return { ok: true, origin: parsed.origin };
  }

  if (parsed.protocol === "http:" && !isProduction && isLoopbackHost(parsed.hostname)) {
    return { ok: true, origin: parsed.origin };
  }

  return { ok: false, detail: BACKEND_CONFIGURATION_ERROR };
}

export const UPLOAD_TICKET_PATH = "/api/upload/ticket";
export const UPLOAD_DIRECT_PATH = "/api/upload/direct";

export type UploadEndpointsResult =
  | { ok: true; origin: string; ticketUrl: string; uploadUrl: string }
  | { ok: false; detail: string };

/**
 * Build both direct-upload endpoints from the single validated origin, so the
 * ticket request and the browser's upload target can never diverge.
 */
export function resolveUploadEndpoints(
  rawUrl: string | undefined,
  isProduction: boolean,
): UploadEndpointsResult {
  const resolved = resolveBackendOrigin(rawUrl, isProduction);
  if (!resolved.ok) return resolved;

  return {
    ok: true,
    origin: resolved.origin,
    ticketUrl: new URL(UPLOAD_TICKET_PATH, resolved.origin).toString(),
    uploadUrl: new URL(UPLOAD_DIRECT_PATH, resolved.origin).toString(),
  };
}
