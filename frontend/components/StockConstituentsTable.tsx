"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { inr, inrCompact, num } from "@/lib/api";
import { TrendingUp, TrendingDown, BarChart3 } from "lucide-react";
import clsx from "clsx";
import { ChartCard } from "@/components/ui/animated-card-chart";
import { SortIcon } from "@/components/ui/sort-icon";

/** Shared sortable constituent-stock table — originally built for the sector
 * page, extracted so the index page (Nifty 50, Nifty Pharma, etc.) can show
 * the same rich per-stock breakdown instead of duplicating ~250 lines of
 * column/sort/cell-renderer logic. */
export type ConstituentStock = {
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

type SortKey = keyof ConstituentStock | null;
type SortDir = "asc" | "desc";

type ColDef = {
  key: keyof ConstituentStock;
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

function sortStocks(stocks: ConstituentStock[], key: SortKey, dir: SortDir): ConstituentStock[] {
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
        "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-micro font-bold",
        up ? "bg-up/10 text-up" : "bg-down/10 text-down"
      )}>
        {up ? "▲" : "▼"} {Math.abs(pct).toFixed(1)}%
      </span>
    </td>
  );
}

export function StockConstituentsTable({
  stocks, medianPe, title, footnote,
}: {
  stocks: ConstituentStock[];
  medianPe?: number | null;
  title: string;
  footnote?: string;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("market_cap");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = useCallback((key: keyof ConstituentStock) => {
    setSortKey((prev) => {
      if (prev === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return key;
      }
      setSortDir("desc");
      return key;
    });
  }, []);

  const sortedStocks = sortStocks(stocks, sortKey, sortDir);
  if (sortedStocks.length === 0) return null;

  return (
    <ChartCard color="#F5A524">
      <div className="border-b border-border bg-raised/40 px-5 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-saffron" />
          <span className="text-sm font-semibold">{title}</span>
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
                    "px-4 py-3 text-micro font-medium uppercase tracking-wider whitespace-nowrap",
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
            {sortedStocks.map((s) => {
              const up   = (s.change_pct ?? 0) >= 0;
              const bare = s.ticker.replace(/\.(NS|BO)$/, "");
              return (
                <tr key={s.ticker} className="hover:bg-raised/40 transition-colors group">
                  <td className="px-4 py-3">
                    <Link href={`/stock/${encodeURIComponent(s.ticker)}`} className="group/link">
                      <p className="font-semibold text-fg group-hover/link:text-saffron transition-colors">{bare}</p>
                      <p className="text-[10px] text-muted truncate max-w-[180px]">{s.name}</p>
                    </Link>
                  </td>
                  <td className="nums px-4 py-3 text-right font-semibold">{inr(s.price)}</td>
                  <td className={clsx("nums px-4 py-3 text-right text-xs font-bold", up ? "text-up" : "text-down")}>
                    <span className="flex items-center justify-end gap-0.5">
                      {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                      {up ? "+" : ""}{(s.change_pct ?? 0).toFixed(2)}%
                    </span>
                  </td>
                  <td className={clsx(
                    "nums px-4 py-3 text-right",
                    sortKey === "market_cap" ? "font-semibold text-fg" : "text-muted"
                  )}>
                    {inrCompact(s.market_cap)}
                  </td>
                  <td className="nums px-4 py-3 text-right">
                    <span className={clsx(
                      s.pe_ratio != null && medianPe != null && s.pe_ratio < medianPe
                        ? "text-up font-medium" : ""
                    )}>
                      {num(s.pe_ratio)}
                    </span>
                  </td>
                  <td className="nums px-4 py-3 text-right">{num(s.pb_ratio)}</td>
                  <td className={clsx(
                    "nums px-4 py-3 text-right",
                    s.roe != null && s.roe > 0.15 ? "text-up font-medium" : ""
                  )}>
                    {s.roe != null ? `${(s.roe * 100).toFixed(1)}%` : "—"}
                  </td>
                  <GrowthCell value={s.revenue_growth} multiply100 />
                  <td className={clsx(
                    "nums px-4 py-3 text-right text-xs font-semibold",
                    s.net_income != null && s.net_income < 0 ? "text-down" : ""
                  )}>
                    {inrCompact(s.net_income)}
                  </td>
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
          {footnote ?? "P/E < median highlighted green · ROE > 15% highlighted green · Returns are price-only · Click any column header to sort ↑↓"}
        </p>
      </div>
    </ChartCard>
  );
}
