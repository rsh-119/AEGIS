"use client";

import { useState } from "react";
import clsx from "clsx";

const AVATAR_COLORS = [
  "bg-blue-500", "bg-emerald-500", "bg-violet-500", "bg-rose-500",
  "bg-amber-500", "bg-cyan-500", "bg-pink-500", "bg-orange-500",
  "bg-teal-500", "bg-indigo-500",
];

export function avatarColor(ticker: string) {
  let h = 0;
  for (let i = 0; i < ticker.length; i++) h = (h * 31 + ticker.charCodeAt(i)) & 0xff;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

/** Company logo via free Clearbit domain lookup, falling back to a colored
 * ticker-initials avatar if there's no website or the image fails to load. */
export function StockLogo({ ticker, website, size = 9 }: { ticker: string; website?: string | null; size?: number }) {
  const [err, setErr] = useState(false);
  const bare = ticker.replace(/\.(NS|BO)$/, "");

  let domain: string | null = null;
  if (website && !err) {
    try {
      domain = new URL(website).hostname.replace(/^www\./, "");
    } catch { /* invalid URL — fall through */ }
  }

  const sz = `h-${size} w-${size}`;

  if (domain) {
    return (
      <div className={clsx(`${sz} shrink-0 rounded-xl overflow-hidden border border-border bg-surface flex items-center justify-center`)}>
        <img
          src={`https://logo.clearbit.com/${domain}`}
          alt={bare}
          className="h-full w-full object-contain p-1"
          onError={() => setErr(true)}
        />
      </div>
    );
  }

  return (
    <div className={clsx(`flex ${sz} shrink-0 items-center justify-center rounded-xl text-xs font-bold text-white`, avatarColor(bare))}>
      {bare.slice(0, 2)}
    </div>
  );
}
