"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { FileBarChart } from "lucide-react";
import { Card } from "@/components/ui/card";
import clsx from "clsx";

type Unit = "cr" | "pct" | "num";
type Row = { key: string; label: string; unit: Unit; values: (number | null)[] };
type Table = { periods: string[]; rows: Row[] };
type GrowthBox = Record<string, Record<string, string>>;
type Financials = {
  quarterly: Table;
  profit_loss: Table;
  balance_sheet: Table;
  cash_flow: Table;
  ratios: Table;
  growth: GrowthBox;
};

const TABS = [
  { key: "quarterly", label: "Quarterly Results" },
  { key: "profit_loss", label: "Profit & Loss" },
  { key: "balance_sheet", label: "Balance Sheet" },
  { key: "cash_flow", label: "Cash Flow" },
  { key: "ratios", label: "Ratios" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

const UNIT_NOTES: Record<TabKey, string> = {
  quarterly: "₹ Cr, unless stated",
  profit_loss: "₹ Cr, unless stated",
  balance_sheet: "₹ Cr",
  cash_flow: "₹ Cr, unless stated",
  ratios: "Days, unless stated",
};

// Highlighting only applies to rows where a negative value is unambiguously bad news
// (unlike e.g. "Other Income" or YoY-growth-style rows where sign alone isn't meaningful here).
const _NEGATIVE_IS_BAD = new Set([
  "Net Profit", "Operating Profit", "Profit before tax",
  "Free Cash Flow", "Cash from Operating Activity", "Net Cash Flow",
]);
const _EMPHASIZE = new Set(["Sales", "Net Profit", "Total Assets", "Cash from Operating Activity"]);

function _fmtIndian(n: number, d = 0): string {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: d }).format(n);
}

function fmtCell(v: number | null, unit: Unit): string {
  if (v == null) return "—";
  if (unit === "pct") return `${v.toFixed(1)}%`;
  if (unit === "cr") return _fmtIndian(v, 0);
  return _fmtIndian(v, 2);
}

function FinTable({ table, unitNote }: { table: Table; unitNote: string }) {
  if (!table?.rows?.length || !table?.periods?.length) {
    return <p className="p-5 text-sm text-muted">No data available.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-raised/60">
            <th className="sticky left-0 z-10 min-w-[170px] bg-raised/80 px-3 py-2.5 text-left text-micro font-medium uppercase tracking-wide text-muted backdrop-blur-sm">
              {unitNote}
            </th>
            {table.periods.map((p) => (
              <th
                key={p}
                className="whitespace-nowrap px-3 py-2.5 text-right text-micro font-medium uppercase tracking-wide text-muted"
              >
                {p}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {table.rows.map((r) => (
            <tr key={r.key} className="transition-colors hover:bg-raised/40">
              <td
                className={clsx(
                  "sticky left-0 z-10 whitespace-nowrap bg-surface px-3 py-2 text-left text-sm backdrop-blur-sm",
                  _EMPHASIZE.has(r.key) && "font-semibold"
                )}
              >
                {r.label}
              </td>
              {r.values.map((v, i) => (
                <td
                  key={i}
                  className={clsx(
                    "nums whitespace-nowrap px-3 py-2 text-right text-sm",
                    v != null && v < 0 && _NEGATIVE_IS_BAD.has(r.key)
                      ? "text-down font-medium"
                      : "text-fg/80",
                    _EMPHASIZE.has(r.key) && "font-semibold"
                  )}
                >
                  {fmtCell(v, r.unit)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const GROWTH_BOXES = [
  { key: "Compounded Sales Growth", label: "Compounded Sales Growth" },
  { key: "Compounded Profit Growth", label: "Compounded Profit Growth" },
  { key: "Stock Price CAGR", label: "Stock Price CAGR" },
  { key: "Return on Equity", label: "Return on Equity" },
] as const;

function GrowthBoxes({ growth }: { growth: GrowthBox }) {
  const present = GROWTH_BOXES.filter((b) => growth?.[b.key] && Object.keys(growth[b.key]).length);
  if (!present.length) return null;
  return (
    <div className="grid gap-3 border-t border-border p-4 sm:grid-cols-2 lg:grid-cols-4">
      {present.map((b) => (
        <div key={b.key} className="rounded-lg border border-border bg-raised/30 p-3">
          <p className="mb-2 text-[11px] font-medium text-muted">{b.label}</p>
          <div className="space-y-1">
            {Object.entries(growth[b.key]).map(([period, val]) => (
              <div key={period} className="flex items-center justify-between text-xs">
                <span className="text-muted">{period.replace(/:$/, "")}</span>
                <span className="nums font-semibold">{val}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="p-5">
      <div className="skeleton h-64 w-full rounded-lg" />
    </div>
  );
}

export function FinancialsTables({ ticker }: { ticker: string }) {
  const { data, error, isLoading } = useSWR<Financials>(
    `/api/stocks/${ticker}/financials`,
    fetcher,
    { revalidateOnFocus: false }
  );
  const [tab, setTab] = useState<TabKey>("quarterly");

  const table = data?.[tab];

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 pt-4 pb-0">
        <div className="flex items-center gap-2 pb-3">
          <FileBarChart className="h-4 w-4 text-saffron" />
          <h2 className="font-medium">Financials</h2>
        </div>
        <div className="flex gap-0 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={clsx(
                "whitespace-nowrap border-b-2 px-3 pb-3 pt-1 text-sm font-medium transition-colors",
                tab === t.key
                  ? "border-saffron text-saffron"
                  : "border-transparent text-muted hover:text-fg"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <Skeleton />}

      {error && (
        <div className="rounded-xl border border-border bg-raised/40 mx-5 my-5 px-5 py-6 text-center">
          <FileBarChart className="mx-auto mb-3 h-8 w-8 text-muted/40" />
          <p className="text-sm font-medium text-muted">Financial statements unavailable</p>
          <p className="mt-1 text-xs text-muted/60">IndianAPI may not carry financials for this stock.</p>
        </div>
      )}

      {table && (
        <>
          <FinTable table={table} unitNote={UNIT_NOTES[tab]} />
          {tab === "profit_loss" && <GrowthBoxes growth={data!.growth} />}
          <p className="border-t border-border px-4 py-2 text-[10px] text-muted">
            Source: company filings via IndianAPI · figures in ₹ Crore unless noted
          </p>
        </>
      )}
    </Card>
  );
}
