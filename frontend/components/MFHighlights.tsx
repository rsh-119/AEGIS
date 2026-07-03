"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Star, TrendingUp, TrendingDown, Zap, Loader2 } from "lucide-react";
import clsx from "clsx";

// ─── Types ────────────────────────────────────────────────────────────────────
type Period = "1y" | "3y" | "5y";

type HFund = {
  scheme_code?: number;
  ticker?: string;
  name: string;
  nav?: number | null;
  price?: number | null;
  return_1d?: number | null;
  return_1y?: number | null;
  return_3y?: number | null;
  return_5y?: number | null;
  day_change_pct?: number | null;
  volume?: number | null;
  fund_house?: string;
};

type Highlights = {
  popular:     HFund[];
  top_gainers: HFund[];
  top_losers:  HFund[];
  most_active: HFund[];
};

const EMPTY: Highlights = { popular: [], top_gainers: [], top_losers: [], most_active: [] };

// ─── Category config ──────────────────────────────────────────────────────────
type Cat = {
  key:   keyof Highlights;
  label: string;
  sub:   string;
  icon:  React.ElementType;
  ring:  string;
  bg:    string;
  text:  string;
  head:  string;
};

const CATS: Cat[] = [
  {
    key:  "popular",
    label: "Most Popular",
    sub:   "Flagship funds from top AMCs",
    icon:  Star,
    ring:  "ring-saffron/25",
    bg:    "bg-saffron/5",
    text:  "text-saffron",
    head:  "bg-saffron/10",
  },
  {
    key:  "top_gainers",
    label: "Top Returns",
    sub:   "Highest performers this period",
    icon:  TrendingUp,
    ring:  "ring-up/25",
    bg:    "bg-up/5",
    text:  "text-up",
    head:  "bg-up/10",
  },
  {
    key:  "top_losers",
    label: "Underperformers",
    sub:   "Lowest returns this period",
    icon:  TrendingDown,
    ring:  "ring-down/25",
    bg:    "bg-down/5",
    text:  "text-down",
    head:  "bg-down/10",
  },
  {
    key:  "most_active",
    label: "Most Active",
    sub:   "Biggest movers today",
    icon:  Zap,
    ring:  "ring-accent/25",
    bg:    "bg-accent/5",
    text:  "text-accent",
    head:  "bg-accent/10",
  },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────
function shortName(name: string, max = 30): string {
  if (name.length <= max) return name;
  // Strip common suffixes to keep it short
  return name
    .replace(/\s*[-–]\s*(direct plan|direct|plan|growth|fund)\s*/gi, " ")
    .trim()
    .slice(0, max)
    .trim() + "…";
}

function RetChip({ v, label }: { v: number | null | undefined; label?: string }) {
  if (v == null) return <span className="text-[10px] text-muted">—</span>;
  const up = v >= 0;
  return (
    <span className={clsx(
      "tabular-nums text-xs font-bold",
      up ? "text-up" : "text-down",
    )}>
      {up ? "+" : ""}{v.toFixed(1)}%{label ? ` ${label}` : ""}
    </span>
  );
}

// ─── Single fund row inside a category card ───────────────────────────────────
function FundRow({ fund, cat, period, isMF }: {
  fund: HFund;
  cat: Cat;
  period: Period;
  isMF: boolean;
}) {
  const href = isMF
    ? `/mf/${fund.scheme_code}`
    : `/mf/etf_${encodeURIComponent(fund.ticker ?? "")}`;

  const retVal  = fund[`return_${period}` as keyof HFund] as number | null;
  const activeV = isMF ? fund.return_1d : (fund.day_change_pct ?? fund.return_1d);
  const showV   = cat.key === "most_active" ? activeV : retVal;
  const showLbl = cat.key === "most_active" ? "1D" : period.toUpperCase();

  const displayName = isMF
    ? shortName(fund.name)
    : (fund.ticker?.replace(".NS", "") ?? fund.name);

  return (
    <Link href={href} className="flex items-center justify-between gap-2 rounded-xl px-3 py-2 transition-colors hover:bg-raised/60 group">
      <div className="min-w-0">
        <p className="truncate text-xs font-semibold text-fg group-hover:text-saffron transition-colors leading-tight">
          {displayName}
        </p>
        {isMF && fund.fund_house && (
          <p className="truncate text-[10px] text-muted leading-tight mt-0.5">{fund.fund_house}</p>
        )}
        {!isMF && fund.name && (
          <p className="truncate text-[10px] text-muted leading-tight mt-0.5 max-w-[140px]">{fund.name}</p>
        )}
      </div>
      <RetChip v={showV} label={showLbl} />
    </Link>
  );
}

// ─── Category card ────────────────────────────────────────────────────────────
function CatCard({ cat, funds, period, isMF }: {
  cat: Cat;
  funds: HFund[];
  period: Period;
  isMF: boolean;
}) {
  const Icon = cat.icon;
  return (
    <div className={clsx(
      "flex-1 min-w-[200px] rounded-2xl ring-1 overflow-hidden",
      cat.ring,
    )}>
      {/* Header */}
      <div className={clsx("flex items-center gap-2 px-3 py-2.5", cat.head)}>
        <div className={clsx("flex h-7 w-7 items-center justify-center rounded-xl", cat.bg)}>
          <Icon className={clsx("h-3.5 w-3.5", cat.text)} />
        </div>
        <div>
          <p className={clsx("text-xs font-bold", cat.text)}>{cat.label}</p>
          <p className="text-[10px] text-muted">{cat.sub}</p>
        </div>
      </div>

      {/* Fund rows */}
      <div className="divide-y divide-border/40 px-1 py-1">
        {funds.length === 0 ? (
          <p className="py-4 text-center text-[11px] text-muted">No data yet</p>
        ) : (
          funds.slice(0, 5).map((f, i) => (
            <FundRow key={f.scheme_code ?? f.ticker ?? i} fund={f} cat={cat} period={period} isMF={isMF} />
          ))
        )}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export function MFHighlights({ type, period }: { type: "mf" | "etf"; period: Period }) {
  const [data, setData]       = useState<Highlights>(EMPTY);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const url = type === "mf"
      ? `/api/mf/highlights?period=${period}`
      : `/api/etf/highlights`;

    fetch(url)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [type, period]);

  if (loading) {
    return (
      <div className="flex gap-3 overflow-x-auto pb-1">
        {CATS.map(c => (
          <div key={c.key} className="min-w-[200px] flex-1 rounded-2xl ring-1 ring-border overflow-hidden">
            <div className="h-10 skeleton" />
            <div className="divide-y divide-border/30">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="px-3 py-2.5 flex items-center justify-between gap-2">
                  <div className="h-3 w-28 rounded skeleton" />
                  <div className="h-3 w-10 rounded skeleton" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  const isEmpty = CATS.every(c => data[c.key].length === 0);
  if (isEmpty) return null;

  return (
    <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-none">
      {CATS.map(cat => (
        <CatCard
          key={cat.key}
          cat={cat}
          funds={data[cat.key]}
          period={period}
          isMF={type === "mf"}
        />
      ))}
    </div>
  );
}
