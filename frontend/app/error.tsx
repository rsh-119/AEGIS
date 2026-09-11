"use client";

/**
 * Route-level error boundary.
 *
 * Without this file, ANY render error on any page escapes all the way to
 * app/global-error.tsx — which replaces the entire document, nav and footer
 * included, with a bare "something went wrong" screen. One page failing then
 * looks identical to the whole application being down, and the visitor has no
 * way to navigate anywhere else.
 *
 * This boundary keeps the root layout mounted (nav, footer, providers, theme)
 * and replaces only the page body, so the rest of the site stays usable. It
 * was found by an E2E test navigating to a stock page whose upstream returned
 * an unexpected shape: the whole shell disappeared.
 *
 * As with global-error, nothing about the error is shown beyond Next's
 * `digest` — a correlation id, not a message or stack.
 */

import * as Sentry from "@sentry/nextjs";
import Link from "next/link";
import { useEffect } from "react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function RouteError({
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
    <Card className="mx-auto my-16 flex max-w-md flex-col items-center gap-3 px-6 py-14 text-center">
      <p className="font-semibold">This page couldn&apos;t be loaded</p>
      <p className="text-sm text-muted">
        Something went wrong rendering this view. The rest of Aegis is still
        working — try again, or head back to the dashboard.
      </p>
      <div className="mt-1 flex gap-2">
        <Button onClick={() => reset()}>Try again</Button>
        <Button asChild variant="ghost">
          <Link href="/">Go to dashboard</Link>
        </Button>
      </div>
      {error.digest && (
        <p className="mt-2 text-[11px] text-muted">Reference: {error.digest}</p>
      )}
    </Card>
  );
}
