/** @type {import('next').NextConfig} */

// ── API proxy target ──────────────────────────────────────────────────────────
// Read SERVER-SIDE ONLY, inside rewrites(). The browser never sees this value
// and must never be pointed at it directly: the backend's session cookies are
// SameSite=Strict, so a cross-site fetch to the backend origin silently drops
// them and login breaks in production only. Everything goes through the
// same-origin /api/:path* rewrite below instead (see lib/auth.tsx).
//
// NOTE: this is a BUILD-TIME value, whatever it is called. Next.js evaluates
// rewrites() during `next build` and freezes the result into
// .next/routes-manifest.json; the running server reads the manifest and never
// calls rewrites() again. Setting it only in a container's runtime
// `environment:` therefore has no effect — it must be passed as a build arg
// (see frontend/Dockerfile) or be present in the build environment (Vercel).
//
// API_PROXY_TARGET is the preferred name because this value is server-side
// only and must not be advertised as public. NEXT_PUBLIC_API_URL is kept as a
// fallback so existing Vercel/Render builds keep working unchanged, but it is
// deprecated for this purpose.
const API_PROXY_TARGET =
  process.env.API_PROXY_TARGET ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

const isProd = process.env.NODE_ENV === "production";

// ── Content-Security-Policy ───────────────────────────────────────────────────
// script-src keeps 'unsafe-inline' deliberately. Next.js's App Router streams
// hydration payloads as inline <script>self.__next_f.push(...)</script> tags
// that it emits itself, so they cannot be hash-pinned from here. The only
// supported alternative is a per-request nonce, which requires a middleware.ts
// — and a middleware that stamps a nonce forces EVERY route to render
// dynamically, which would drop all 21 statically-prerendered routes in this
// app to server-rendered. That is a real availability/latency cost for a
// defence-in-depth gain, so 'unsafe-inline' stays and is documented here
// rather than silently tolerated. (Adding a hash alongside it would be worse
// than useless: a CSP3 browser IGNORES 'unsafe-inline' the moment any hash or
// nonce is present, which would break hydration outright.)
//
// 'unsafe-eval' IS removed in production. It is only needed by the webpack dev
// server's eval-based source maps and React Fast Refresh; verified absent from
// the production bundle (no `eval(` / `new Function(` in any built chunk).
const scriptSrc = [
  "'self'",
  "'unsafe-inline'",
  // Google Identity Services (Sign in with Google) — components/GoogleSignInButton.tsx
  "https://accounts.google.com/gsi/client",
  ...(isProd ? [] : ["'unsafe-eval'"]),
];

const connectSrc = [
  "'self'",                              // API (same-origin rewrite) + SSE price stream
  "https://accounts.google.com",         // GIS token endpoint
  // Sentry ingest — only contacted when NEXT_PUBLIC_SENTRY_DSN is set.
  "https://*.ingest.sentry.io",
  "https://*.ingest.us.sentry.io",
  "https://*.ingest.de.sentry.io",
  ...(isProd ? [] : ["ws:", "http://localhost:8000"]),
];

const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",              // clickjacking — CSP-level counterpart to X-Frame-Options
  "form-action 'self'",
  `script-src ${scriptSrc.join(" ")}`,
  // React inline style props + Next's inlined critical CSS. No way to hash
  // these either; scope is limited to styles, which cannot execute.
  "style-src 'self' 'unsafe-inline'",
  // next/font/google self-hosts its font files at build time — no external
  // font origin is contacted.
  "font-src 'self' data:",
  // Company/fund logos come from arbitrary upstream https hosts (IndianAPI).
  "img-src 'self' data: https:",
  `connect-src ${connectSrc.join(" ")}`,
  // GIS renders its account chooser/consent UI in an iframe from this origin
  "frame-src 'self' https://accounts.google.com",
  "worker-src 'self' blob:",
].join("; ");

const nextConfig = {
  output: "standalone",

  // The repo root carries an empty, dependency-less package-lock.json, which
  // makes Next infer the monorepo root as the tracing root and warn. Pin it to
  // this directory so `output: "standalone"` traces the right file set.
  outputFileTracingRoot: __dirname,

  // Never ship .js.map files to production — they expose original source
  productionBrowserSourceMaps: false,

  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options",           value: "DENY" },
          { key: "X-Content-Type-Options",    value: "nosniff" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
          { key: "Referrer-Policy",           value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy",        value: "camera=(), microphone=(), geolocation=()" },
          { key: "Content-Security-Policy",   value: csp },
        ],
      },
      // Referrer-Policy override for the reset-password page specifically: the
      // reset token lives in this page's URL query string, and the default
      // policy above ("strict-origin-when-cross-origin") still leaks the full
      // URL — including the token — to same-origin destinations' Referer
      // header. "no-referrer" strips it entirely. Next.js applies the later-
      // matching entry's value on a collision, so this must come after the
      // global "/(.*)" entry above.
      {
        source: "/reset-password",
        headers: [{ key: "Referrer-Policy", value: "no-referrer" }],
      },
    ];
  },

  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_PROXY_TARGET}/api/:path*` },
    ];
  },
};

// Wraps the config with Sentry's build plugin (source map upload, etc).
// Safe with no Sentry account yet — org/project undefined and no
// SENTRY_AUTH_TOKEN just skips source map upload with a build-time warning,
// it doesn't fail the build. Actual error capture (instrumentation*.ts /
// sentry.*.config.ts) is separately gated on NEXT_PUBLIC_SENTRY_DSN.
const { withSentryConfig } = require("@sentry/nextjs");
module.exports = withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  silent: true,
  // Replaces the deprecated top-level `disableLogger` (removed in a future
  // @sentry/nextjs major) — strips Sentry's debug logging from the bundle.
  webpack: { treeshake: { removeDebugLogging: true } },
});
