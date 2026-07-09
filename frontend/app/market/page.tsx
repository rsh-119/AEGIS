"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, inr, inrCompact, pct, signCls, num } from "@/lib/api";
import { PriceChart } from "@/components/PriceChart";
import { TrendingUp, TrendingDown, ArrowUpRight, ArrowDownRight, Zap } from "lucide-react";
import clsx from "clsx";
import { ChartCard } from "@/components/ui/animated-card-chart";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StockLogo } from "@/components/StockLogo";
import { SECTORS } from "@/lib/sectors";

/* ─── Types ──────────────────────────────────────── */
type Candle = { date: string; close: number; ma20: number | null; ma50: number | null };
type SectorStock = {
  ticker: string; name: string; price?: number; change_pct?: number;
  market_cap?: number; pe_ratio?: number; roe?: number;
  revenue_growth?: number; net_margin?: number; website?: string | null;
};

/* ─── Period selector ────────────────────────────── */
const PERIODS = [
  { label: "1M", value: "1mo" },
  { label: "3M", value: "3mo" },
  { label: "6M", value: "6mo" },
  { label: "1Y", value: "1y"  },
  { label: "2Y", value: "2y"  },
  { label: "5Y", value: "5y"  },
];


/* ─── Index chart card ───────────────────────────── */
function IndexCard({ slug, name, period, onPeriodChange }: {
  slug: string; name: string; period: string; onPeriodChange: (p: string) => void;
}) {
  const { data, isLoading } = useSWR(
    `/api/market/index/${slug}?period=${period}`, fetcher,
    { revalidateOnFocus: false }
  );

  const q     = data?.quote ?? {};
  const hist  = data?.history ?? {};
  const price = q.current_price;
  const prev  = q.previous_close;
  const chg   = price && prev ? ((price - prev) / prev) * 100 : null;
  const up    = (chg ?? 0) >= 0;
  const candles: Candle[] = hist.candles ?? [];

  return (
    <ChartCard color={up ? "#1FC77D" : "#F0454B"}>
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">{name}</p>
          {price ? (
            <p className="nums mt-0.5 text-2xl font-bold text-fg">
              {price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            </p>
          ) : (
            <div className="skeleton mt-1 h-7 w-32 rounded" />
          )}
          {chg != null && (
            <p className={clsx("nums mt-0.5 flex items-center gap-1 text-sm font-semibold", up ? "text-up" : "text-down")}>
              {up ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {up ? "+" : ""}{chg.toFixed(2)}% today
              <span className="font-normal text-muted text-xs ml-1">
                (prev {prev?.toLocaleString("en-IN", { maximumFractionDigits: 0 })})
              </span>
            </p>
          )}
        </div>

        {/* Period tabs */}
        <div className="flex items-center gap-1 rounded-lg bg-raised p-1">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => onPeriodChange(p.value)}
              className={clsx(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                period === p.value ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stats strip */}
      {price && (
        <div className="flex divide-x divide-border border-b border-border">
          {[
            { label: "Day High", value: q.day_high?.toLocaleString("en-IN", { maximumFractionDigits: 0 }) ?? "—" },
            { label: "Day Low",  value: q.day_low?.toLocaleString("en-IN", { maximumFractionDigits: 0 }) ?? "—" },
            { label: "52W High", value: q.week52_high?.toLocaleString("en-IN", { maximumFractionDigits: 0 }) ?? "—" },
            { label: "52W Low",  value: q.week52_low?.toLocaleString("en-IN", { maximumFractionDigits: 0 }) ?? "—" },
            { label: `${PERIODS.find(p => p.value === period)?.label} Chg`, value: hist.pct_change != null ? `${hist.pct_change >= 0 ? "+" : ""}${hist.pct_change.toFixed(2)}%` : "—" },
          ].map((s) => (
            <div key={s.label} className="flex-1 px-3 py-2 text-center">
              <p className="text-[10px] text-muted">{s.label}</p>
              <p className="nums mt-0.5 text-xs font-bold text-fg">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Chart */}
      <div className="px-2 pb-3 pt-3">
        {isLoading || candles.length === 0 ? (
          <div className="skeleton h-52 w-full rounded-lg" />
        ) : (
          <PriceChart candles={candles} up={up} />
        )}
      </div>
    </ChartCard>
  );
}

/* ─── Sector card grid ───────────────────────────── */
function SectorGrid() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {SECTORS.map((s) => {
        const Icon = s.icon;
        return (
          <Link
            key={s.slug}
            href={`/sector/${encodeURIComponent(s.slug)}`}
            className="card flex flex-col items-start gap-3 border border-border p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
          >
            <span className={clsx(
              "flex h-9 w-9 items-center justify-center rounded-xl ring-1",
              s.color, s.accent
            )}>
              <Icon className="h-4 w-4" />
            </span>
            <div className="min-w-0 w-full">
              <p className="text-sm font-semibold leading-tight text-fg">
                {s.name}
              </p>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

/* ─── Stock list row ─────────────────────────────── */
function StockRow({ stock, rank }: { stock: SectorStock; rank: number }) {
  const up   = (stock.change_pct ?? 0) >= 0;
  const bare = stock.ticker.replace(/\.(NS|BO)$/, "");
  return (
    <Link
      href={`/stock/${encodeURIComponent(stock.ticker)}`}
      className="group flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-raised/50"
    >
      <span className="w-5 shrink-0 text-center text-[11px] font-bold text-muted">{rank}</span>
      <StockLogo ticker={stock.ticker} website={stock.website} size={8} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-fg group-hover:text-saffron transition-colors truncate">
          {stock.name || bare}
        </p>
        <p className="text-[10px] text-muted font-mono">{bare} · {stock.market_cap ? inrCompact(stock.market_cap) : "—"}</p>
      </div>
      <div className="shrink-0 text-right">
        <p className="nums text-sm font-bold text-fg">{stock.price ? inr(stock.price) : "—"}</p>
        {stock.change_pct != null && (
          <p className={clsx("nums mt-0.5 flex items-center justify-end gap-0.5 text-xs font-semibold", up ? "text-up" : "text-down")}>
            {up ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {up ? "+" : ""}{stock.change_pct.toFixed(2)}%
          </p>
        )}
      </div>
    </Link>
  );
}

function RowSkeleton() {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-5 py-3.5" style={{ opacity: 1 - i * 0.1 }}>
          <div className="skeleton h-3 w-4 rounded shrink-0" />
          <div className="skeleton h-8 w-8 rounded-lg shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className="skeleton h-3.5 w-28 rounded" />
            <div className="skeleton h-2.5 w-16 rounded" />
          </div>
          <div className="space-y-1.5 text-right shrink-0">
            <div className="skeleton h-3.5 w-16 rounded" />
            <div className="skeleton h-2.5 w-10 rounded ml-auto" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Page ──────────────────────────────────────── */
/* ─── 52-Week Highs & Lows section ───────────────── */
function FiftyTwoWeekSection() {
  const { data, isLoading } = useSWR<{ highs: SectorStock[]; lows: SectorStock[] }>(
    "/api/market/52week", fetcher, { revalidateOnFocus: false }
  );
  const highs = data?.highs ?? [];
  const lows = data?.lows ?? [];

  return (
    <section id="52-week" className="space-y-4">
      <h2 className="font-semibold text-fg">52-Week Highs &amp; Lows</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-raised/40 px-4 py-3">
            <TrendingUp className="h-4 w-4 text-up" />
            <h3 className="text-sm font-semibold">New Highs</h3>
            <Badge className="ml-auto bg-up/10 text-up text-[10px]">{highs.length}</Badge>
          </div>
          {isLoading ? (
            <RowSkeleton />
          ) : highs.length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No new highs today</p>
          ) : (
            <div className="divide-y divide-border overflow-y-auto" style={{ maxHeight: "420px" }}>
              {highs.slice(0, 10).map((s, i) => <StockRow key={s.ticker} stock={s} rank={i + 1} />)}
            </div>
          )}
        </Card>
        <Card className="overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border bg-raised/40 px-4 py-3">
            <TrendingDown className="h-4 w-4 text-down" />
            <h3 className="text-sm font-semibold">New Lows</h3>
            <Badge className="ml-auto bg-down/10 text-down text-[10px]">{lows.length}</Badge>
          </div>
          {isLoading ? (
            <RowSkeleton />
          ) : lows.length === 0 ? (
            <p className="p-8 text-center text-sm text-muted">No new lows today</p>
          ) : (
            <div className="divide-y divide-border overflow-y-auto" style={{ maxHeight: "420px" }}>
              {lows.slice(0, 10).map((s, i) => <StockRow key={s.ticker} stock={s} rank={i + 1} />)}
            </div>
          )}
        </Card>
      </div>
    </section>
  );
}

/* ─── Price Shockers section ─────────────────────── */
function PriceShockersSection() {
  const { data, isLoading } = useSWR<SectorStock[]>("/api/market/price-shockers", fetcher, { revalidateOnFocus: false });
  const stocks = data ?? [];

  return (
    <section id="price-shockers" className="space-y-4">
      <h2 className="font-semibold text-fg">Price Shockers</h2>
      <Card className="overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border bg-raised/40 px-4 py-3">
          <Zap className="h-4 w-4 text-saffron" />
          <h3 className="text-sm font-semibold">Unusual Price Movements</h3>
          <Badge className="ml-auto bg-raised text-muted text-[10px]">{stocks.length}</Badge>
        </div>
        {isLoading ? (
          <RowSkeleton />
        ) : stocks.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted">No price shockers right now</p>
        ) : (
          <div className="divide-y divide-border overflow-y-auto" style={{ maxHeight: "560px" }}>
            {stocks.slice(0, 15).map((s, i) => <StockRow key={s.ticker} stock={s} rank={i + 1} />)}
          </div>
        )}
      </Card>
    </section>
  );
}

export default function MarketPage() {
  const [niftyPeriod, setNiftyPeriod]   = useState("1y");
  const [sensexPeriod, setSensexPeriod] = useState("1y");

  return (
    <div className="space-y-10 animate-fade-up">

      {/* ── Header ── */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-saffron">Live Data</p>
        <h1 className="font-display mt-1 text-3xl font-bold">Indian Markets</h1>
        <p className="mt-1 text-sm text-muted">NSE · BSE · Real-time indices and sector performance</p>
      </div>

      {/* ── Index charts ── */}
      <section className="space-y-4">
        <h2 className="font-semibold text-fg">Market Indices</h2>
        <div className="grid gap-5 lg:grid-cols-2">
          <IndexCard
            slug="nifty50"
            name="Nifty 50"
            period={niftyPeriod}
            onPeriodChange={setNiftyPeriod}
          />
          <IndexCard
            slug="sensex"
            name="Sensex"
            period={sensexPeriod}
            onPeriodChange={setSensexPeriod}
          />
        </div>
      </section>

      {/* ── Sector grid ── */}
      <section className="space-y-4">
        <div>
          <h2 className="font-semibold text-fg">Explore by Sector</h2>
          <p className="text-xs text-muted">Click any sector to open its index chart, rankings &amp; financials</p>
        </div>
        <SectorGrid />
      </section>

      {/* ── 52-Week Highs/Lows ── */}
      <FiftyTwoWeekSection />

      {/* ── Price Shockers ── */}
      <PriceShockersSection />

    </div>
  );
}
