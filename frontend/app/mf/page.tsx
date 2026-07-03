"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { inrCompact, inr } from "@/lib/api";
import { MFHighlights } from "@/components/MFHighlights";
import {
  TrendingUp, TrendingDown, Search,
  ArrowUpDown, ArrowUp, ArrowDown, BarChart3, Layers,
  ChevronLeft, ChevronRight, Loader2,
} from "lucide-react";
import clsx from "clsx";

// ─── Types ────────────────────────────────────────────────────────────────────
type MFItem = {
  scheme_code: number;
  name: string;
  nav?: number;
  nav_date?: string;
  return_1y?: number | null;
  return_3y?: number | null;
  return_5y?: number | null;
  fund_house?: string;
  scheme_type?: string;
};

type ETFItem = {
  ticker: string;
  name: string;
  asset_class: string;
  sub_category: string;
  price: number;
  day_change_pct: number | null;
  aum: number | null;
  expense_ratio: number | null;
  return_1y: number | null;
  return_3y: number | null;
  return_5y: number | null;
};

type Period  = "1y" | "3y" | "5y";
type SortDir = "asc" | "desc";

// ─── Shared helpers ───────────────────────────────────────────────────────────
function RetPill({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-muted text-xs">—</span>;
  const up = v >= 0;
  return (
    <span className={clsx(
      "inline-flex items-center gap-0.5 rounded-lg px-2 py-0.5 text-xs font-bold tabular-nums",
      up ? "bg-up/10 text-up" : "bg-down/10 text-down",
    )}>
      {up ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
      {up ? "+" : ""}{v.toFixed(1)}%
    </span>
  );
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  if (!active) return <ArrowUpDown className="h-3 w-3 text-muted/40 shrink-0" />;
  return dir === "asc"
    ? <ArrowUp   className="h-3 w-3 text-saffron shrink-0" />
    : <ArrowDown className="h-3 w-3 text-saffron shrink-0" />;
}

// Horizontally-scrollable filter pills row
function PillRow({
  items, active, onSelect,
}: {
  items: { key: string; label: string }[];
  active: string;
  onSelect: (k: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto pb-0.5 scrollbar-none">
      {items.map(c => (
        <button
          key={c.key}
          onClick={() => onSelect(c.key)}
          className={clsx(
            "shrink-0 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all duration-200",
            active === c.key
              ? "bg-saffron text-white shadow-md shadow-saffron/20"
              : "bg-raised text-muted ring-1 ring-border hover:ring-saffron/30 hover:text-fg",
          )}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}

const MF_CATS  = [
  { key: "",       label: "All"    },
  { key: "equity", label: "Equity" },
  { key: "debt",   label: "Debt"   },
  { key: "hybrid", label: "Hybrid" },
  { key: "index",  label: "Index"  },
  { key: "elss",   label: "ELSS"   },
  { key: "gold",   label: "Gold"   },
];

const ETF_CATS = [
  { key: "",       label: "All"    },
  { key: "Equity", label: "Equity" },
  { key: "Gold",   label: "Gold"   },
  { key: "Silver", label: "Silver" },
  { key: "Debt",   label: "Debt"   },
];

// ─── ETF Table ────────────────────────────────────────────────────────────────
function ETFTable({ period }: { period: Period }) {
  const [etfs, setEtfs]       = useState<ETFItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [cat, setCat]         = useState("");
  const [sortKey, setSortKey] = useState<keyof ETFItem>("return_1y");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  useEffect(() => {
    fetch("/api/etf")
      .then(r => r.json())
      .then(d => { setEtfs(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const handleSort = (k: keyof ETFItem) => {
    if (sortKey === k) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("desc"); }
  };

  const retKey = period === "1y" ? "return_1y" : period === "3y" ? "return_3y" : "return_5y";

  const filtered = cat ? etfs.filter(e => e.asset_class === cat) : etfs;
  const sorted   = [...filtered].sort((a, b) => {
    const av = a[sortKey] as number | string | null;
    const bv = b[sortKey] as number | string | null;
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "string")
      return sortDir === "asc" ? av.localeCompare(bv as string) : (bv as string).localeCompare(av);
    return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
  });

  const TH = ({ k, label, hint }: { k: keyof ETFItem; label: string; hint?: string }) => (
    <th
      title={hint}
      onClick={() => handleSort(k)}
      className={clsx(
        "px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap cursor-pointer select-none transition-colors hover:bg-raised",
        sortKey === k ? "text-saffron" : "text-muted",
      )}
    >
      <span className="inline-flex items-center justify-end gap-1">
        <SortIcon active={sortKey === k} dir={sortDir} /> {label}
      </span>
    </th>
  );

  return (
    <div className="space-y-4">
      <PillRow items={ETF_CATS} active={cat} onSelect={c => setCat(c)} />

      <div className={clsx("card overflow-hidden transition-opacity duration-200", loading ? "opacity-60" : "opacity-100")}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-raised/30">
                <th className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide text-muted min-w-[220px]">
                  ETF
                </th>
                <TH k="price"          label="Price"     hint="Current market price" />
                <TH k="day_change_pct" label="1D %"      hint="Today's change" />
                <TH k={retKey as keyof ETFItem} label={`${period.toUpperCase()} Ret`} hint={`${period.toUpperCase()} price return`} />
                <TH k="aum"            label="AUM"       hint="Assets under management" />
                <TH k="expense_ratio"  label="Exp %"     hint="Annual expense ratio" />
                <th className="px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wide text-muted whitespace-nowrap">
                  Type
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={7} className="px-4 py-3.5">
                        <div className="skeleton h-4 w-full rounded" />
                      </td>
                    </tr>
                  ))
                : sorted.map(e => {
                    const retVal = e[retKey as keyof ETFItem] as number | null;
                    const up = (e.day_change_pct ?? 0) >= 0;
                    return (
                      <tr key={e.ticker} className="hover:bg-raised/40 transition-colors">
                        <td className="px-4 py-3">
                          <Link href={`/mf/etf_${encodeURIComponent(e.ticker)}`}>
                            <p className="font-semibold text-fg hover:text-saffron transition-colors text-sm">
                              {e.ticker.replace(".NS", "")}
                            </p>
                            <p className="text-[11px] text-muted truncate max-w-[200px] leading-tight mt-0.5">
                              {e.name}
                            </p>
                          </Link>
                        </td>
                        <td className="nums px-4 py-3 text-right font-semibold whitespace-nowrap">
                          {inr(e.price)}
                        </td>
                        <td className={clsx(
                          "nums px-4 py-3 text-right text-xs font-bold whitespace-nowrap",
                          up ? "text-up" : "text-down",
                        )}>
                          {e.day_change_pct != null ? `${up ? "+" : ""}${e.day_change_pct.toFixed(2)}%` : "—"}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <RetPill v={retVal} />
                        </td>
                        <td className="nums px-4 py-3 text-right text-muted text-xs whitespace-nowrap">
                          {e.aum ? inrCompact(e.aum) : "—"}
                        </td>
                        <td className="nums px-4 py-3 text-right text-muted text-xs whitespace-nowrap">
                          {e.expense_ratio ? `${(e.expense_ratio * 100).toFixed(2)}%` : "—"}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="rounded-lg bg-raised px-2 py-0.5 text-[10px] font-medium text-muted ring-1 ring-border whitespace-nowrap">
                            {e.sub_category}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
        </div>
      </div>
      {!loading && sorted.length === 0 && (
        <p className="py-12 text-center text-sm text-muted">No ETFs found for this category.</p>
      )}
    </div>
  );
}

// ─── MF Table ─────────────────────────────────────────────────────────────────
function MFTable({ period }: { period: Period }) {
  const [search, setSearch]       = useState("");
  const [dSearch, setDSearch]     = useState("");
  const [cat, setCat]             = useState("");
  const [page, setPage]           = useState(1);
  const [funds, setFunds]         = useState<MFItem[]>([]);
  const [total, setTotal]         = useState(0);
  const [pages, setPages]         = useState(1);
  const [listLoading, setListLoading] = useState(true);
  const [retLoading, setRetLoading]   = useState(false);
  const [returns, setReturns]         = useState<Record<number, any>>({});
  const [sortKey, setSortKey]         = useState<string>("return");
  const [sortDir, setSortDir]         = useState<SortDir>("desc");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const LIMIT = 40;

  // Debounce search input
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setDSearch(search); setPage(1); }, 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  useEffect(() => { setPage(1); }, [cat]);

  // Fetch fund list
  useEffect(() => {
    setListLoading(true);
    const params = new URLSearchParams({ page: String(page), limit: String(LIMIT) });
    if (dSearch) params.set("search", dSearch);
    if (cat)     params.set("category", cat);
    fetch(`/api/mf?${params}`)
      .then(r => r.json())
      .then(d => {
        setFunds(d.funds ?? []);
        setTotal(d.total ?? 0);
        setPages(d.pages ?? 1);
        setListLoading(false);
      })
      .catch(() => setListLoading(false));
  }, [page, dSearch, cat]);

  // Fetch returns for visible page
  useEffect(() => {
    if (!funds.length) return;
    const missing = funds.map(f => f.scheme_code).filter(c => !returns[c]);
    if (!missing.length) return;
    setRetLoading(true);
    fetch("/api/mf/returns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes: missing }),
    })
      .then(r => r.json())
      .then(d => { setReturns(prev => ({ ...prev, ...d })); setRetLoading(false); })
      .catch(() => setRetLoading(false));
  }, [funds]);

  const handleSort = (k: string) => {
    if (sortKey === k) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("desc"); }
  };

  const retKey = period === "1y" ? "return_1y" : period === "3y" ? "return_3y" : "return_5y";

  const merged: MFItem[] = funds.map(f => ({ ...f, ...returns[f.scheme_code] }));
  const sorted = [...merged].sort((a, b) => {
    if (sortKey === "name")
      return sortDir === "asc" ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name);
    if (sortKey === "nav") {
      const av = a.nav ?? null, bv = b.nav ?? null;
      if (av == null && bv == null) return 0;
      if (av == null) return 1; if (bv == null) return -1;
      return sortDir === "asc" ? av - bv : bv - av;
    }
    if (sortKey === "return") {
      const av = (a as any)[retKey] ?? null, bv = (b as any)[retKey] ?? null;
      if (av == null && bv == null) return 0;
      if (av == null) return 1; if (bv == null) return -1;
      return sortDir === "asc" ? av - bv : bv - av;
    }
    return 0;
  });

  const TH = ({ k, label, hint }: { k: string; label: string; hint?: string }) => (
    <th
      title={hint}
      onClick={() => handleSort(k)}
      className={clsx(
        "px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap cursor-pointer select-none transition-colors hover:bg-raised",
        sortKey === k ? "text-saffron" : "text-muted",
      )}
    >
      <span className="inline-flex items-center justify-end gap-1">
        <SortIcon active={sortKey === k} dir={sortDir} /> {label}
      </span>
    </th>
  );

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted pointer-events-none" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search fund name, AMC…"
          className="w-full rounded-xl border border-border bg-raised/60 py-2 pl-9 pr-4 text-sm placeholder:text-muted focus:border-saffron/50 focus:outline-none focus:ring-1 focus:ring-saffron/30 transition-all"
        />
      </div>

      {/* Category filter */}
      <PillRow items={MF_CATS} active={cat} onSelect={c => setCat(c)} />

      {/* Stats */}
      <div className="flex items-center justify-between text-xs text-muted">
        <span>
          <span className="font-semibold text-fg">{total.toLocaleString("en-IN")}</span>
          {" "}funds{cat ? ` · ${MF_CATS.find(c => c.key === cat)?.label}` : ""}
        </span>
        <span className="flex items-center gap-1.5">
          {retLoading && <Loader2 className="h-3 w-3 animate-spin text-saffron" />}
          {retLoading ? "Loading returns…" : "AMFI NAV data"}
        </span>
      </div>

      <div className={clsx(
        "card overflow-hidden transition-opacity duration-200",
        listLoading ? "opacity-60" : "opacity-100",
      )}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-raised/30">
                <th
                  onClick={() => handleSort("name")}
                  className={clsx(
                    "px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wide whitespace-nowrap cursor-pointer select-none min-w-[280px] transition-colors hover:bg-raised",
                    sortKey === "name" ? "text-saffron" : "text-muted",
                  )}
                >
                  <span className="inline-flex items-center gap-1">
                    Fund Name <SortIcon active={sortKey === "name"} dir={sortDir} />
                  </span>
                </th>
                <TH k="nav"    label="NAV"                         hint="Net Asset Value (latest)" />
                <TH k="return" label={`${period.toUpperCase()} Ret`} hint={`${period.toUpperCase()} return from AMFI NAV`} />
                <th className="px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wide text-muted whitespace-nowrap">
                  Fund House
                </th>
                <th className="px-4 py-3 text-right text-[11px] font-semibold uppercase tracking-wide text-muted whitespace-nowrap">
                  Type
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {listLoading
                ? Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={5} className="px-4 py-3.5">
                        <div className="skeleton h-4 w-full rounded" />
                      </td>
                    </tr>
                  ))
                : sorted.map(f => {
                    const retVal = (f as any)[retKey];
                    return (
                      <tr key={f.scheme_code} className="hover:bg-raised/40 transition-colors">
                        <td className="px-4 py-3.5">
                          <Link href={`/mf/${f.scheme_code}`}>
                            <p className="font-medium text-fg hover:text-saffron transition-colors leading-snug line-clamp-2 max-w-sm text-sm">
                              {f.name}
                            </p>
                          </Link>
                        </td>
                        <td className="nums px-4 py-3.5 text-right text-sm font-semibold whitespace-nowrap">
                          {f.nav != null ? `₹${f.nav.toFixed(4)}` : (
                            retLoading
                              ? <span className="inline-block h-3.5 w-16 rounded skeleton" />
                              : <span className="text-muted">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-right">
                          {retLoading && retVal == null
                            ? <span className="inline-block h-5 w-14 rounded-lg skeleton" />
                            : <RetPill v={retVal} />
                          }
                        </td>
                        <td className="px-4 py-3.5 text-right">
                          <span className="text-xs text-muted truncate block max-w-[150px] ml-auto leading-tight">
                            {f.fund_house || (retLoading ? <span className="inline-block h-3 w-20 rounded skeleton" /> : "—")}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 text-right">
                          {f.scheme_type ? (
                            <span className="rounded-lg bg-raised px-2 py-0.5 text-[10px] font-medium text-muted ring-1 ring-border whitespace-nowrap">
                              {f.scheme_type}
                            </span>
                          ) : (
                            retLoading
                              ? <span className="inline-block h-5 w-16 rounded-lg skeleton" />
                              : <span className="text-muted text-xs">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <span className="text-xs text-muted">
            Page {page} of {pages}
            <span className="mx-1.5 text-border">·</span>
            {total.toLocaleString("en-IN")} funds
          </span>
          <div className="flex items-center gap-1.5">
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
              className="flex items-center gap-1 rounded-xl border border-border px-3 py-1.5 text-xs text-muted hover:border-saffron/40 hover:text-fg disabled:opacity-40 transition-all"
            >
              <ChevronLeft className="h-3.5 w-3.5" /> Prev
            </button>
            {Array.from({ length: Math.min(5, pages) }, (_, i) => {
              const p = Math.max(1, Math.min(pages - 4, page - 2)) + i;
              return (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={clsx(
                    "rounded-xl px-3 py-1.5 text-xs transition-all",
                    p === page
                      ? "bg-saffron text-white font-bold shadow-sm"
                      : "border border-border text-muted hover:border-saffron/40 hover:text-fg",
                  )}
                >
                  {p}
                </button>
              );
            })}
            <button
              disabled={page >= pages}
              onClick={() => setPage(p => p + 1)}
              className="flex items-center gap-1 rounded-xl border border-border px-3 py-1.5 text-xs text-muted hover:border-saffron/40 hover:text-fg disabled:opacity-40 transition-all"
            >
              Next <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function MFPage() {
  const [tab, setTab]       = useState<"mf" | "etf">("mf");
  const [period, setPeriod] = useState<Period>("1y");

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold">Mutual Funds & ETFs</h1>
        <p className="mt-1 text-sm text-muted">
          {tab === "mf"
            ? "8,000+ Indian mutual funds · NAV data from AMFI"
            : "NSE-listed ETFs · Live prices via Yahoo Finance"}
        </p>
      </div>

      {/* Tab + period row */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Tab switcher */}
        <div className="flex rounded-xl bg-raised p-1 ring-1 ring-border">
          {([
            { key: "mf",  label: "Mutual Funds", icon: Layers    },
            { key: "etf", label: "ETFs",          icon: BarChart3 },
          ] as const).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={clsx(
                "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200",
                tab === key
                  ? "bg-surface text-fg shadow-sm ring-1 ring-border"
                  : "text-muted hover:text-fg",
              )}
            >
              <Icon className="h-4 w-4" /> {label}
            </button>
          ))}
        </div>

        {/* Period selector */}
        <div className="flex rounded-xl bg-raised p-1 ring-1 ring-border">
          {(["1y", "3y", "5y"] as Period[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={clsx(
                "rounded-lg px-4 py-1.5 text-sm font-semibold transition-all duration-200",
                period === p
                  ? "bg-saffron text-white shadow-sm shadow-saffron/20"
                  : "text-muted hover:text-fg",
              )}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Highlights strip — switches with tab */}
      <MFHighlights type={tab} period={period} />

      {/*
        Both components stay mounted — hiding with CSS instead of
        conditional render keeps fetched data alive when switching tabs.
      */}
      <div className={clsx("transition-opacity duration-200", tab === "mf"  ? "block opacity-100" : "hidden opacity-0")}>
        <MFTable  period={period} />
      </div>
      <div className={clsx("transition-opacity duration-200", tab === "etf" ? "block opacity-100" : "hidden opacity-0")}>
        <ETFTable period={period} />
      </div>
    </div>
  );
}
