import { resolveUploadEndpoints } from "@/lib/backend-origin";

type TicketPayload = { token?: string; expires_in?: number; detail?: string };

/**
 * Mint a single-use upload ticket through the authenticated same-origin proxy.
 *
 * The browser then uploads the file straight to the backend, which sidesteps
 * the Netlify 6 MB buffered-request limit. The session cookie stays on the
 * same-origin call; the direct request carries only the short-lived ticket.
 */
export async function POST(request: Request) {
  // Server-side only: the validated origin is never hardcoded into client code.
  // A rejection returns a generic configuration error so no environment value
  // or credential is ever echoed to the browser.
  const endpoints = resolveUploadEndpoints(
    process.env.RETAILMIND_API_URL,
    process.env.NODE_ENV === "production",
  );
  if (!endpoints.ok) {
    return Response.json({ detail: endpoints.detail }, { status: 500 });
  }

  const headers = new Headers({ "content-type": "application/json" });
  if (process.env.RETAILMIND_API_TOKEN) {
    headers.set("authorization", `Bearer ${process.env.RETAILMIND_API_TOKEN}`);
  }
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);

  try {
    const response = await fetch(endpoints.ticketUrl, {
      method: "POST",
      headers,
      body: "{}",
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    });
    const payload = (await response.json().catch(() => ({}))) as TicketPayload;
    if (!response.ok || !payload.token) {
      return Response.json(
        { detail: payload.detail || "Could not start the upload. Sign in again and retry." },
        { status: response.status || 502 },
      );
    }
    return Response.json({
      token: payload.token,
      expires_in: payload.expires_in ?? 600,
      // Same validated origin as the ticket call, so the client never guesses it.
      upload_url: endpoints.uploadUrl,
    });
  } catch {
    return Response.json(
      { detail: "The upload service is unavailable right now. Wait a moment and retry." },
      { status: 503 },
    );
  }
}
