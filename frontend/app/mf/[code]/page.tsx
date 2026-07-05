"use client";

import { use, useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  ChevronLeft, ChevronRight, TrendingUp, TrendingDown, Building2,
  Layers, BarChart3, AlertTriangle, Loader2,
} from "lucide-react";
import { inrCompact } from "@/lib/api";
import clsx from "clsx";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, Legend, CartesianGrid, ReferenceLine,
} from "recharts";
import { Card } from "@/components/ui/card";

// ─── Types ────────────────────────────────────────────────────────────────────
type Period = "1y" | "3y" | "5y" | "all";

type MFDetail = {
  scheme_code: number;
  name: string;
  fund_house: string;
  scheme_type: string;
  scheme_category: string;
  nav: number | null;
  nav_date: string | null;
  return_1y: number | null;
  return_3y: number | null;
  return_5y: number | null;
  chart: { date: string; nav: number }[];
  chart_start: string | null;
};

type ETFDetail = {
  ticker: string;
  name: string;
  price: number | null;
  day_change_pct: number | null;
  aum: number | null;
  expense_ratio: number | null;
  fund_family: string;
  return_1y: number | null;
  return_3y: number | null;
  return_5y: number | null;
  chart: { date: string; close: number }[];
  chart_start: string | null;
};

type NiftyPt = { date: string; close: number };

// ─── Helpers ──────────────────────────────────────────────────────────────────
function RetBadge({ v, label }: { v: number | null; label: string }) {
  if (v == null) return (
    <div className="rounded-2xl border border-border bg-surface p-4 text-center">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1.5 text-xl font-bold text-muted">—</p>
    </div>
  );
  const up = v >= 0;
  return (
    <div className={clsx("rounded-2xl border p-4 text-center",
      up ? "border-up/20 bg-up/5" : "border-down/20 bg-down/5")}>
      <p className="text-xs text-muted">{label}</p>
      <p className={clsx("mt-1.5 text-xl font-bold", up ? "text-up" : "text-down")}>
        {up ? "+" : ""}{v.toFixed(2)}%
      </p>
      <p className="mt-0.5 text-[10px] text-muted">{up ? "gain" : "loss"}</p>
    </div>
  );
}

// ─── Normalised chart data: both series indexed to 100 at start ───────────────
function normalise(pts: { date: string; value: number }[]): { date: string; value: number }[] {
  if (!pts.length) return [];
  const base = pts[0].value;
  if (!base) return pts;
  return pts.map(p => ({ date: p.date, value: parseFloat(((p.value / base) * 100).toFixed(2)) }));
}

function filterByPeriod<T extends { date: string }>(pts: T[], period: Period): T[] {
  if (period === "all") return pts;
  const days = period === "1y" ? 365 : period === "3y" ? 1095 : 1825;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  return pts.filter(p => new Date(p.date) >= cutoff);
}

// Custom tooltip
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-border bg-surface/95 px-4 py-3 shadow-xl backdrop-blur-sm">
      <p className="mb-2 text-xs font-semibold text-muted">{label}</p>
      {payload.map((p: any) => (
        <div key={p.name} className="flex items-center gap-2 text-sm">
          <span className="h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} />
          <span className="text-muted">{p.name}:</span>
          <span className="font-bold text-fg">{p.value?.toFixed(2)}</span>
          <span className="text-muted text-xs">(base 100)</span>
        </div>
      ))}
    </div>
  );
}

// ─── Chart section ────────────────────────────────────────────────────────────
function CompareChart({
  fundPts, niftyPts, fundLabel, period, setPeriod,
}: {
  fundPts: { date: string; value: number }[];
  niftyPts: { date: string; value: number }[];
  fundLabel: string;
  period: Period;
  setPeriod: (p: Period) => void;
}) {
  const filteredFund  = filterByPeriod(fundPts, period);
  const filteredNifty = filterByPeriod(niftyPts, period);

  const normFund  = normalise(filteredFund);
  const normNifty = normalise(filteredNifty);

  // Merge by date
  const dateMap = new Map<string, { date: string; fund?: number; nifty?: number }>();
  normFund.forEach(p => dateMap.set(p.date, { date: p.date, fund: p.value }));
  normNifty.forEach(p => {
    const ex = dateMap.get(p.date) ?? { date: p.date };
    dateMap.set(p.date, { ...ex, nifty: p.value });
  });
  const merged = Array.from(dateMap.values()).sort((a, b) => a.date.localeCompare(b.date));

  // Final fund return vs nifty
  const fundEnd  = normFund.at(-1)?.value;
  const niftyEnd = normNifty.at(-1)?.value;

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between gap-3 flex-wrap">
        <h2 className="font-semibold text-sm">Performance vs Nifty 50 (Base 100)</h2>
        <div className="flex rounded-xl bg-raised p-1 ring-1 ring-border">
          {(["1y", "3y", "5y", "all"] as Period[]).map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={clsx("rounded-lg px-3 py-1 text-xs font-semibold transition-all",
                period === p ? "bg-saffron text-white shadow-sm" : "text-muted hover:text-fg")}>
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Return comparison badges */}
      {(fundEnd != null || niftyEnd != null) && (
        <div className="mb-4 grid grid-cols-2 gap-3">
          {[
            { label: `${fundLabel} (${period.toUpperCase()})`, v: fundEnd ? +(fundEnd - 100).toFixed(2) : null, color: "#F59E0B" },
            { label: `Nifty 50 (${period.toUpperCase()})`,     v: niftyEnd ? +(niftyEnd - 100).toFixed(2) : null, color: "#3B82F6" },
          ].map(({ label, v, color }) => (
            <div key={label} className="rounded-xl border border-border bg-raised/40 p-3 flex items-center gap-3">
              <span className="h-3 w-3 rounded-full shrink-0" style={{ backgroundColor: color }} />
              <div>
                <p className="text-[10px] text-muted truncate max-w-[130px]">{label}</p>
                <p className={clsx("text-sm font-bold", v == null ? "text-muted" : v >= 0 ? "text-up" : "text-down")}>
                  {v != null ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—"}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={merged} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" strokeOpacity={0.5} />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false}
              tickFormatter={d => { const dt = new Date(d); return `${dt.toLocaleString("en-IN", { month: "short" })} '${String(dt.getFullYear()).slice(2)}`; }}
              interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 10, fill: "var(--muted)" }} tickLine={false} axisLine={false}
              tickFormatter={v => `${v}`} />
            <ReferenceLine y={100} stroke="var(--border)" strokeDasharray="4 2" />
            <Tooltip content={<ChartTooltip />} />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
            <Line
              name={fundLabel.length > 25 ? fundLabel.slice(0, 22) + "…" : fundLabel}
              dataKey="fund" stroke="#F59E0B" strokeWidth={2} dot={false} connectNulls />
            <Line
              name="Nifty 50"
              dataKey="nifty" stroke="#3B82F6" strokeWidth={1.5} dot={false}
              strokeDasharray="5 3" connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-[10px] text-muted">Both series indexed to 100 at period start · For information only</p>
    </Card>
  );
}

// ─── MF Detail view ───────────────────────────────────────────────────────────
function MFDetailView({ code }: { code: number }) {
  const [data, setData]       = useState<MFDetail | null>(null);
  const [nifty, setNifty]     = useState<NiftyPt[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod]   = useState<Period>("1y");

  useEffect(() => {
    fetch(`/api/mf/${code}`)
      .then(r => r.json())
      .then(async (d: MFDetail) => {
        setData(d);
        if (d.chart_start) {
          const nr = await fetch(`/api/mf/${code}/nifty50?from_date=${d.chart_start}`).then(r => r.json());
          setNifty(nr);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [code]);

  const holdings = useFundHoldings(code);

  if (loading) return (
    <div className="flex flex-col items-center gap-3 py-20">
      <Loader2 className="h-8 w-8 animate-spin text-saffron" />
      <p className="text-sm text-muted">Loading fund data…</p>
    </div>
  );

  if (!data) return (
    <Card className="p-8 text-center">
      <AlertTriangle className="mx-auto mb-3 h-7 w-7 text-muted" />
      <p className="text-muted">Could not load this fund.</p>
    </Card>
  );

  const fundPts  = data.chart.map(p => ({ date: p.date, value: p.nav }));
  const niftyPts = nifty.map(p => ({ date: p.date, value: p.close }));

  return (
    <div className="space-y-5">
      {/* Header card */}
      <Card className="p-5">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-saffron/10 ring-1 ring-saffron/20">
            <Layers className="h-6 w-6 text-saffron" />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="font-display text-lg font-bold text-fg leading-snug">{data.name}</h1>
            <div className="mt-2 flex flex-wrap gap-2">
              {data.fund_house && (
                <span className="flex items-center gap-1 rounded-lg bg-raised px-2.5 py-1 text-xs text-muted ring-1 ring-border">
                  <Building2 className="h-3 w-3" /> {data.fund_house}
                </span>
              )}
              {data.scheme_type && (
                <span className="rounded-lg bg-raised px-2.5 py-1 text-xs text-muted ring-1 ring-border">{data.scheme_type}</span>
              )}
              {data.scheme_category && (
                <span className="rounded-lg bg-saffron/10 px-2.5 py-1 text-xs font-medium text-saffron ring-1 ring-saffron/20">{data.scheme_category}</span>
              )}
            </div>
          </div>
          {data.nav && (
            <div className="text-right shrink-0">
              <p className="text-2xl font-bold nums">₹{data.nav.toFixed(4)}</p>
              <p className="text-xs text-muted mt-0.5">NAV · {data.nav_date}</p>
            </div>
          )}
        </div>
      </Card>

      {/* Return badges */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <RetBadge v={data.return_1y} label="1Y Return" />
        <RetBadge v={data.return_3y} label="3Y Return" />
        <RetBadge v={data.return_5y} label="5Y Return" />
        <div className="rounded-2xl border border-border bg-surface p-4 text-center">
          <p className="text-xs text-muted">Fund Type</p>
          <p className="mt-1.5 text-sm font-bold text-fg">{data.scheme_type || "—"}</p>
        </div>
      </div>

      {/* Comparison chart + Fund holdings, side by side on larger screens
          (holdings are best-effort — only ~251 funds match IndianAPI's
          internal list — so the chart takes full width when absent) */}
      {holdings && holdings.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-5">
          {fundPts.length > 0 && (
            <div className="lg:col-span-3">
              <CompareChart
                fundPts={fundPts}
                niftyPts={niftyPts}
                fundLabel={data.name.split("-")[0].trim()}
                period={period}
                setPeriod={setPeriod}
              />
            </div>
          )}
          <div className={fundPts.length > 0 ? "lg:col-span-2" : "lg:col-span-5"}>
            <FundHoldingsCard holdings={holdings} />
          </div>
        </div>
      ) : (
        fundPts.length > 0 && (
          <CompareChart
            fundPts={fundPts}
            niftyPts={niftyPts}
            fundLabel={data.name.split("-")[0].trim()}
            period={period}
            setPeriod={setPeriod}
          />
        )
      )}

      {/* Similar funds — same scheme category, deduped by core fund name */}
      <SimilarFundsCard category={data.scheme_category} excludeCode={code} />
    </div>
  );
}

type Holding = { name: string; allocation: string };

function useFundHoldings(code: number): Holding[] | null {
  const [holdings, setHoldings] = useState<Holding[] | null>(null);

  useEffect(() => {
    setHoldings(null);
    fetch(`/api/mf/${code}/holdings`)
      .then(r => r.json())
      .then((d: Holding[]) => setHoldings(Array.isArray(d) ? d : []))
      .catch(() => setHoldings([]));
  }, [code]);

  return holdings;
}

function FundHoldingsCard({ holdings }: { holdings: Holding[] }) {
  return (
    <Card className="p-5">
      <h2 className="mb-3 flex items-center gap-2 font-semibold"><Layers className="h-4 w-4 text-saffron" /> Fund Holdings</h2>
      <div className="divide-y divide-border">
        {holdings.slice(0, 15).map((h, i) => (
          <div key={i} className="flex items-center justify-between gap-3 py-2 text-sm">
            <span className="truncate text-fg/90">{h.name}</span>
            <span className="nums shrink-0 font-semibold text-fg">{h.allocation}%</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

type SimilarFund = { scheme_code: number; name: string };

// IndianAPI's scheme_category comes as "Equity Scheme - Flexi Cap Fund" —
// extract just "Flexi Cap" since that's what actually matches AMFI scheme
// names for the category filter (the full label never matches anything).
function extractCategoryKeyword(category: string): string {
  const match = category.match(/Scheme\s*-\s*(.+?)\s*Fund\s*$/i);
  return match ? match[1].trim() : category;
}

function SimilarFundsCard({ category, excludeCode }: { category: string; excludeCode: number }) {
  const [funds, setFunds] = useState<SimilarFund[] | null>(null);
  const keyword = category ? extractCategoryKeyword(category) : "";

  useEffect(() => {
    if (!keyword) { setFunds([]); return; }
    setFunds(null);
    fetch(`/api/mf?category=${encodeURIComponent(keyword)}&limit=40`)
      .then(r => r.json())
      .then((d: { funds?: SimilarFund[] }) => {
        const seen = new Set<string>();
        const result: SimilarFund[] = [];
        for (const f of d.funds ?? []) {
          if (f.scheme_code === excludeCode) continue;
          // Dedup Direct/Regular/Growth/Dividend variants of the same core fund
          const key = f.name.toLowerCase().split("-")[0].trim();
          if (seen.has(key)) continue;
          seen.add(key);
          result.push(f);
          if (result.length >= 6) break;
        }
        setFunds(result);
      })
      .catch(() => setFunds([]));
  }, [keyword, excludeCode]);

  if (!funds || funds.length === 0) return null;

  return (
    <Card className="p-5">
      <h2 className="mb-3 flex items-center gap-2 font-semibold"><Layers className="h-4 w-4 text-saffron" /> Similar Funds</h2>
      <p className="mb-3 text-xs text-muted">Other {keyword} funds</p>
      <div className="divide-y divide-border">
        {funds.map((f) => (
          <Link
            key={f.scheme_code}
            href={`/mf/${f.scheme_code}`}
            className="flex items-center justify-between gap-3 py-2.5 text-sm text-fg/90 hover:text-saffron transition-colors"
          >
            <span className="truncate">{f.name.split("-")[0].trim()}</span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" />
          </Link>
        ))}
      </div>
    </Card>
  );
}

// ─── ETF Detail view ──────────────────────────────────────────────────────────
function ETFDetailView({ ticker }: { ticker: string }) {
  const [data, setData]       = useState<ETFDetail | null>(null);
  const [nifty, setNifty]     = useState<NiftyPt[]>([]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod]   = useState<Period>("1y");

  useEffect(() => {
    fetch(`/api/etf/${ticker}`)
      .then(r => r.json())
      .then(async (d: ETFDetail) => {
        setData(d);
        if (d.chart_start) {
          const nr = await fetch(`/api/etf/${ticker}/nifty50?from_date=${d.chart_start}`).then(r => r.json());
          setNifty(nr);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [ticker]);

  if (loading) return (
    <div className="flex flex-col items-center gap-3 py-20">
      <Loader2 className="h-8 w-8 animate-spin text-saffron" />
      <p className="text-sm text-muted">Loading ETF data…</p>
    </div>
  );

  if (!data) return (
    <Card className="p-8 text-center">
      <AlertTriangle className="mx-auto mb-3 h-7 w-7 text-muted" />
      <p className="text-muted">Could not load this ETF.</p>
    </Card>
  );

  const up = (data.day_change_pct ?? 0) >= 0;
  const fundPts  = data.chart.map(p => ({ date: p.date, value: p.close }));
  const niftyPts = nifty.map(p => ({ date: p.date, value: p.close }));

  return (
    <div className="space-y-5">
      {/* Header card */}
      <Card className="p-5">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-accent/10 ring-1 ring-accent/20">
            <BarChart3 className="h-6 w-6 text-accent" />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="font-display text-lg font-bold text-fg leading-snug">{data.name}</h1>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className="rounded-lg bg-raised px-2.5 py-1 text-xs font-semibold text-fg ring-1 ring-border">
                {ticker.replace(".NS", "")}
              </span>
              {data.fund_family && (
                <span className="flex items-center gap-1 rounded-lg bg-raised px-2.5 py-1 text-xs text-muted ring-1 ring-border">
                  <Building2 className="h-3 w-3" /> {data.fund_family}
                </span>
              )}
              {data.expense_ratio != null && (
                <span className="rounded-lg bg-raised px-2.5 py-1 text-xs text-muted ring-1 ring-border">
                  Expense: {(data.expense_ratio * 100).toFixed(2)}%
                </span>
              )}
              {data.aum != null && (
                <span className="rounded-lg bg-raised px-2.5 py-1 text-xs text-muted ring-1 ring-border">
                  AUM: {inrCompact(data.aum)}
                </span>
              )}
            </div>
          </div>
          {data.price && (
            <div className="text-right shrink-0">
              <p className="text-2xl font-bold nums">₹{data.price.toFixed(2)}</p>
              <p className={clsx("text-sm font-bold", up ? "text-up" : "text-down")}>
                {up ? "+" : ""}{data.day_change_pct?.toFixed(2)}%
              </p>
            </div>
          )}
        </div>
      </Card>

      {/* Return badges */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <RetBadge v={data.return_1y} label="1Y Return" />
        <RetBadge v={data.return_3y} label="3Y Return" />
        <RetBadge v={data.return_5y} label="5Y Return" />
        <div className="rounded-2xl border border-border bg-surface p-4 text-center">
          <p className="text-xs text-muted">AUM</p>
          <p className="mt-1.5 text-sm font-bold text-fg">{data.aum ? inrCompact(data.aum) : "—"}</p>
        </div>
      </div>

      {/* Comparison chart */}
      {fundPts.length > 0 && (
        <CompareChart
          fundPts={fundPts}
          niftyPts={niftyPts}
          fundLabel={ticker.replace(".NS", "")}
          period={period}
          setPeriod={setPeriod}
        />
      )}
    </div>
  );
}

// ─── Page router ──────────────────────────────────────────────────────────────
export default function MFDetailPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = use(params);
  const isETF = code.startsWith("etf_");
  const id    = isETF ? decodeURIComponent(code.replace("etf_", "")) : code;

  return (
    <div className="space-y-5 animate-fade-up">
      <div className="flex items-center gap-3">
        <Link href="/mf" className="flex items-center gap-1.5 text-sm text-muted hover:text-fg transition-colors">
          <ChevronLeft className="h-4 w-4" /> MF & ETF
        </Link>
        <span className="text-border">/</span>
        <span className="text-sm font-medium text-muted">{isETF ? "ETF" : "Mutual Fund"}</span>
      </div>

      {isETF
        ? <ETFDetailView ticker={id} />
        : <MFDetailView  code={parseInt(id)} />
      }
    </div>
  );
}
