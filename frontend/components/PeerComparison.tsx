"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, inrCompact, inr, num } from "@/lib/api";
import { Users, ArrowUpRight, Star, ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import Link from "next/link";
import clsx from "clsx";

type Peer = {
  ticker: string;
  name: string;
  price: number;
  day_change_pct: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  roe: number | null;
  revenue_growth: number | null;
  debt_to_equity: number | null;
  profit_margin: number | null;
  dividend_yield: number | null;
};

type SectorAvg = Record<string, number | null>;
type SortDir = "asc" | "desc" | null;
type SortKey = keyof Peer | null;

// ─── Small sort icon ──────────────────────────────────────────────────────────
function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active || dir === null) return <ArrowUpDown className="h-3 w-3 text-muted/40" />;
  return dir === "asc"
    ? <ArrowUp className="h-3 w-3 text-saffron" />
    : <ArrowDown className="h-3 w-3 text-saffron" />;
}

function Cell({ val, good, bad }: { val: string; good?: boolean; bad?: boolean }) {
  return (
    <td className={clsx(
      "nums px-3 py-2.5 text-right text-sm whitespace-nowrap",
      good && "text-up font-medium",
      bad && "text-down font-medium",
      !good && !bad && "text-fg/80"
    )}>
      {val}
    </td>
  );
}

type ColDef = {
  key: keyof Peer;
  label: string;
  format: (v: any) => string;
  hint: string;
  good?: (v: any, avg: SectorAvg) => boolean;
  bad?: (v: any, avg: SectorAvg) => boolean;
};

const COLS: ColDef[] = [
  {
    key: "price",
    label: "Price",
    format: (v) => inr(v),
    hint: "Current market price",
  },
  {
    key: "market_cap",
    label: "Mkt Cap",
    format: (v) => inrCompact(v),
    hint: "Market capitalisation",
  },
  {
    key: "pe_ratio",
    label: "P/E",
    format: (v) => num(v),
    hint: "Price to Earnings (trailing)",
    good: (v, avg) => v != null && avg.pe_ratio != null && v < avg.pe_ratio,
    bad: (v, avg) => v != null && avg.pe_ratio != null && v > avg.pe_ratio * 1.3,
  },
  {
    key: "pb_ratio",
    label: "P/B",
    format: (v) => num(v),
    hint: "Price to Book",
    good: (v, avg) => v != null && avg.pb_ratio != null && v < avg.pb_ratio,
  },
  {
    key: "roe",
    label: "ROE",
    format: (v) => v != null ? `${(v * 100).toFixed(1)}%` : "—",
    hint: "Return on Equity",
    good: (v, avg) => v != null && avg.roe != null && v > avg.roe,
    bad: (v, avg) => v != null && avg.roe != null && v < avg.roe * 0.7,
  },
  {
    key: "revenue_growth",
    label: "Rev Growth",
    format: (v) => v != null ? `${(v * 100).toFixed(1)}%` : "—",
    hint: "Revenue growth YoY",
    good: (v) => v != null && v > 0.1,
    bad: (v) => v != null && v < 0,
  },
  {
    key: "profit_margin",
    label: "Net Margin",
    format: (v) => v != null ? `${(v * 100).toFixed(1)}%` : "—",
    hint: "Net profit margin",
    good: (v, avg) => v != null && avg.profit_margin != null && v > avg.profit_margin,
    bad: (v) => v != null && v < 0,
  },
  {
    key: "debt_to_equity",
    label: "D/E",
    format: (v) => num(v),
    hint: "Debt to Equity ratio",
    good: (v, avg) => v != null && avg.debt_to_equity != null && v < avg.debt_to_equity,
    bad: (v) => v != null && v > 200,
  },
  {
    key: "dividend_yield",
    label: "Div Yield",
    format: (v) => v != null ? `${(v * 100).toFixed(2)}%` : "—",
    hint: "Dividend yield",
  },
  {
    key: "day_change_pct",
    label: "1D Chg",
    format: (v) => v != null ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—",
    hint: "Today's price change",
    good: (v) => (v ?? 0) > 0,
    bad: (v) => (v ?? 0) < 0,
  },
];

export function PeerComparison({ ticker, selfName, selfData }: {
  ticker: string;
  selfName: string;
  selfData?: Record<string, any>;
}) {
  const { data, isLoading } = useSWR(`/api/stocks/${ticker}/peers`, fetcher, {
    revalidateOnFocus: false,
  });

  const [sortKey, setSortKey] = useState<SortKey>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);

  const toggleSort = (key: keyof Peer) => {
    if (sortKey === key) {
      if (sortDir === "asc") setSortDir("desc");
      else if (sortDir === "desc") { setSortKey(null); setSortDir(null); }
      else setSortDir("asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  if (isLoading) {
    return (
      <div className="card p-5">
        <div className="mb-4 flex items-center gap-2">
          <Users className="h-4 w-4 text-saffron" />
          <h2 className="font-medium">Peer Comparison</h2>
        </div>
        <div className="skeleton h-48 w-full rounded-lg" />
      </div>
    );
  }

  const peers: Peer[] = data?.peers ?? [];
  const avg: SectorAvg = data?.sector_avg ?? {};
  const sector: string = data?.sector ?? "";

  if (!peers.length) {
    return (
      <div className="card p-5">
        <div className="mb-3 flex items-center gap-2">
          <Users className="h-4 w-4 text-saffron" />
          <h2 className="font-medium">Peer Comparison</h2>
        </div>
        <p className="text-sm text-muted">Peer data not available for this sector.</p>
      </div>
    );
  }

  // Sort peers
  const sortedPeers = sortKey
    ? [...peers].sort((a, b) => {
        const av = a[sortKey] as number | null;
        const bv = b[sortKey] as number | null;
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return sortDir === "asc" ? av - bv : bv - av;
      })
    : peers;

  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-saffron" />
          <h2 className="font-medium">Peer Comparison</h2>
          {sector && (
            <span className="pill bg-raised text-muted ring-1 ring-border text-[10px]">{sector}</span>
          )}
        </div>
        <span className="text-xs text-muted">{peers.length} peers · click headers to sort</span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-raised/60">
              <th className="px-3 py-2.5 text-left text-[11px] font-medium uppercase tracking-wide text-muted sticky left-0 bg-raised/80 backdrop-blur-sm min-w-[140px]">
                Company
              </th>
              {COLS.map((c) => (
                <th
                  key={c.key}
                  title={c.hint}
                  onClick={() => toggleSort(c.key)}
                  className="px-3 py-2.5 text-right text-[11px] font-medium uppercase tracking-wide text-muted whitespace-nowrap cursor-pointer select-none hover:text-fg hover:bg-raised transition-colors"
                >
                  <span className="inline-flex items-center gap-1 justify-end">
                    {c.label}
                    <SortIcon active={sortKey === c.key} dir={sortKey === c.key ? sortDir : null} />
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {/* ── THIS STOCK (pinned, highlighted) ── */}
            {selfData && (
              <tr className="border-b-2 border-saffron/40 bg-gradient-to-r from-saffron/10 via-saffron/5 to-transparent">
                <td className="sticky left-0 bg-saffron/10 px-3 py-3 backdrop-blur-sm">
                  <div className="flex items-center gap-2 min-w-[130px]">
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-saffron/20">
                      <Star className="h-3.5 w-3.5 text-saffron fill-saffron" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-saffron">{ticker.replace(/\.(NS|BO)$/, "")}</p>
                      <p className="truncate text-[10px] text-saffron/70 max-w-[110px]">{selfName}</p>
                      <span className="text-[9px] font-bold text-saffron uppercase tracking-wider">This stock</span>
                    </div>
                  </div>
                </td>
                {COLS.map((c) => {
                  const v = selfData[c.key];
                  const isGood = c.good?.(v, avg);
                  const isBad = c.bad?.(v, avg);
                  return (
                    <td key={c.key} className={clsx(
                      "nums px-3 py-3 text-right text-sm font-bold whitespace-nowrap",
                      isGood ? "text-up" : isBad ? "text-down" : "text-saffron"
                    )}>
                      {c.format(v)}
                    </td>
                  );
                })}
              </tr>
            )}

            {/* ── Sector median row ── */}
            <tr className="bg-saffron/5 border-b-2 border-saffron/20">
              <td className="sticky left-0 bg-saffron/5 px-3 py-2.5">
                <span className="text-xs font-semibold text-saffron">Sector Median</span>
              </td>
              {COLS.map((c) => {
                const v = avg[c.key as string];
                return (
                  <td key={c.key} className="nums px-3 py-2.5 text-right text-xs font-semibold text-saffron whitespace-nowrap">
                    {v != null ? c.format(v) : "—"}
                  </td>
                );
              })}
            </tr>

            {/* ── Peer rows ── */}
            {sortedPeers.map((p) => (
              <tr key={p.ticker} className="transition hover:bg-raised/50">
                <td className="sticky left-0 bg-surface px-3 py-2.5 backdrop-blur-sm">
                  <div className="flex items-center gap-2 min-w-[130px]">
                    <div>
                      <Link
                        href={`/stock/${encodeURIComponent(p.ticker)}`}
                        className="text-sm font-medium hover:text-saffron flex items-center gap-1"
                      >
                        {p.ticker.replace(/\.(NS|BO)$/, "")}
                        <ArrowUpRight className="h-3 w-3 text-muted" />
                      </Link>
                      <p className="truncate text-[10px] text-muted max-w-[120px]">{p.name}</p>
                    </div>
                  </div>
                </td>
                {COLS.map((c) => {
                  const v = p[c.key];
                  const isGood = c.good?.(v, avg);
                  const isBad = c.bad?.(v, avg);
                  return (
                    <Cell key={c.key} val={c.format(v)} good={isGood} bad={isBad} />
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[10px] text-muted">
        Green = better than sector median · Red = weaker · Click column headers to sort ↑↓ · Hover for definitions
      </p>
    </div>
  );
}
