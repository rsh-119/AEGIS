"use client";

import { useEffect, useState } from "react";
import { Analytics } from "@vercel/analytics/next";
import { getConsent, subscribeConsent } from "@/lib/cookieConsent";

/**
 * Vercel Web Analytics, gated on the cookie banner's choice. Renders nothing
 * until the visitor has opted in — mounting <Analytics/> is what fires its
 * first beacon, so "not rendered" is the same as "not tracked".
 * Reactive via subscribeConsent so accepting mid-session starts tracking
 * without a reload; declining does not retroactively delete an already-sent
 * beacon, but stops any further ones.
 */
export function ConsentedAnalytics() {
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    setAllowed(getConsent() === "all");
    return subscribeConsent((choice) => setAllowed(choice === "all"));
  }, []);

  if (!allowed) return null;
  return <Analytics />;
}
