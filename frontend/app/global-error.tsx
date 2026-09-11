"use client";

/**
 * Root error boundary for the App Router.
 *
 * This is the LAST resort: it only renders when an error escapes the root
 * layout itself, which means the layout — <Nav>, providers, theme, global CSS —
 * did not mount. Next.js therefore requires this component to render its own
 * <html>/<body>, and none of the app's normal chrome or design tokens are
 * available here. The styling below is deliberately inline and self-contained
 * for that reason, not an inconsistency with the rest of the UI.
 *
 * Sentry's Next.js SDK cannot see React render errors in the App Router unless
 * they are handed to it from a global-error boundary — without this file the
 * build warns and those errors are simply never reported. Sentry.captureException
 * no-ops when NEXT_PUBLIC_SENTRY_DSN is unset (see instrumentation-client.ts),
 * so this works with or without a Sentry account.
 *
 * Nothing about the error is shown to the visitor beyond Next's own `digest`
 * — a short server-generated correlation id, not a message, stack or path.
 * That is what support can match against the Sentry event; leaking the message
 * itself can disclose internals.
 */

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0b0d10",
          color: "#e6e8eb",
          fontFamily:
            "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
          padding: "24px",
        }}
      >
        <main style={{ maxWidth: "420px", textAlign: "center" }}>
          <p
            style={{
              margin: "0 0 8px",
              fontSize: "12px",
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "#7c8694",
            }}
          >
            Aegis
          </p>
          <h1 style={{ margin: "0 0 12px", fontSize: "20px", fontWeight: 600 }}>
            Something went wrong
          </h1>
          <p style={{ margin: "0 0 20px", fontSize: "14px", lineHeight: 1.6, color: "#a4adba" }}>
            The page failed to load. This has been reported automatically — try
            again, and if it keeps happening come back in a few minutes.
          </p>
          <button
            type="button"
            onClick={() => reset()}
            style={{
              appearance: "none",
              border: "1px solid #2b313a",
              borderRadius: "8px",
              background: "#151a20",
              color: "#e6e8eb",
              padding: "9px 18px",
              fontSize: "14px",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
          {error.digest && (
            <p style={{ margin: "18px 0 0", fontSize: "11px", color: "#5d6772" }}>
              Reference: {error.digest}
            </p>
          )}
        </main>
      </body>
    </html>
  );
}
