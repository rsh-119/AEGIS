// Registers the Sentry server/edge config for whichever runtime Next.js is
// running in, and hooks Server Component / middleware errors into Sentry.
// See instrumentation-client.ts for the browser-side init.
import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
