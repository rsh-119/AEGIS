"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, inrCompact, num } from "@/lib/api";
import { GitCompareArrows, ChevronRight, Search, TrendingUp, TrendingDown, Users } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { StockLogo } from "@/components/StockLogo";

/* ─── Types ──────────────────────────────────────── */
type SectorMeta = { sector: string; count: number; tickers: string[] };
type PeerRow = {
  ticker: string;
  name: string;
  price?: number;
  change_pct?: number;
  market_cap?: number;
  pe_ratio?: number;
  pb_ratio?: number;
  roe?: number;
  revenue_growth?: number;
  net_income?: number | null;
  debt_to_equity?: number;
  dividend_yield?: number;
  return_1y?: number | null;
  return_3y?: number | null;
  return_5y?: number | null;
  website?: string | null;
};

/* ─── Sector colors ──────────────────────────────── */
const SECTOR_COLORS: Record<string, string> = {
  "Technology":             "bg-blue-500/10 text-blue-500 ring-blue-500/20",
  "Financial Services":     "bg-emerald-500/10 text-emerald-500 ring-emerald-500/20",
  "Energy":                 "bg-orange-500/10 text-orange-500 ring-orange-500/20",
  "Consumer Defensive":     "bg-purple-500/10 text-purple-500 ring-purple-500/20",
  "Consumer Cyclical":      "bg-pink-500/10 text-pink-500 ring-pink-500/20",
  "Healthcare":             "bg-red-500/10 text-red-500 ring-red-500/20",
  "Industrials":            "bg-yellow-500/10 text-yellow-600 ring-yellow-500/20",
  "Basic Materials":        "bg-stone-500/10 text-stone-500 ring-stone-500/20",
  "Real Estate":            "bg-teal-500/10 text-teal-500 ring-teal-500/20",
  "Communication Services": "bg-indigo-500/10 text-indigo-500 ring-indigo-500/20",
  "Utilities":              "bg-cyan-500/10 text-cyan-500 ring-cyan-500/20",
};
function sectorColor(s: string) {
  return SECTOR_COLORS[s] ?? "bg-saffron/10 text-saffron ring-saffron/20";
}


/* ─── Build comparison rows: target + top 10 by mkt cap ── */
function buildRows(allStocks: PeerRow[], targetTicker: string): PeerRow[] {
  const target = allStocks.find((s) => s.ticker === targetTicker);

  // Sort rest by market_cap desc, take top 10
  const others = allStocks
    .filter((s) => s.ticker !== targetTicker)
    .filter((s) => s.market_cap != null)
    .sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0))
    .slice(0, 10);

  // Put target first, then the top-10 peers
  return target ? [target, ...others] : others;
}

/* ─── Column config ──────────────────────────────── */
const COLS = [
  { key: "market_cap",          label: "Mkt Cap",    fmt: (v: number) => inrCompact(v),                                   growth: false },
  { key: "pe_ratio",            label: "P/E",        fmt: (v: number) => num(v),                                          growth: false },
  { key: "pb_ratio",            label: "P/B",        fmt: (v: number) => num(v),                                          growth: false },
  { key: "roe",                 label: "ROE",        fmt: (v: number) => `${(v * 100).toFixed(1)}%`,                     growth: false },
  { key: "revenue_growth",      label: "Sales %",    fmt: (v: number) => `${v >= 0 ? "▲" : "▼"} ${Math.abs(v * 100).toFixed(1)}%`, growth: true },
  { key: "net_income",          label: "Net Profit", fmt: (v: number) => inrCompact(v),                                   growth: false },
  { key: "debt_to_equity",      label: "D/E",        fmt: (v: number) => num(v),                                          growth: false },
  { key: "dividend_yield",      label: "Div Yield",  fmt: (v: number) => `${(v * 100).toFixed(2)}%`,                     growth: false },
  { key: "return_1y",           label: "1Y Return",  fmt: (v: number) => `${v >= 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(1)}%`,      growth: true },
  { key: "return_3y",           label: "3Y Return",  fmt: (v: number) => `${v >= 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(1)}%`,      growth: true },
  { key: "return_5y",           label: "5Y Return",  fmt: (v: number) => `${v >= 0 ? "▲" : "▼"} ${Math.abs(v).toFixed(1)}%`,      growth: true },
];

const HIGHER_BETTER = new Set(["roe", "revenue_growth", "net_income", "dividend_yield", "market_cap", "return_1y", "return_3y", "return_5y"]);
const LOWER_BETTER  = new Set(["pe_ratio", "pb_ratio", "debt_to_equity"]);

/* ─── SectorList ─────────────────────────────────── */
function SectorList({ selected, onSelect }: { selected: string | null; onSelect: (s: string) => void }) {
  const { data, isLoading } = useSWR<SectorMeta[]>("/api/market/sectors", fetcher, { revalidateOnFocus: false });
  const [filter, setFilter] = useState("");
  const sectors = (data ?? []).filter((s) => s.sector.toLowerCase().includes(filter.toLowerCase()));

  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="border-b border-border bg-raised/40 px-4 py-3">
        <h2 className="text-sm font-semibold">NSE/BSE Sectors</h2>
        <div className="relative mt-2">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter sectors…"
            className="w-full rounded-lg bg-surface py-1.5 pl-8 pr-3 text-xs text-fg outline-none ring-1 ring-border focus:ring-saffron/50 transition-all"
          />
        </div>
      </div>
      <div className="divide-y divide-border overflow-y-auto" style={{ maxHeight: "60vh" }}>
        {isLoading
          ? Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3">
                <div className="skeleton h-7 w-7 rounded-lg" /><div className="skeleton h-4 w-28 rounded" />
              </div>
            ))
          : sectors.map((s) => (
              <button key={s.sector} onClick={() => onSelect(s.sector)}
                className={clsx(
                  "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors border-l-2",
                  selected === s.sector ? "bg-saffron/8 border-saffron" : "border-transparent hover:bg-raised/60"
                )}
              >
                <span className={clsx("flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold ring-1", sectorColor(s.sector))}>
                  {s.sector[0]}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={clsx("text-sm font-medium truncate", selected === s.sector ? "text-saffron" : "text-fg")}>{s.sector}</p>
                  <p className="text-[10px] text-muted">{s.count} stocks</p>
                </div>
                <ChevronRight className={clsx("h-3.5 w-3.5 shrink-0", selected === s.sector ? "text-saffron" : "text-muted")} />
              </button>
            ))}
      </div>
    </Card>
  );
}

/* ─── StockPicker ────────────────────────────────── */
function StockPicker({
  stocks, isLoading, sector, selected, onSelect, partial,
}: {
  stocks: PeerRow[]; isLoading: boolean; partial?: boolean;
  sector: string; selected: string | null; onSelect: (t: string) => void;
}) {
  // Show all stocks; sort by market cap when available, else alphabetically
  const sorted = [...stocks].sort((a, b) => {
    if (a.market_cap != null && b.market_cap != null) return b.market_cap - a.market_cap;
    if (a.market_cap != null) return -1;
    if (b.market_cap != null) return 1;
    return a.ticker.localeCompare(b.ticker);
  });

  return (
    <Card className="flex flex-col overflow-hidden">
      <div className="border-b border-border bg-raised/40 px-4 py-3">
        <h2 className="text-sm font-semibold">{sector}</h2>
        <p className="text-xs text-muted">Pick a stock · sorted by market cap</p>
        {partial && (
          <p className="mt-1 text-[10px] text-amber-500/80">Live data unavailable — comparison table will be limited</p>
        )}
      </div>
      <div className="divide-y divide-border overflow-y-auto" style={{ maxHeight: "60vh" }}>
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3">
                <div className="skeleton h-4 w-20 rounded" /><div className="skeleton ml-auto h-4 w-16 rounded" />
              </div>
            ))
          : sorted.map((s) => {
              const up   = (s.change_pct ?? 0) >= 0;
              const bare = s.ticker.replace(/\.(NS|BO)$/, "");
              return (
                <button key={s.ticker} onClick={() => onSelect(s.ticker)}
                  className={clsx(
                    "flex w-full items-center gap-3 px-4 py-3 text-left transition-colors border-l-2",
                    selected === s.ticker ? "bg-saffron/8 border-saffron" : "border-transparent hover:bg-raised/60"
                  )}
                >
                  <StockLogo ticker={s.ticker} website={s.website} size={7} />
                  <div className="min-w-0 flex-1">
                    <p className={clsx("text-xs font-bold", selected === s.ticker ? "text-saffron" : "text-fg")}>{bare}</p>
                    <p className="truncate text-[10px] text-muted">{s.name}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="nums text-xs font-bold">
                      {s.price != null ? `₹${s.price.toLocaleString("en-IN", { maximumFractionDigits: 0 })}` : "—"}
                    </p>
                    {s.change_pct != null && (
                      <p className={clsx("flex items-center justify-end gap-0.5 text-[10px] font-semibold", up ? "text-up" : "text-down")}>
                        {up ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                        {up ? "+" : ""}{s.change_pct.toFixed(2)}%
                      </p>
                    )}
                  </div>
                </button>
              );
            })}
      </div>
    </Card>
  );
}

/* ─── ComparisonTable ────────────────────────────── */
function ComparisonTable({ rows, targetTicker, sector }: {
  rows: PeerRow[]; targetTicker: string; sector: string;
}) {
  if (!rows.length) {
    return (
      <Card className="flex items-center justify-center p-8 text-center">
        <p className="text-sm text-muted">No comparison data available.</p>
      </Card>
    );
  }

  // Pre-compute best / worst per column
  const colStats: Record<string, { best: number; worst: number }> = {};
  for (const col of COLS) {
    const vals = rows
      .map((r) => (r as unknown as Record<string, number>)[col.key])
      .filter((v): v is number => v != null && isFinite(v));
    if (!vals.length) continue;
    const mn = Math.min(...vals);
    const mx = Math.max(...vals);
    colStats[col.key] = HIGHER_BETTER.has(col.key)
      ? { best: mx, worst: mn }
      : LOWER_BETTER.has(col.key)
      ? { best: mn, worst: mx }
      : { best: mx, worst: mn };
  }

  function cellClass(key: string, value: number | null): string {
    if (value == null || !colStats[key]) return "text-fg";
    const { best, worst } = colStats[key];
    if (best === worst) return "text-fg";
    if (value === best)  return "text-up bg-up/8 font-bold";
    if (value === worst) return "text-down bg-down/8 font-bold";
    return "text-fg";
  }

  const peerCount = rows.filter((r) => r.ticker !== targetTicker).length;

  return (
    <Card className="overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-raised/40 px-5 py-3">
        <div>
          <h2 className="text-sm font-semibold">Peer Comparison — {sector}</h2>
          <p className="text-xs text-muted">
            Selected stock vs top {peerCount} by market cap ·{" "}
            <span className="text-up font-semibold">Green</span> = best ·{" "}
            <span className="text-down font-semibold">Red</span> = worst
          </p>
        </div>
        <span className={clsx("rounded-full px-2.5 py-1 text-xs font-bold ring-1", sectorColor(sector))}>
          {rows.length} stocks
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-raised/30">
              <th className="sticky left-0 z-10 bg-surface px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-muted whitespace-nowrap">
                Company
              </th>
              {COLS.map((c) => (
                <th key={c.key} className="px-3 py-2.5 text-right text-[10px] font-semibold uppercase tracking-wider text-muted whitespace-nowrap">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => {
              const isTarget = row.ticker === targetTicker;
              const bare     = row.ticker.replace(/\.(NS|BO)$/, "");
              return (
                <tr
                  key={row.ticker}
                  className={clsx(
                    "border-b border-border/50 transition-colors last:border-0",
                    isTarget ? "bg-saffron/5" : "hover:bg-raised/40"
                  )}
                >
                  {/* Company name cell */}
                  <td className={clsx("sticky left-0 z-10 px-4 py-3 whitespace-nowrap", isTarget ? "bg-saffron/5" : "bg-surface")}>
                    <div className="flex items-center gap-2.5">
                      <StockLogo ticker={row.ticker} website={row.website} size={7} />
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <Link
                            href={`/stock/${encodeURIComponent(row.ticker)}`}
                            className={clsx(
                              "text-xs font-bold hover:underline underline-offset-2 transition-colors",
                              isTarget ? "text-saffron" : "text-fg hover:text-saffron"
                            )}
                          >
                            {bare}
                          </Link>
                          {isTarget && (
                            <span className="rounded-full bg-saffron/15 px-1.5 py-0.5 text-[9px] font-bold text-saffron">
                              YOU
                            </span>
                          )}
                          {idx === 1 && !isTarget && (
                            <span className="rounded-full bg-yellow-500/15 px-1.5 py-0.5 text-[9px] font-bold text-yellow-600">
                              #1
                            </span>
                          )}
                        </div>
                        <p className="max-w-[110px] truncate text-[10px] text-muted">{row.name}</p>
                      </div>
                    </div>
                  </td>

                  {/* Metric cells */}
                  {COLS.map((c) => {
                    const v = (row as unknown as Record<string, number | null>)[c.key];
                    const cls = cellClass(c.key, v ?? null);
                    const isGrowth = c.growth && v != null;
                    const isUp = v != null && v >= 0;
                    return (
                      <td key={c.key} className="px-3 py-3 text-right whitespace-nowrap">
                        {v != null ? (
                          isGrowth ? (
                            <span className={clsx(
                              "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px] font-bold",
                              cls.includes("text-up") || (!cls.includes("text-down") && isUp)
                                ? "bg-up/10 text-up"
                                : "bg-down/10 text-down"
                            )}>
                              {c.fmt(v)}
                            </span>
                          ) : (
                            <span className={clsx("nums text-xs", cls)}>
                              {c.fmt(v)}
                            </span>
                          )
                        ) : "—"}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

/* ─── Page ───────────────────────────────────────── */
export default function PeersPage() {
  const [sector, setSector] = useState<string | null>(null);
  const [ticker, setTicker] = useState<string | null>(null);

  // Fetch ALL sector stocks at page level — shared by picker + comparison
  const { data: sectorData, isLoading: sectorLoading } = useSWR(
    sector ? `/api/market/sector/${encodeURIComponent(sector)}` : null,
    fetcher,
    { revalidateOnFocus: false }
  );
  const sectorStocks: PeerRow[] = sectorData?.stocks ?? [];
  const isPartial: boolean = sectorData?.partial ?? false;

  // Build comparison rows whenever ticker or sector stocks change
  const comparisonRows = ticker ? buildRows(sectorStocks, ticker) : [];

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Hero */}
      <div className="flex items-center gap-4">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-saffron/10 ring-2 ring-saffron/20">
          <GitCompareArrows className="h-5 w-5 text-saffron" />
        </div>
        <div>
          <h1 className="font-display text-2xl font-bold">Peer Comparison</h1>
          <p className="text-sm text-muted">
            Pick a sector → select a stock → compare against top 10 by market cap
          </p>
        </div>
      </div>

      {/* Breadcrumb */}
      {(sector || ticker) && (
        <div className="flex items-center gap-1.5 text-xs text-muted">
          <button onClick={() => { setSector(null); setTicker(null); }} className="hover:text-fg transition-colors">
            All Sectors
          </button>
          {sector && (
            <>
              <ChevronRight className="h-3 w-3" />
              <button
                onClick={() => setTicker(null)}
                className={clsx("transition-colors", !ticker ? "text-saffron font-semibold" : "hover:text-fg")}
              >
                {sector}
              </button>
            </>
          )}
          {ticker && (
            <>
              <ChevronRight className="h-3 w-3" />
              <span className="text-saffron font-semibold">{ticker.replace(/\.(NS|BO)$/, "")}</span>
            </>
          )}
        </div>
      )}

      {/* Step indicator */}
      <div className="flex items-center gap-2">
        {[
          { n: 1, label: "Choose Sector", done: !!sector },
          { n: 2, label: "Select Stock",  done: !!ticker },
          { n: 3, label: "Compare",       done: !!ticker },
        ].map((step, i) => (
          <div key={step.n} className="flex items-center gap-2">
            <div className={clsx(
              "flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold transition-all",
              step.done ? "bg-saffron text-white" : "bg-raised text-muted ring-1 ring-border"
            )}>
              {step.done ? "✓" : step.n}
            </div>
            <span className={clsx("text-xs font-medium", step.done ? "text-fg" : "text-muted")}>
              {step.label}
            </span>
            {i < 2 && <ChevronRight className="h-3.5 w-3.5 text-border" />}
          </div>
        ))}
      </div>

      {/* 3-panel layout */}
      <div className="grid gap-4 lg:grid-cols-[220px_210px_1fr]">
        {/* Sector list */}
        <SectorList
          selected={sector}
          onSelect={(s) => { setSector(s); setTicker(null); }}
        />

        {/* Stock picker */}
        {sector ? (
          <StockPicker
            stocks={sectorStocks}
            isLoading={sectorLoading}
            sector={sector}
            selected={ticker}
            onSelect={setTicker}
            partial={isPartial}
          />
        ) : (
          <Card className="flex items-center justify-center p-8 text-center">
            <div>
              <Users className="mx-auto mb-2 h-7 w-7 text-muted" />
              <p className="text-sm font-medium text-muted">Select a sector</p>
              <p className="text-xs text-muted/60">to see stocks</p>
            </div>
          </Card>
        )}

        {/* Comparison table */}
        {ticker && comparisonRows.length ? (
          <ComparisonTable rows={comparisonRows} targetTicker={ticker} sector={sector ?? ""} />
        ) : (
          <Card className="flex items-center justify-center p-8 text-center">
            <div>
              <GitCompareArrows className="mx-auto mb-2 h-7 w-7 text-muted" />
              <p className="text-sm font-medium text-muted">
                {sector ? "Select a stock to compare" : "Select a sector, then a stock"}
              </p>
              <p className="mt-1 text-xs text-muted/60">
                Compares against top 7 sector stocks by market cap
              </p>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
