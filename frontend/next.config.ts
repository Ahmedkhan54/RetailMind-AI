import type { NextConfig } from "next";
import { resolveBackendOrigin } from "./src/lib/backend-origin.ts";

const isProduction = process.env.NODE_ENV === "production";
const servesHttps =
  process.env.RETAILMIND_PUBLIC_ORIGIN?.startsWith("https://") ||
  process.env.VERCEL_ENV === "production" ||
  process.env.VERCEL_ENV === "preview";

// The direct upload route sends the file straight to the Python backend, so its
// exact origin must be allowed in connect-src. It reuses the upload-ticket
// route's validation, so CSP can never allow an origin the backend call would
// reject (HTTP outside development, embedded credentials, malformed values).
// When validation fails, no origin is added.
function backendOrigin(): string | null {
  const resolved = resolveBackendOrigin(process.env.RETAILMIND_API_URL, isProduction);
  return resolved.ok ? resolved.origin : null;
}

const uploadConnectOrigin = backendOrigin();

// Pragmatic same-origin CSP. Next.js injects inline hydration scripts without a
// nonce, so 'unsafe-inline' is required for scripts/styles. connect-src stays
// same-origin except for the configured backend origin used by direct uploads.
const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  `script-src 'self' 'unsafe-inline'${isProduction ? "" : " 'unsafe-eval' blob:"}`,
  `connect-src 'self'${uploadConnectOrigin ? ` ${uploadConnectOrigin}` : ""}${isProduction ? "" : " ws: wss:"}`,
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "media-src 'self'",
  ...(isProduction && servesHttps ? ["upgrade-insecure-requests"] : []),
].join("; ");

const nextConfig: NextConfig = {
  /* config options here */
  async redirects() {
    return [{ source: "/", destination: "/overview", permanent: false }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Strict-Transport-Security", value: "max-age=63072000" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-DNS-Prefetch-Control", value: "off" },
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
  devIndicators: false,
  // cacheComponents and partialPrefetching are disabled for stable builds on Windows
  // cacheComponents: true,
  // partialPrefetching: true,
  experimental: {
    cpus: 1,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
