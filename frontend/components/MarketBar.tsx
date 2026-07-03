"use client";

import useSWR from "swr";
import Link from "next/link";
import { fetcher } from "@/lib/api";
import { TrendingUp, TrendingDown } from "lucide-react";
import clsx from "clsx";

type Index = {
  name: string;
  price: number;
  change_pts: number;
  change_pct: number;
};

// Internal route slugs for each index
const INDEX_SLUGS: Record<string, string> = {
  "Nifty 50":      "/index/nifty50",
  "Nifty Next 50": "/index/niftynext50",
  "Bank Nifty":    "/index/banknifty",
  "Nifty IT":      "/index/niftyit",
  "Nifty Pharma":  "/index/niftypharma",
};

export function MarketBar() {
  const { data } = useSWR<Index[]>("/api/market/indices", fetcher, {
    revalidateOnFocus: false,
    refreshInterval: 15_000,   // NSE API via backend cache — fast and cheap
  });

  const indices: Index[] = data ?? [];

  if (!indices.length) {
    return (
      <div className="border-b border-border bg-surface/60 backdrop-blur-sm">
        <div className="mx-auto flex max-w-screen-xl gap-6 overflow-x-auto px-3 py-2 sm:px-6">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-4 w-28 shrink-0 rounded" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="border-b border-border bg-surface/70 backdrop-blur-sm">
      <div
        className="flex items-center gap-1 overflow-x-auto px-4 py-1.5 sm:px-6 md:px-10 lg:px-14"
        style={{ scrollbarWidth: "none" }}
      >
        {indices.map((idx) => {
          const up = idx.change_pct >= 0;
          const href = INDEX_SLUGS[idx.name] ?? "#";
          return (
            <Link
              key={idx.name}
              href={href}
              className={clsx(
                "flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 transition-all duration-150",
                "hover:bg-raised/80 hover:shadow-sm cursor-pointer group"
              )}
              title={`View ${idx.name} chart`}
            >
              <span className="text-xs font-semibold text-fg/70 whitespace-nowrap group-hover:text-fg transition-colors">
                {idx.name}
              </span>
              <span className="nums text-xs font-bold text-fg whitespace-nowrap">
                {idx.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </span>
              <span className={clsx(
                "flex items-center gap-0.5 text-[11px] font-bold whitespace-nowrap",
                up ? "text-up" : "text-down"
              )}>
                {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                {up ? "+" : ""}{idx.change_pct.toFixed(2)}%
                <span className="ml-0.5 text-[10px] font-normal opacity-70">
                  ({up ? "+" : ""}{idx.change_pts.toFixed(1)})
                </span>
              </span>

              {/* Separator */}
              <span className="ml-1 h-4 w-px bg-border/60 shrink-0" />
            </Link>
          );
        })}

        <span className="ml-auto shrink-0 text-[10px] text-muted whitespace-nowrap pl-2">
          ~1 min delay · click to open exchange
        </span>
      </div>
    </div>
  );
}
