"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import { fetcher, num, pct, signCls, del } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { LoginPrompt } from "@/components/LoginPrompt";
import { useAuth } from "@/lib/auth";
import { Trash2, ArrowUpDown, ArrowUp, ArrowDown, Download, SlidersHorizontal } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useConfirm } from "@/components/ui/confirm-dialog";

type ColKey =
  | "pe_ratio" | "market_cap" | "dividend_yield"
  | "net_profit_cr" | "net_profit_yoy_pct"
  | "revenue_cr" | "revenue_yoy_pct" | "roe";

type SortKey = "name" | "current_price" | ColKey;
type SortDir = "asc" | "desc";

const COLUMNS: { key: ColKey; label: string }[] = [
  { key: "pe_ratio",           label: "P/E" },
  { key: "market_cap",         label: "Mar Cap Rs.Cr." },
  { key: "dividend_yield",     label: "Div Yld %" },
  { key: "net_profit_cr",      label: "NP Qtr Rs.Cr." },
  { key: "net_profit_yoy_pct", label: "Qtr Profit Var %" },
  { key: "revenue_cr",         label: "Sales Qtr Rs.Cr." },
  { key: "revenue_yoy_pct",    label: "Qtr Sales Var %" },
  { key: "roe",                label: "ROE %" },
];

const STORAGE_KEY = "aegis_watchlist_columns";

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 text-muted/40 shrink-0" />;
  return dir === "asc"
    ? <ArrowUp className="h-3 w-3 text-saffron shrink-0" />
    : <ArrowDown className="h-3 w-3 text-saffron shrink-0" />;
}

// market_cap arrives in raw INR (matches the rest of the app) — this table
// shows Rs. Crore like Screener, so divide down for display only.
const crFmt = (raw: number | null | undefined) =>
  raw == null || isNaN(raw) ? "—" : num(raw / 1e7, 2);

export default function WatchlistPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { toast } = useToast();
  const confirm = useConfirm();
  const { data } = useSWR(user ? "/api/watchlist" : null, fetcher, { revalidateOnFocus: false });
  const items = data?.items || [];

  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [industry, setIndustry] = useState<string>("all");
  const [visibleCols, setVisibleCols] = useState<Set<ColKey>>(new Set(COLUMNS.map((c) => c.key)));
  const [colsOpen, setColsOpen] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) setVisibleCols(new Set(JSON.parse(saved)));
    } catch {
      /* ignore malformed storage */
    }
  }, []);

  function toggleCol(key: ColKey) {
    setVisibleCols((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "name" ? "asc" : "desc"); }
  }

  const industries = useMemo(
    () => Array.from(new Set(items.map((it: any) => it.industry).filter(Boolean))).sort() as string[],
    [items]
  );

  const roeOf = (it: any) => it.roce ?? it.roe;

  const filteredItems = industry === "all" ? items : items.filter((it: any) => it.industry === industry);

  const sortedItems = [...filteredItems].sort((a: any, b: any) => {
    if (sortKey === "name") {
      const an = a.company_name || a.ticker, bn = b.company_name || b.ticker;
      return sortDir === "asc" ? an.localeCompare(bn) : bn.localeCompare(an);
    }
    const av = sortKey === "roe" ? roeOf(a) : a[sortKey];
    const bv = sortKey === "roe" ? roeOf(b) : b[sortKey];
    const aval = av ?? -Infinity, bval = bv ?? -Infinity;
    return sortDir === "asc" ? aval - bval : bval - aval;
  });

  async function remove(id: number) {
    const ok = await confirm({
      title: "Remove from watchlist?",
      confirmLabel: "Remove",
      destructive: true,
    });
    if (!ok) return;
    try {
      await del(`/api/watchlist/${id}`);
    } catch (e) {
      // 404 = already gone (stale list, double-click, etc.) — the desired
      // end state is already true, so just refresh instead of erroring out.
      if (!(e instanceof Error) || !e.message.includes("404")) {
        toast({ variant: "error", title: "Couldn't remove item", description: (e as Error).message });
        return;
      }
    }
    mutate("/api/watchlist");
    toast({ variant: "success", title: "Removed from watchlist" });
  }

  function exportCsv() {
    const cols = COLUMNS.filter((c) => visibleCols.has(c.key));
    const header = ["S.No", "Name", "CMP Rs.", ...cols.map((c) => c.label)];
    const rows = sortedItems.map((it: any, i: number) => [
      i + 1,
      it.company_name || it.ticker,
      it.current_price ?? "",
      ...cols.map((c) => {
        if (c.key === "roe") { const v = roeOf(it); return v != null ? (v * 100).toFixed(2) : ""; }
        if (c.key === "dividend_yield") return it.dividend_yield != null ? (it.dividend_yield * 100).toFixed(2) : "";
        if (c.key === "market_cap") return it.market_cap != null ? (it.market_cap / 1e7).toFixed(2) : "";
        return it[c.key] ?? "";
      }),
    ]);
    const csv = [header, ...rows].map((r) => r.map((v) => `"${v}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "watchlist.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  if (authLoading) return null;
  if (!user) {
    return (
      <div className="space-y-6 animate-fade-up">
        <h1 className="font-display text-3xl font-semibold">Watchlist</h1>
        <LoginPrompt what="your watchlist" />
      </div>
    );
  }

  const visibleColList = COLUMNS.filter((c) => visibleCols.has(c.key));
  const colCount = 3 + visibleColList.length + 1; // S.No + Name + CMP + toggleable + remove

  return (
    <div className="space-y-6 animate-fade-up">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="font-display text-3xl font-semibold">Watchlist</h1>
        <div className="w-full max-w-xs">
          <SearchBox placeholder="Add a stock…" />
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <select
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
          className="rounded-full border border-border bg-raised/40 px-4 py-2 text-sm text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-saffron/40"
        >
          <option value="all">All Industries</option>
          {industries.map((ind) => <option key={ind} value={ind}>{ind}</option>)}
        </select>

        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={exportCsv}>
            <Download className="h-4 w-4" /> Export
          </Button>
          <div className="relative">
            <Button variant="ghost" onClick={() => setColsOpen((o) => !o)}>
              <SlidersHorizontal className="h-4 w-4" /> Edit Columns
            </Button>
            {colsOpen && (
              <div
                className="absolute right-0 z-10 mt-2 w-56 rounded-2xl border border-border bg-surface p-2 shadow-lg"
                onMouseLeave={() => setColsOpen(false)}
              >
                {COLUMNS.map((c) => (
                  <label key={c.key} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-raised/60 cursor-pointer">
                    <input type="checkbox" checked={visibleCols.has(c.key)} onChange={() => toggleCol(c.key)} />
                    {c.label}
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-border text-muted">
            <tr className="[&>th]:px-4 [&>th]:py-3 [&>th]:text-left [&>th]:text-[10px] [&>th]:font-normal [&>th]:uppercase [&>th]:tracking-[0.1px] [&>th]:whitespace-nowrap">
              <th>S.No</th>
              <th>
                <button onClick={() => handleSort("name")} className={clsx("flex items-center gap-1 hover:text-fg", sortKey === "name" && "text-saffron")}>
                  Name <SortIcon active={sortKey === "name"} dir={sortDir} />
                </button>
              </th>
              <th className="!text-right">
                <button onClick={() => handleSort("current_price")} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === "current_price" && "text-saffron")}>
                  CMP Rs. <SortIcon active={sortKey === "current_price"} dir={sortDir} />
                </button>
              </th>
              {visibleColList.map((c) => (
                <th key={c.key} className="!text-right">
                  <button onClick={() => handleSort(c.key)} className={clsx("ml-auto flex items-center gap-1 hover:text-fg", sortKey === c.key && "text-saffron")}>
                    {c.label} <SortIcon active={sortKey === c.key} dir={sortDir} />
                  </button>
                </th>
              ))}
              <th></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sortedItems.length === 0 ? (
              <tr><td colSpan={colCount} className="px-5 py-10 text-center text-muted">
                Watchlist is empty. Use search above to add NSE/BSE stocks.
              </td></tr>
            ) : sortedItems.map((it: any, i: number) => {
              const roe = roeOf(it);
              return (
                <tr key={it.id} className="[&>td]:px-4 [&>td]:py-3 hover:bg-raised/40">
                  <td className="text-muted">{i + 1}</td>
                  <td>
                    <a href={`/stock/${it.ticker}`} className="font-medium hover:text-saffron">{it.company_name || it.ticker}</a>
                    <div className="text-xs text-muted">{it.ticker.replace(".NS", "").replace(".BO", "")}</div>
                  </td>
                  <td className="nums text-right">{num(it.current_price, 2)}</td>
                  {visibleCols.has("pe_ratio") && <td className="nums text-right">{num(it.pe_ratio, 2)}</td>}
                  {visibleCols.has("market_cap") && <td className="nums text-right">{crFmt(it.market_cap)}</td>}
                  {visibleCols.has("dividend_yield") && (
                    <td className="nums text-right">{it.dividend_yield != null ? num(it.dividend_yield * 100, 2) : "—"}</td>
                  )}
                  {visibleCols.has("net_profit_cr") && <td className="nums text-right">{num(it.net_profit_cr, 2)}</td>}
                  {visibleCols.has("net_profit_yoy_pct") && (
                    <td className={`nums text-right ${signCls(it.net_profit_yoy_pct)}`}>{pct(it.net_profit_yoy_pct)}</td>
                  )}
                  {visibleCols.has("revenue_cr") && <td className="nums text-right">{num(it.revenue_cr, 2)}</td>}
                  {visibleCols.has("revenue_yoy_pct") && (
                    <td className={`nums text-right ${signCls(it.revenue_yoy_pct)}`}>{pct(it.revenue_yoy_pct)}</td>
                  )}
                  {visibleCols.has("roe") && <td className="nums text-right">{roe != null ? num(roe * 100, 2) : "—"}</td>}
                  <td className="text-right">
                    <button onClick={() => remove(it.id)} className="text-muted hover:text-down">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
