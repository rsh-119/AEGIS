"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, inr, inrCompact, pct, signCls, num } from "@/lib/api";
import { PriceChart } from "@/components/PriceChart";
import {
  TrendingUp, TrendingDown, ChevronRight, ChevronLeft,
  ArrowUpRight, ArrowDownRight, Building2, BarChart3,
  Cpu, Landmark, Heart, Zap, Factory, Layers,
  Radio, Sun, Home as HomeIcon, ShoppingCart,
} from "lucide-react";
import clsx from "clsx";
import { ChartCard } from "@/components/ui/animated-card-chart";
import { Card } from "@/components/ui/card";

/* ─── Types ──────────────────────────────────────── */
type Candle = { date: string; close: number; ma20: number | null; ma50: number | null };
type SectorStock = {
  ticker: string; name: string; price?: number; change_pct?: number;
  market_cap?: number; pe_ratio?: number; roe?: number;
  revenue_growth?: number; net_margin?: number;
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

/* ─── Sector config ──────────────────────────────── */
type SectorCfg = {
  name: string;
  slug: string;           // API sector name
  indexSlug?: string;     // /api/market/index/{indexSlug}
  icon: React.ComponentType<{ className?: string }>;
  color: string;          // tailwind bg + text combo
  accent: string;         // border / ring color
};

const SECTORS: SectorCfg[] = [
  { name: "Technology",           slug: "Technology",           indexSlug: "niftyit",      icon: Cpu,         color: "bg-blue-500/10 text-blue-500",      accent: "border-blue-500/30 ring-blue-500/20" },
  { name: "Financial Services",   slug: "Financial Services",   indexSlug: "banknifty",    icon: Landmark,    color: "bg-emerald-500/10 text-emerald-500", accent: "border-emerald-500/30 ring-emerald-500/20" },
  { name: "Healthcare",           slug: "Healthcare",           indexSlug: "niftypharma",  icon: Heart,       color: "bg-rose-500/10 text-rose-500",       accent: "border-rose-500/30 ring-rose-500/20" },
  { name: "Energy",               slug: "Energy",               indexSlug: "niftyenergy",  icon: Zap,         color: "bg-orange-500/10 text-orange-500",   accent: "border-orange-500/30 ring-orange-500/20" },
  { name: "Consumer Defensive",   slug: "Consumer Defensive",   indexSlug: "niftyfmcg",   icon: ShoppingCart,color: "bg-purple-500/10 text-purple-500",   accent: "border-purple-500/30 ring-purple-500/20" },
  { name: "Consumer Cyclical",    slug: "Consumer Cyclical",    indexSlug: "niftyauto",    icon: ArrowUpRight,color: "bg-pink-500/10 text-pink-500",        accent: "border-pink-500/30 ring-pink-500/20" },
  { name: "Industrials",          slug: "Industrials",          indexSlug: "niftyinfra",   icon: Factory,     color: "bg-yellow-500/10 text-yellow-600",   accent: "border-yellow-500/30 ring-yellow-500/20" },
  { name: "Basic Materials",      slug: "Basic Materials",      indexSlug: "niftymetal",   icon: Layers,      color: "bg-stone-500/10 text-stone-500",     accent: "border-stone-500/30 ring-stone-500/20" },
  { name: "Real Estate",          slug: "Real Estate",          indexSlug: "niftyrealty",  icon: HomeIcon,    color: "bg-teal-500/10 text-teal-500",       accent: "border-teal-500/30 ring-teal-500/20" },
  { name: "Communication",        slug: "Communication Services",indexSlug: "niftymedia",  icon: Radio,       color: "bg-indigo-500/10 text-indigo-500",   accent: "border-indigo-500/30 ring-indigo-500/20" },
];

/* ─── Avatar ─────────────────────────────────────── */
const AVATAR_COLORS = [
  "bg-blue-500","bg-emerald-500","bg-violet-500","bg-rose-500",
  "bg-amber-500","bg-cyan-500","bg-pink-500","bg-orange-500","bg-teal-500","bg-indigo-500",
];
function avatarColor(t: string) {
  let h = 0;
  for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) & 0xff;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

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
function SectorGrid({ selected, onSelect }: {
  selected: SectorCfg | null;
  onSelect: (s: SectorCfg) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {SECTORS.map((s) => {
        const Icon = s.icon;
        const isActive = selected?.slug === s.slug;
        return (
          <button
            key={s.slug}
            onClick={() => onSelect(s)}
            className={clsx(
              "card flex flex-col items-start gap-3 p-4 text-left transition-all duration-200",
              "hover:-translate-y-0.5 hover:shadow-md",
              isActive ? `border-2 ${s.accent} shadow-md` : "border border-border"
            )}
          >
            <span className={clsx(
              "flex h-9 w-9 items-center justify-center rounded-xl ring-1",
              s.color, s.accent
            )}>
              <Icon className="h-4 w-4" />
            </span>
            <div className="min-w-0 w-full">
              <p className={clsx("text-sm font-semibold leading-tight", isActive ? s.color.split(" ")[1] : "text-fg")}>
                {s.name}
              </p>
              {isActive && (
                <p className="mt-0.5 text-[10px] text-muted">Viewing detail ↓</p>
              )}
            </div>
          </button>
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
      <div className={clsx(
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold text-white",
        avatarColor(bare)
      )}>
        {bare.slice(0, 2)}
      </div>
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

/* ─── Sector detail panel ────────────────────────── */
type SectorTab = "performers" | "losers" | "allstocks";

function SectorDetail({ cfg }: { cfg: SectorCfg }) {
  const [tab, setTab]       = useState<SectorTab>("performers");
  const [period, setPeriod] = useState("1y");

  const { data: sectorData, isLoading } = useSWR(
    `/api/market/sector/${encodeURIComponent(cfg.slug)}`, fetcher,
    { revalidateOnFocus: false }
  );

  const { data: indexData, isLoading: indexLoading } = useSWR(
    cfg.indexSlug ? `/api/market/index/${cfg.indexSlug}?period=${period}` : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  const stocks: SectorStock[] = sectorData?.stocks ?? [];

  const performers = [...stocks]
    .filter((s) => s.change_pct != null)
    .sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0));

  const losers = [...performers].reverse();

  const allstocks = [...stocks]
    .filter((s) => s.market_cap != null)
    .sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0));

  const listMap: Record<SectorTab, SectorStock[]> = {
    performers, losers, allstocks,
  };

  const indexQ    = indexData?.quote ?? {};
  const indexHist = indexData?.history ?? {};
  const indexUp   = (indexHist.pct_change ?? 0) >= 0;
  const indexCandles: Candle[] = indexHist.candles ?? [];

  // Aggregate for badge
  const avgChange = stocks.length
    ? stocks.reduce((s, x) => s + (x.change_pct ?? 0), 0) / stocks.filter(x => x.change_pct != null).length
    : null;

  const Icon = cfg.icon;

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Section header */}
      <div className="flex items-center gap-3">
        <span className={clsx("flex h-9 w-9 items-center justify-center rounded-xl ring-1", cfg.color, cfg.accent)}>
          <Icon className="h-4 w-4" />
        </span>
        <div>
          <h2 className="font-display text-xl font-bold">{cfg.name}</h2>
          <p className="text-xs text-muted">
            {stocks.length} stocks tracked ·{" "}
            {avgChange != null && (
              <span className={avgChange >= 0 ? "text-up font-semibold" : "text-down font-semibold"}>
                avg {avgChange >= 0 ? "+" : ""}{avgChange.toFixed(2)}% today
              </span>
            )}
          </p>
        </div>
        {avgChange != null && (
          <span className={clsx(
            "ml-auto rounded-full px-3 py-1 text-xs font-bold ring-1",
            avgChange >= 0 ? "bg-up/10 text-up ring-up/20" : "bg-down/10 text-down ring-down/20"
          )}>
            {avgChange >= 0 ? <TrendingUp className="inline h-3 w-3 mr-1" /> : <TrendingDown className="inline h-3 w-3 mr-1" />}
            {avgChange >= 0 ? "+" : ""}{avgChange.toFixed(2)}%
          </span>
        )}
      </div>

      {/* Sector index chart (if available) */}
      {cfg.indexSlug && (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
            <div>
              <p className="text-xs text-muted">Sector Index</p>
              <p className="font-semibold text-fg">{cfg.name} Index</p>
              {indexQ.current_price && (
                <p className="nums text-sm font-bold text-fg">
                  {indexQ.current_price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                  {indexHist.pct_change != null && (
                    <span className={clsx("ml-2 text-xs", indexUp ? "text-up" : "text-down")}>
                      {indexUp ? "+" : ""}{indexHist.pct_change.toFixed(2)}%
                    </span>
                  )}
                </p>
              )}
            </div>
            <div className="flex items-center gap-1 rounded-lg bg-raised p-1">
              {PERIODS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPeriod(p.value)}
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
          <div className="px-2 pb-3 pt-3">
            {indexLoading || indexCandles.length === 0 ? (
              <div className="skeleton h-44 w-full rounded-lg" />
            ) : (
              <PriceChart candles={indexCandles} up={indexUp} />
            )}
          </div>
        </Card>
      )}

      {/* Tab list */}
      <Card className="overflow-hidden">
        {/* Tab header */}
        <div className="flex items-center justify-between border-b border-border">
          <div className="flex overflow-x-auto">
            {([
              { value: "performers" as SectorTab, label: "Top Performers", icon: TrendingUp },
              { value: "losers"     as SectorTab, label: "Top Losers",     icon: TrendingDown },
              { value: "allstocks"  as SectorTab, label: "All Stocks",     icon: BarChart3 },
            ] as { value: SectorTab; label: string; icon: React.ComponentType<{className?: string}> }[]).map((t) => {
              const TIcon = t.icon;
              return (
                <button
                  key={t.value}
                  onClick={() => setTab(t.value)}
                  className={clsx(
                    "flex shrink-0 items-center gap-1.5 border-b-2 px-5 py-3.5 text-sm font-medium transition-all",
                    tab === t.value
                      ? "border-saffron text-saffron"
                      : "border-transparent text-muted hover:text-fg"
                  )}
                >
                  <TIcon className="h-3.5 w-3.5" />
                  {t.label}
                  {t.value === "allstocks" && stocks.length > 0 && (
                    <span className="ml-1 rounded-full bg-raised px-1.5 py-0.5 text-[10px] font-bold text-muted">
                      {stocks.length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Column labels */}
        <div className="flex items-center justify-between border-b border-border/50 px-5 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted">
          <span>Stock</span>
          <span>Price · {tab === "allstocks" ? "Mkt Cap" : "1D Change"}</span>
        </div>

        {/* Rows — scrollable container for All Stocks tab */}
        {isLoading ? (
          <RowSkeleton />
        ) : tab === "allstocks" ? (
          <div
            className="overflow-y-auto divide-y divide-border"
            style={{ maxHeight: "480px" }}
          >
            {allstocks.length === 0
              ? <p className="px-5 py-8 text-center text-sm text-muted">No stocks found</p>
              : allstocks.map((s, i) => (
                  <StockRow key={s.ticker} stock={s} rank={i + 1} />
                ))
            }
          </div>
        ) : (
          <div className="divide-y divide-border">
            {listMap[tab].slice(0, 10).map((s, i) => (
              <StockRow key={s.ticker} stock={s} rank={i + 1} />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

/* ─── Page ──────────────────────────────────────── */
export default function MarketPage() {
  const [niftyPeriod, setNiftyPeriod]   = useState("1y");
  const [sensexPeriod, setSensexPeriod] = useState("1y");
  const [activeSector, setActiveSector] = useState<SectorCfg | null>(null);

  const handleSectorClick = (s: SectorCfg) => {
    // Toggle off if same sector clicked again
    setActiveSector((prev) => (prev?.slug === s.slug ? null : s));
    // Scroll to sector detail smoothly
    if (activeSector?.slug !== s.slug) {
      setTimeout(() => {
        document.getElementById("sector-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 100);
    }
  };

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
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-fg">Explore by Sector</h2>
            <p className="text-xs text-muted">Click any sector to see index chart, top performers, losers &amp; large caps</p>
          </div>
          {activeSector && (
            <button
              onClick={() => setActiveSector(null)}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-muted ring-1 ring-border hover:bg-raised hover:text-fg transition-all"
            >
              <ChevronLeft className="h-3.5 w-3.5" /> Back to all
            </button>
          )}
        </div>
        <SectorGrid selected={activeSector} onSelect={handleSectorClick} />
      </section>

      {/* ── Sector detail ── */}
      {activeSector && (
        <section id="sector-detail">
          <SectorDetail cfg={activeSector} />
        </section>
      )}

    </div>
  );
}
