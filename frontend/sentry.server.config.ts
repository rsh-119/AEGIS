// Server-side (Node.js runtime) Sentry init — loaded by instrumentation.ts.
// No-op until NEXT_PUBLIC_SENTRY_DSN is set.
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    tracesSampleRate: 0.1,
  });
}
