// Client-side Sentry init. No-op until NEXT_PUBLIC_SENTRY_DSN is set — same
// fail-closed-until-configured pattern used for the backend's SENTRY_DSN
// (see backend/app/main.py).
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NODE_ENV,
    tracesSampleRate: 0.1,          // 10% of page loads/navigations traced
    replaysSessionSampleRate: 0,    // no session replay by default (privacy)
    replaysOnErrorSampleRate: 0,
  });
}
