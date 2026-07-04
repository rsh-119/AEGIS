"use client";

import { use, useState, useCallback } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, inr, inrCompact, num } from "@/lib/api";
import {
  TrendingUp, TrendingDown, ChevronLeft, BarChart3, Building2,
  ArrowUpDown, ArrowUp, ArrowDown,
} from "lucide-react";
import clsx from "clsx";
import { ChartCard } from "@/components/ui/animated-card-chart";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";

type Stock = {
  ticker: string;
  name: string;
  price: number;
  change_pct: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  roe: number | null;
  revenue_growth: number | null;
  net_income: number | null;
  volume: number | null;
  return_1y: number | null;
  return_3y: number | null;
  return_5y: number | null;
};

type SectorData = {
  sector: string;
  stocks: Stock[];
  stats: {
    median_pe: number | null;
    median_pb: number | null;
    median_return_1y: number | null;
    count: number;
  };
};

type SortKey = keyof Stock | null;
type SortDir = "asc" | "desc";

// ─── Column definitions ───────────────────────────────────────────────────────
type ColDef = {
  key: keyof Stock;
  label: string;
  align: "left" | "right";
  hint?: string;
};

const COLS: ColDef[] = [
  { key: "name",            label: "Company",    align: "left"  },
  { key: "price",           label: "Price",      align: "right", hint: "Current market price" },
  { key: "change_pct",      label: "1D Chg",     align: "right", hint: "Today's price change %" },
  { key: "market_cap",      label: "Mkt Cap",    align: "right", hint: "Market capitalisation" },
  { key: "pe_ratio",        label: "P/E",        align: "right", hint: "Price / Earnings (trailing)" },
  { key: "pb_ratio",        label: "P/B",        align: "right", hint: "Price / Book value" },
  { key: "roe",             label: "ROE",        align: "right", hint: "Return on Equity" },
  { key: "revenue_growth",  label: "Sales %",    align: "right", hint: "Revenue growth YoY" },
  { key: "net_income",      label: "Net Profit", align: "right", hint: "Net income (absolute)" },
  { key: "return_1y",       label: "1Y Return",  align: "right", hint: "1-year price return" },
  { key: "return_3y",       label: "3Y Return",  align: "right", hint: "3-year price return" },
  { key: "return_5y",       label: "5Y Return",  align: "right", hint: "5-year price return" },
];

// ─── Sort helpers ─────────────────────────────────────────────────────────────
function sortStocks(stocks: Stock[], key: SortKey, dir: SortDir): Stock[] {
  if (!key) return stocks;
  return [...stocks].sort((a, b) => {
    const av = a[key] as string | number | null;
    const bv = b[key] as string | number | null;
    if (av == null && bv == null) return 0;
    if (av == null) return 1;   // nulls always last
    if (bv == null) return -1;
    if (typeof av === "string" && typeof bv === "string") {
      return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    }
    return dir === "asc"
      ? (av as number) - (bv as number)
      : (bv as number) - (av as number);
  });
}

// ─── Sort icon ────────────────────────────────────────────────────────────────
function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 text-muted/40 shrink-0" />;
  return dir === "asc"
    ? <ArrowUp className="h-3 w-3 text-saffron shrink-0" />
    : <ArrowDown className="h-3 w-3 text-saffron shrink-0" />;
}

// ─── Cell renderers ───────────────────────────────────────────────────────────
function ReturnCell({ value }: { value: number | null }) {
  if (value == null) return <td className="nums px-4 py-3 text-right text-muted">—</td>;
  const up = value >= 0;
  return (
    <td className={clsx("nums px-4 py-3 text-right text-xs font-bold", up ? "text-up" : "text-down")}>
      {up ? "+" : ""}{value.toFixed(1)}%
    </td>
  );
}

function GrowthCell({ value, multiply100 = false }: { value: number | null; multiply100?: boolean }) {
  if (value == null) return <td className="px-4 py-3 text-right text-muted">—</td>;
  const pct = multiply100 ? value * 100 : value;
  const up = pct >= 0;
  return (
    <td className="px-4 py-3 text-right">
      <span className={clsx(
        "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px] font-bold",
        up ? "bg-up/10 text-up" : "bg-down/10 text-down"
      )}>
        {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
      </span>
    </td>
  );
}

function StatBox({ label, value, up }: { label: string; value: string; up?: boolean }) {
  return (
    <Card className="p-4 cursor-default select-none text-center transition-all duration-200 hover:-translate-y-0.5 hover:border-[rgba(21,128,61,0.22)] hover:shadow-[var(--shadow-md),var(--shadow-glow)]">
      <Label className="block">{label}</Label>
      <p className={clsx("nums mt-1.5 text-xl font-bold", up ? "text-up" : "text-fg")}>{value}</p>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function SectorPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = use(params);
  const sector = decodeURIComponent(name);

  const { data, isLoading, error } = useSWR<SectorData>(
    `/api/market/sector/${encodeURIComponent(sector)}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  const [sortKey, setSortKey] = useState<SortKey>("market_cap");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = useCallback((key: keyof Stock) => {
    setSortKey((prev) => {
      if (prev === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return key;
      }
      setSortDir("desc");
      return key;
    });
  }, []);

  const sortedStocks = sortStocks(data?.stocks ?? [], sortKey, sortDir);

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Back nav */}
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-1.5 text-sm text-muted hover:text-fg transition-colors">
          <ChevronLeft className="h-4 w-4" /> Home
        </Link>
        <span className="text-border">/</span>
        <span className="text-sm text-muted">Sectors</span>
        <span className="text-border">/</span>
        <span className="text-sm font-medium">{sector}</span>
      </div>

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-saffron/10 ring-1 ring-saffron/20">
          <Building2 className="h-5 w-5 text-saffron" />
        </div>
        <div>
          <h1 className="font-display text-2xl font-bold">{sector}</h1>
          <p className="text-sm text-muted">
            {data ? `${data.stocks.length} companies tracked` : "Loading…"}
          </p>
        </div>
      </div>

      {/* Sector stats */}
      {data?.stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatBox label="Companies" value={String(data.stats.count)} />
          <StatBox label="Median P/E" value={data.stats.median_pe != null ? num(data.stats.median_pe) : "—"} />
          <StatBox label="Median P/B" value={data.stats.median_pb != null ? num(data.stats.median_pb) : "—"} />
          <StatBox
            label="Median 1Y Return"
            value={data.stats.median_return_1y != null
              ? `${data.stats.median_return_1y >= 0 ? "+" : ""}${data.stats.median_return_1y.toFixed(1)}%`
              : "—"}
            up={data.stats.median_return_1y != null && data.stats.median_return_1y >= 0}
          />
        </div>
      )}

      {/* Skeletons */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="skeleton h-14 rounded-xl" style={{ opacity: 1 - i * 0.08 }} />
          ))}
        </div>
      )}

      {error && (
        <Card className="p-8 text-center">
          <p className="text-muted">Could not load sector data. Try again shortly.</p>
        </Card>
      )}

      {sortedStocks.length > 0 && (
        <ChartCard color="#F5A524">
          <div className="border-b border-border bg-raised/40 px-5 py-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-saffron" />
              <span className="text-sm font-semibold">{sector} Stocks</span>
            </div>
            <span className="text-xs text-muted">
              {sortKey
                ? `Sorted by ${COLS.find(c => c.key === sortKey)?.label ?? sortKey} ${sortDir === "asc" ? "↑" : "↓"}`
                : "Click column headers to sort"}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-raised/20">
                  {COLS.map(({ key, label, align, hint }) => (
                    <th
                      key={key}
                      title={hint}
                      onClick={() => handleSort(key)}
                      className={clsx(
                        "px-4 py-3 text-[11px] font-medium uppercase tracking-wider whitespace-nowrap",
                        "cursor-pointer select-none transition-colors hover:bg-raised hover:text-fg",
                        sortKey === key ? "text-saffron" : "text-muted",
                        align === "left" ? "text-left" : "text-right"
                      )}
                    >
                      <span className={clsx(
                        "inline-flex items-center gap-1",
                        align === "right" && "justify-end"
                      )}>
                        {align === "right" && <SortIcon active={sortKey === key} dir={sortDir} />}
                        {label}
                        {align === "left" && <SortIcon active={sortKey === key} dir={sortDir} />}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>

              <tbody className="divide-y divide-border">
                {sortedStocks.map((s, i) => {
                  const up   = (s.change_pct ?? 0) >= 0;
                  const bare = s.ticker.replace(/\.(NS|BO)$/, "");
                  return (
                    <tr
                      key={s.ticker}
                      className="hover:bg-raised/40 transition-colors group"
                    >
                      {/* Company */}
                      <td className="px-4 py-3">
                        <Link href={`/stock/${encodeURIComponent(s.ticker)}`} className="group/link">
                          <p className="font-semibold text-fg group-hover/link:text-saffron transition-colors">{bare}</p>
                          <p className="text-[10px] text-muted truncate max-w-[180px]">{s.name}</p>
                        </Link>
                      </td>

                      {/* Price */}
                      <td className="nums px-4 py-3 text-right font-semibold">{inr(s.price)}</td>

                      {/* 1D Chg */}
                      <td className={clsx("nums px-4 py-3 text-right text-xs font-bold", up ? "text-up" : "text-down")}>
                        <span className="flex items-center justify-end gap-0.5">
                          {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                          {up ? "+" : ""}{(s.change_pct ?? 0).toFixed(2)}%
                        </span>
                      </td>

                      {/* Mkt Cap */}
                      <td className={clsx(
                        "nums px-4 py-3 text-right",
                        sortKey === "market_cap" ? "font-semibold text-fg" : "text-muted"
                      )}>
                        {inrCompact(s.market_cap)}
                      </td>

                      {/* P/E */}
                      <td className="nums px-4 py-3 text-right">
                        <span className={clsx(
                          s.pe_ratio != null && data?.stats.median_pe != null && s.pe_ratio < data.stats.median_pe
                            ? "text-up font-medium" : ""
                        )}>
                          {num(s.pe_ratio)}
                        </span>
                      </td>

                      {/* P/B */}
                      <td className="nums px-4 py-3 text-right">{num(s.pb_ratio)}</td>

                      {/* ROE */}
                      <td className={clsx(
                        "nums px-4 py-3 text-right",
                        s.roe != null && s.roe > 0.15 ? "text-up font-medium" : ""
                      )}>
                        {s.roe != null ? `${(s.roe * 100).toFixed(1)}%` : "—"}
                      </td>

                      {/* Sales % */}
                      <GrowthCell value={s.revenue_growth} multiply100 />

                      {/* Net Profit */}
                      <td className={clsx(
                        "nums px-4 py-3 text-right text-xs font-semibold",
                        s.net_income != null && s.net_income < 0 ? "text-down" : ""
                      )}>
                        {inrCompact(s.net_income)}
                      </td>

                      {/* Returns */}
                      <ReturnCell value={s.return_1y} />
                      <ReturnCell value={s.return_3y} />
                      <ReturnCell value={s.return_5y} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="border-t border-border bg-raised/20 px-5 py-2.5">
            <p className="text-[10px] text-muted">
              P/E &lt; sector median highlighted green · ROE &gt; 15% highlighted green ·
              Returns are price-only · Click any column header to sort ↑↓ · Data via Yahoo Finance
            </p>
          </div>
        </ChartCard>
      )}

      {data?.stocks?.length === 0 && !isLoading && (
        <Card className="p-8 text-center">
          <Building2 className="mx-auto mb-3 h-8 w-8 text-muted/30" />
          <p className="text-muted">No tracked stocks found for <strong>{sector}</strong>.</p>
        </Card>
      )}
    </div>
  );
}
