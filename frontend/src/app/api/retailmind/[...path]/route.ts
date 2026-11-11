type RouteContext = { params: Promise<{ path: string[] }> };

async function proxyRequest(request: Request, context: RouteContext) {
  const { path } = await context.params;
  const incomingUrl = new URL(request.url);
  const backendBase = process.env.RETAILMIND_API_URL || "http://127.0.0.1:8000";
  const backendPath = path[0] === "retailmind" ? path.slice(1) : path;
  const target = new URL(`/api/${backendPath.map(encodeURIComponent).join("/")}${incomingUrl.search}`, backendBase);
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  if (process.env.RETAILMIND_API_TOKEN) {
    headers.set("authorization", `Bearer ${process.env.RETAILMIND_API_TOKEN}`);
  }
  const cookie = request.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      // Do not let a stalled upstream hold the browser request open forever.
      signal: AbortSignal.timeout(60000),
    });
    const responseHeaders = new Headers();
    for (const header of ["content-type", "content-disposition", "cache-control", "set-cookie", "x-cleaning-report"]) {
      const value = response.headers.get(header);
      if (value) responseHeaders.set(header, value);
    }
    if (!responseHeaders.has("content-type")) responseHeaders.set("content-type", "application/json");
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  } catch {
    return Response.json(
      { detail: "The Python analytics API is unavailable. Start the local API or configure RETAILMIND_API_URL." },
      { status: 503 },
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const DELETE = proxyRequest;
