"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Cookie } from "lucide-react";
import { getConsent, setConsent } from "@/lib/cookieConsent";

/**
 * First-visit cookie banner. Shown once per browser (or until the
 * STORAGE_VERSION in lib/cookieConsent.ts bumps). "Necessary only" still
 * lets the app function fully — auth/session cookies aren't optional and
 * aren't gated by this; only opt-in tracking (Vercel Analytics, see
 * layout.tsx) reads this choice.
 */
export function CookieConsent() {
  // Undecided in SSR/first paint either way, so start hidden and only flip
  // on in an effect — avoids a hydration mismatch from reading localStorage
  // during render, and avoids flashing the banner for returning visitors.
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (getConsent() === null) setVisible(true);
  }, []);

  function decide(choice: "all" | "necessary") {
    setConsent(choice);
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label="Cookie preferences"
      className="animate-fade-up fixed inset-x-3 bottom-3 z-[90] sm:inset-x-auto sm:bottom-5 sm:left-5 sm:max-w-sm"
    >
      <div className="rounded-2xl border border-border bg-surface p-4 shadow-lg shadow-black/10">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-saffron/10">
            <Cookie className="h-4 w-4 text-saffron" />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-fg">Cookies, kept to what's needed</p>
            <p className="mt-1 text-[13px] leading-relaxed text-muted">
              Aegis uses essential cookies to keep you signed in. With your OK, it also
              uses analytics cookies to see which features are actually useful.{" "}
              <Link href="/privacy#cookies" className="text-saffron hover:underline">
                What&apos;s in each
              </Link>
              .
            </p>
          </div>
        </div>
        <div className="mt-3.5 flex items-center justify-end gap-2">
          <button
            onClick={() => decide("necessary")}
            className="rounded-lg px-3 py-1.5 text-xs font-semibold text-muted transition-colors hover:bg-raised hover:text-fg"
          >
            Necessary only
          </button>
          <button
            onClick={() => decide("all")}
            className="rounded-lg bg-saffron px-3.5 py-1.5 text-xs font-bold text-white transition-colors hover:bg-saffron/90"
          >
            Accept all
          </button>
        </div>
      </div>
    </div>
  );
}
