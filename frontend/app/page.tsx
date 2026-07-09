"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import useSWR from "swr";

/* ─── Lazy-load hook: fires when element enters viewport OR after 2s max ── */
function useLazy(rootMargin = "400px") {
  const ref  = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (ready) return;
    const activate = () => setReady(true);
    // Hard cap: always load within 2s so MF/deals aren't stuck forever
    const timer = setTimeout(activate, 2000);
    const el = ref.current;
    if (!el) return () => clearTimeout(timer);
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { activate(); obs.disconnect(); } },
      { rootMargin },
    );
    obs.observe(el);
    return () => { clearTimeout(timer); obs.disconnect(); };
  }, [ready, rootMargin]);
  return { ref, ready };
}
import Link from "next/link";
import { fetcher, inr, inrCompact, pct, signCls } from "@/lib/api";
import { SearchBox } from "@/components/SearchBox";
import { useWatchlist } from "@/lib/useWatchlist";
import {
  TrendingUp, TrendingDown, Zap, BarChart3,
  Sparkles, Activity, ArrowUpRight, ArrowDownRight,
  ChevronRight, Bookmark, ArrowUpDown, Rocket, Flame,
} from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { StockLogo } from "@/components/StockLogo";
import { HoverEffect, HoverEffectGroup } from "@/components/ui/card-hover-effect";

/* ─── Types ──────────────────────────────────────── */
type Stock = {
  ticker: string;
  name: string;
  price: number;
  change_pct: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  volume: number | null;
  avg_volume: number | null;
  cap_type: "large" | "mid" | "small";
  website?: string | null;
};
type OverviewData = {
  gainers: Stock[];
  losers: Stock[];
  high_volume: Stock[];
  fetched_at?: number;
};

/* ─── Hero background — light/dark variants ───────── */
function AuroraBg() {
  const VP = { x: 720, y: -60 };
  const W  = 1440;
  const H  = 220;
  const spokeXs = [0, 120, 240, 360, 480, 580, 660, 720, 780, 860, 960, 1080, 1200, 1320, 1440];
  const hLines  = [60, 100, 130, 155, 175, 190, 205, 218];

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>

      {/* ── LIGHT MODE: colourful aurora blobs ── */}
      <div className="dark:hidden">
        <div className="absolute" style={{
          top: "-18%", right: "-12%", width: "780px", height: "780px", borderRadius: "50%",
          background: "radial-gradient(circle at center, rgba(245,165,36,0.32) 0%, rgba(251,146,60,0.18) 35%, transparent 70%)",
          filter: "blur(72px)", animation: "aurora-drift-1 18s ease-in-out infinite alternate",
        }} />
        <div className="absolute" style={{
          bottom: "-20%", left: "-14%", width: "680px", height: "680px", borderRadius: "50%",
          background: "radial-gradient(circle at center, rgba(139,92,246,0.28) 0%, rgba(109,67,236,0.14) 40%, transparent 70%)",
          filter: "blur(80px)", animation: "aurora-drift-2 22s ease-in-out infinite alternate",
        }} />
        <div className="absolute" style={{
          top: "15%", left: "5%", width: "520px", height: "520px", borderRadius: "50%",
          background: "radial-gradient(circle at center, rgba(20,184,166,0.18) 0%, rgba(6,182,212,0.10) 45%, transparent 70%)",
          filter: "blur(90px)", animation: "aurora-drift-3 26s ease-in-out infinite alternate",
        }} />
        <div className="absolute" style={{
          top: "-10%", left: "28%", width: "460px", height: "460px", borderRadius: "50%",
          background: "radial-gradient(circle at center, rgba(251,113,133,0.14) 0%, transparent 65%)",
          filter: "blur(70px)", animation: "aurora-drift-4 14s ease-in-out infinite alternate",
        }} />
        <div className="absolute" style={{
          top: "20%", left: "42%", width: "360px", height: "360px", borderRadius: "50%",
          background: "radial-gradient(circle at center, rgba(245,165,36,0.12) 0%, transparent 65%)",
          filter: "blur(60px)", animation: "aurora-drift-5 10s ease-in-out infinite alternate",
        }} />
      </div>

      {/* ── DARK MODE: monochrome top glow only ── */}
      <div className="hidden dark:block">
        {/* Single top-centre radial — very faint white */}
        <div className="absolute inset-x-0 top-0" style={{
          height: "60%",
          background: "radial-gradient(ellipse 70% 55% at 50% -5%, rgba(255,255,255,0.055) 0%, transparent 100%)",
        }} />
        {/* Subtle saffron warmth at top-right corner only */}
        <div className="absolute" style={{
          top: "-20%", right: "-10%", width: "500px", height: "500px", borderRadius: "50%",
          background: "radial-gradient(circle at center, rgba(246,171,40,0.07) 0%, transparent 70%)",
          filter: "blur(80px)",
        }} />
      </div>

      {/* ── Grain noise overlay (both modes) ── */}
      <div className="absolute inset-0" style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E")`,
        backgroundRepeat: "repeat", backgroundSize: "180px 180px",
        opacity: 0.045, mixBlendMode: "overlay",
      }} />

      {/* ── Perspective grid — bottom ── */}
      <div className="absolute inset-x-0 bottom-0" style={{ height: `${H}px` }}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="w-full h-full">
          <defs>
            {/* light mode grid — amber */}
            <linearGradient id="grid-fade-light" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="rgb(245,165,36)" stopOpacity="0" />
              <stop offset="60%"  stopColor="rgb(245,165,36)" stopOpacity="0.12" />
              <stop offset="100%" stopColor="rgb(245,165,36)" stopOpacity="0.22" />
            </linearGradient>
            <mask id="grid-mask-light"><rect width={W} height={H} fill="url(#grid-fade-light)" /></mask>
            {/* dark mode grid — white/grey */}
            <linearGradient id="grid-fade-dark" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="rgb(255,255,255)" stopOpacity="0" />
              <stop offset="55%"  stopColor="rgb(255,255,255)" stopOpacity="0.035" />
              <stop offset="100%" stopColor="rgb(255,255,255)" stopOpacity="0.06" />
            </linearGradient>
            <mask id="grid-mask-dark"><rect width={W} height={H} fill="url(#grid-fade-dark)" /></mask>
          </defs>

          {/* light */}
          <g mask="url(#grid-mask-light)" className="dark:hidden">
            {spokeXs.map((x, i) => (
              <line key={`sl${i}`} x1={VP.x} y1={VP.y} x2={x} y2={H}
                stroke="rgb(245,165,36)" strokeWidth="0.6" strokeOpacity="0.9" />
            ))}
            {hLines.map((y, i) => {
              const t = (y - VP.y) / (H - VP.y);
              return <line key={`hl${i}`} x1={VP.x + (0 - VP.x)*t} y1={y} x2={VP.x + (W - VP.x)*t} y2={y}
                stroke="rgb(245,165,36)" strokeWidth="0.5" strokeOpacity="0.85" />;
            })}
            <ellipse cx={VP.x} cy={H * 0.28} rx={280} ry={28} fill="rgb(245,165,36)" opacity="0.08" />
          </g>

          {/* dark */}
          <g mask="url(#grid-mask-dark)" className="hidden dark:block">
            {spokeXs.map((x, i) => (
              <line key={`sd${i}`} x1={VP.x} y1={VP.y} x2={x} y2={H}
                stroke="rgb(200,210,230)" strokeWidth="0.5" strokeOpacity="0.7" />
            ))}
            {hLines.map((y, i) => {
              const t = (y - VP.y) / (H - VP.y);
              return <line key={`hd${i}`} x1={VP.x + (0 - VP.x)*t} y1={y} x2={VP.x + (W - VP.x)*t} y2={y}
                stroke="rgb(200,210,230)" strokeWidth="0.4" strokeOpacity="0.65" />;
            })}
          </g>
        </svg>
      </div>

      {/* ── Vignette ── */}
      <div className="absolute inset-0" style={{
        background: "radial-gradient(ellipse at 50% 40%, transparent 40%, rgb(var(--color-ink)/0.5) 100%)",
      }} />
    </div>
  );
}

/* ─── Pill tabs ──────────────────────────────────── */
function Tabs<T extends string>({
  tabs, active, onChange,
}: {
  tabs: { value: T; label: string; icon?: React.ReactNode }[];
  active: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onChange(t.value)}
          className={clsx(
            "flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium transition-all duration-150",
            active === t.value
              ? "bg-ink text-white shadow-sm dark:bg-white dark:text-ink"
              : "bg-raised text-muted ring-1 ring-border hover:text-fg hover:ring-border/80"
          )}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* ─── Sort selector ──────────────────────────────── */
type SortKey = "change_pct" | "market_cap";

function SortBtn({ sort, onChange }: { sort: SortKey; onChange: (s: SortKey) => void }) {
  const labels: Record<SortKey, string> = {
    change_pct: "1D Change",
    market_cap: "Mkt Cap",
  };
  const options: SortKey[] = ["change_pct", "market_cap"];
  return (
    <button
      onClick={() => {
        const i = options.indexOf(sort);
        onChange(options[(i + 1) % options.length]);
      }}
      className="flex items-center gap-1 text-xs font-semibold text-saffron hover:text-saffron/80 transition-colors"
    >
      {labels[sort]} <ArrowUpDown className="h-3 w-3" />
    </button>
  );
}

function sortStocks(stocks: Stock[], key: SortKey): Stock[] {
  return [...stocks].sort((a, b) => {
    const av = (a as unknown as Record<string, number | null>)[key] ?? 0;
    const bv = (b as unknown as Record<string, number | null>)[key] ?? 0;
    return bv - av;
  });
}

/* ─── List row — Groww style ─────────────────────── */
/* ─── Bookmark button ────────────────────────────── */
function BookmarkBtn({ ticker, name }: { ticker: string; name: string }) {
  const { isWatched, toggle } = useWatchlist();
  const watched = isWatched(ticker);
  return (
    <button
      onClick={async (e) => {
        e.preventDefault();
        e.stopPropagation();
        await toggle(ticker, name);
      }}
      title={watched ? "Remove from watchlist" : "Add to watchlist"}
      className={clsx(
        "shrink-0 rounded-md p-1 transition-all duration-200 hover:scale-110",
        watched
          ? "text-saffron"
          : "text-muted/50 hover:text-muted"
      )}
    >
      <Bookmark className={clsx("h-4 w-4", watched ? "fill-saffron stroke-saffron" : "fill-none")} />
    </button>
  );
}

function StockListRow({ s, rank }: { s: Stock; rank?: number }) {
  const up   = (s.change_pct ?? 0) >= 0;
  const bare = s.ticker.replace(/\.(NS|BO)$/, "");
  const name = s.name || bare;

  return (
    <div className="group flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-raised/50">
      <Link
        href={`/stock/${encodeURIComponent(s.ticker)}`}
        className="flex min-w-0 flex-1 items-center gap-4"
      >
        <StockLogo ticker={s.ticker} website={s.website} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-fg group-hover:text-saffron transition-colors leading-tight">
            {name}
          </p>
          <div className="mt-0.5 flex items-center gap-2 min-w-0">
            <span className="shrink-0 font-mono text-[10px] text-muted">{bare}</span>
            {s.market_cap && (
              <span className="truncate text-[10px] text-muted">· {inrCompact(s.market_cap)}</span>
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <p className="nums text-sm font-bold text-fg">{inr(s.price)}</p>
          <p className={clsx(
            "nums mt-0.5 flex items-center justify-end gap-0.5 text-xs font-semibold",
            up ? "text-up" : "text-down"
          )}>
            {up ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {up ? "+" : ""}{(s.change_pct ?? 0).toFixed(2)}%
          </p>
        </div>
      </Link>
      <BookmarkBtn ticker={s.ticker} name={name} />
    </div>
  );
}

/* ─── List skeleton ──────────────────────────────── */
function ListSkeleton({ n = 8 }: { n?: number }) {
  return (
    <div className="divide-y divide-border">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-5 py-3.5" style={{ opacity: 1 - i * 0.08 }}>
          <div className="skeleton h-9 w-9 rounded-xl shrink-0" />
          <div className="flex-1 space-y-1.5">
            <div className="skeleton h-3.5 w-32 rounded" />
            <div className="skeleton h-2.5 w-20 rounded" />
          </div>
          <div className="space-y-1.5 text-right shrink-0">
            <div className="skeleton h-3.5 w-16 rounded" />
            <div className="skeleton h-2.5 w-12 rounded ml-auto" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Section with header ────────────────────────── */
function SectionCard({
  title, subtitle, icon, sort, onSortChange, children, topBorder,
}: {
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  sort?: SortKey;
  onSortChange?: (s: SortKey) => void;
  children: React.ReactNode;
  topBorder?: "up" | "down" | "warn" | "neutral";
}) {
  const accentColors = {
    up:      "from-up",
    down:    "from-down",
    warn:    "from-yellow-500",
    neutral: "from-saffron",
  };
  const accent = topBorder ? accentColors[topBorder] : "from-saffron";
  return (
    <Card className="relative overflow-hidden">
      {/* Gradient top line */}
      <div className={clsx(
        "relative h-[2px] w-full bg-gradient-to-r to-transparent via-current",
        accent
      )} />
      {/* Header */}
      <div className="relative flex items-center justify-between gap-3 border-b border-border/80 bg-raised/30 px-5 py-3.5 backdrop-blur-sm">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface text-saffron ring-1 ring-border shadow-sm">
            {icon}
          </span>
          <div>
            <h2 className="text-sm font-semibold text-fg">{title}</h2>
            {subtitle && <p className="text-[10px] text-muted mt-0.5">{subtitle}</p>}
          </div>
        </div>
        {sort && onSortChange && (
          <SortBtn sort={sort} onChange={onSortChange} />
        )}
      </div>
      <div className="relative">{children}</div>
    </Card>
  );
}

/* ─── Market Movers block ────────────────────────── */
function MoverColumn({
  title,
  stocks,
  loading,
  color,
}: {
  title: string;
  stocks: Stock[];
  loading: boolean;
  color: "up" | "down";
}) {
  return (
    <div className="flex-1 min-w-0 flex flex-col">
      <div className={clsx(
        "px-4 py-2.5 text-xs font-semibold uppercase tracking-wider border-b border-border shrink-0",
        color === "up" ? "text-up" : "text-down"
      )}>
        {color === "up" ? "↑" : "↓"} {title}
      </div>
      {/* ~10 rows visible (each row ≈56px), scroll for the rest */}
      <div className="overflow-y-auto max-h-[560px] divide-y divide-border scrollbar-thin scrollbar-track-transparent scrollbar-thumb-border">
        {loading
          ? <ListSkeleton n={8} />
          : stocks.length
          ? stocks.map((s) => <StockListRow key={s.ticker} s={s} />)
          : <p className="px-4 py-8 text-center text-sm text-muted">No data</p>
        }
      </div>
    </div>
  );
}

function MarketMovers({ data, loading }: { data?: OverviewData; loading: boolean }) {
  const gainers = data?.gainers ?? [];
  const losers  = data?.losers  ?? [];

  const ageMin = data?.fetched_at
    ? Math.round((Date.now() / 1000 - data.fetched_at) / 60)
    : null;

  return (
    <SectionCard
      title="Market Movers"
      subtitle={ageMin != null ? `Nifty 50 · as of ${ageMin} min ago` : "Nifty 50"}
      icon={<Activity className="h-4 w-4" />}
    >
      <div className="flex flex-col divide-y divide-border sm:flex-row sm:divide-y-0 sm:divide-x">
        <MoverColumn title="Top Gainers" stocks={gainers} loading={loading} color="up"   />
        <MoverColumn title="Top Losers"  stocks={losers}  loading={loading} color="down" />
      </div>
    </SectionCard>
  );
}

/* ─── Top Mutual Funds block ─────────────────────── */
type MFHighlights = {
  popular:     MFFund[];
  top_gainers: MFFund[];
  top_losers:  MFFund[];
  most_active: MFFund[];
};
type MFFund = {
  scheme_code: number;
  name:        string;
  nav:         number | null;
  nav_date:    string | null;
  return_1d:   number | null;
  return_1y:   number | null;
  return_3y:   number | null;
  return_5y:   number | null;
  fund_house:  string | null;
  scheme_type: string | null;
};
type MFPeriod = "1y" | "3y" | "5y";
type MFView   = "popular" | "gainers" | "losers";

const CAT_COLORS: Record<string, string> = {
  "Small Cap":  "bg-rose-500/10 text-rose-500",
  "Mid Cap":    "bg-orange-500/10 text-orange-500",
  "Large Cap":  "bg-blue-500/10 text-blue-500",
  "Flexi Cap":  "bg-violet-500/10 text-violet-500",
  "ELSS":       "bg-green-500/10 text-green-500",
  "Hybrid":     "bg-teal-500/10 text-teal-500",
  "Index":      "bg-sky-500/10 text-sky-500",
  "Debt":       "bg-slate-500/10 text-slate-400",
  "Liquid":     "bg-slate-400/10 text-slate-400",
  "Sector":     "bg-amber-500/10 text-amber-500",
  "Intl":       "bg-purple-500/10 text-purple-500",
  "Thematic":   "bg-pink-500/10 text-pink-500",
  "Equity":     "bg-saffron/10 text-saffron",
};

function inferCategory(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("small cap") || n.includes("smallcap"))                     return "Small Cap";
  if (n.includes("mid cap") || n.includes("midcap"))                         return "Mid Cap";
  if (n.includes("large cap") || n.includes("largecap"))                     return "Large Cap";
  if (n.includes("flexi cap") || n.includes("flexicap") || n.includes("multi cap")) return "Flexi Cap";
  if (n.includes("elss") || n.includes("tax saver") || n.includes("long term equity")) return "ELSS";
  if (n.includes("balanced") || n.includes("hybrid") || n.includes("advantage")) return "Hybrid";
  if (n.includes("liquid") || n.includes("overnight") || n.includes("money market")) return "Liquid";
  if (n.includes("debt") || n.includes("bond") || n.includes("gilt") || n.includes("income")) return "Debt";
  if (n.includes("index") || n.includes("nifty") || n.includes("sensex"))    return "Index";
  if (n.includes("international") || n.includes("global") || n.includes("overseas")) return "Intl";
  if (n.includes("sectoral") || n.includes("banking") || n.includes("pharma") || n.includes("infra")) return "Sector";
  if (n.includes("thematic") || n.includes("esg") || n.includes("consumption")) return "Thematic";
  return "Equity";
}

function shortAMC(fundHouse: string | null): string {
  if (!fundHouse) return "";
  const h = fundHouse.toLowerCase();
  if (h.includes("sbi"))                         return "SBI";
  if (h.includes("hdfc"))                        return "HDFC";
  if (h.includes("icici"))                       return "ICICI Pru";
  if (h.includes("axis"))                        return "Axis";
  if (h.includes("mirae"))                       return "Mirae";
  if (h.includes("kotak"))                       return "Kotak";
  if (h.includes("nippon") || h.includes("reliance")) return "Nippon";
  if (h.includes("uti"))                         return "UTI";
  if (h.includes("aditya") || h.includes("birla") || h.includes("absl")) return "ABSL";
  if (h.includes("dsp"))                         return "DSP";
  if (h.includes("franklin"))                    return "Franklin";
  if (h.includes("parag parikh") || h.includes("ppfas")) return "PPFAS";
  if (h.includes("motilal"))                     return "Motilal";
  if (h.includes("tata"))                        return "Tata";
  if (h.includes("quant"))                       return "Quant";
  if (h.includes("whiteoak"))                    return "WhiteOak";
  if (h.includes("edelweiss"))                   return "Edelweiss";
  if (h.includes("bandhan"))                     return "Bandhan";
  if (h.includes("canara"))                      return "Canara";
  if (h.includes("invesco"))                     return "Invesco";
  if (h.includes("baroda") || h.includes("bnp")) return "Baroda BNP";
  return fundHouse.split(" ")[0];
}

function TopMutualFunds() {
  const [view,   setView]   = useState<MFView>("popular");
  const [period, setPeriod] = useState<MFPeriod>("1y");
  const { ref: lazyRef, ready } = useLazy();

  const { data, isLoading } = useSWR<MFHighlights>(
    ready ? `/api/mf/highlights?period=${period}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60_000 },
  );

  const funds: MFFund[] =
    view === "popular" ? (data?.popular ?? []) :
    view === "gainers" ? (data?.top_gainers ?? []) :
                         (data?.top_losers ?? []);

  const retKey = period === "3y" ? "return_3y" : period === "5y" ? "return_5y" : "return_1y";

  const viewTabs: { value: MFView; label: string }[] = [
    { value: "popular", label: "Popular" },
    { value: "gainers", label: "Top Gainers" },
    { value: "losers",  label: "Top Losers"  },
  ];
  const periodTabs: { value: MFPeriod; label: string }[] = [
    { value: "1y", label: "1Y" },
    { value: "3y", label: "3Y" },
    { value: "5y", label: "5Y" },
  ];

  return (
    <div ref={lazyRef}>
    <SectionCard
      title="Top Mutual Funds"
      subtitle="AMFI · live NAV via MFapi"
      icon={<BarChart3 className="h-4 w-4" />}
      topBorder="up"
    >
      {/* View + period toggles */}
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div className="flex gap-1">
          {viewTabs.map((t) => (
            <button
              key={t.value}
              onClick={() => setView(t.value)}
              className={clsx(
                "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
                view === t.value
                  ? "bg-saffron text-white shadow-sm"
                  : "text-muted hover:bg-raised hover:text-fg"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        {view !== "popular" && (
          <div className="flex items-center gap-0.5 rounded-lg bg-raised p-0.5">
            {periodTabs.map((t) => (
              <button
                key={t.value}
                onClick={() => setPeriod(t.value)}
                className={clsx(
                  "rounded-md px-2.5 py-1 text-micro font-semibold transition-all",
                  period === t.value
                    ? "bg-surface text-fg shadow-sm ring-1 ring-border"
                    : "text-muted hover:text-fg"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Column header */}
      <div className="grid grid-cols-[1fr_auto_auto] gap-2 px-5 py-2 text-micro-cap font-semibold uppercase tracking-wider text-muted border-b border-border">
        <span>Fund</span>
        <span className="text-right">NAV</span>
        <span className="text-right w-20">{view === "popular" ? "1Y Return" : `${period.toUpperCase()} Return`}</span>
      </div>

      <div className="divide-y divide-border">
        {isLoading ? (
          <ListSkeleton n={8} />
        ) : funds.length > 0 ? (
          funds.map((fund) => {
            const ret    = (fund[retKey] ?? fund.return_1y) as number | null;
            const retUp  = ret != null && ret >= 0;
            const dayUp  = (fund.return_1d ?? 0) >= 0;
            const cat    = inferCategory(fund.name);
            const amc    = shortAMC(fund.fund_house);
            // Strip "- Regular Plan - Growth" suffixes for display
            const displayName = fund.name
              .replace(/- (regular|direct) (plan|growth|idcw|dividend).*/i, "")
              .replace(/\s{2,}/g, " ")
              .trim();

            return (
              <Link
                key={fund.scheme_code}
                href={`/mf/${fund.scheme_code}`}
                className="grid grid-cols-[1fr_auto_auto] items-center gap-2 px-5 py-3 hover:bg-raised/40 transition-colors"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    {amc && (
                      <span className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold bg-raised text-muted">
                        {amc}
                      </span>
                    )}
                    <span className={clsx(
                      "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold",
                      CAT_COLORS[cat] ?? "bg-muted/10 text-muted"
                    )}>
                      {cat}
                    </span>
                  </div>
                  <p className="text-sm font-semibold text-fg truncate leading-tight">{displayName}</p>
                  {fund.return_1d != null && (
                    <span className={clsx("text-micro-cap font-semibold", dayUp ? "text-up" : "text-down")}>
                      {dayUp ? "▲" : "▼"} {Math.abs(fund.return_1d).toFixed(2)}% today
                    </span>
                  )}
                </div>

                <div className="text-right">
                  {fund.nav != null ? (
                    <>
                      <p className="nums text-sm font-semibold">₹{fund.nav.toFixed(2)}</p>
                      {fund.nav_date && (
                        <p className="text-[9px] text-muted">{fund.nav_date}</p>
                      )}
                    </>
                  ) : (
                    <span className="text-sm text-muted">—</span>
                  )}
                </div>

                <div className="w-20 text-right">
                  {ret != null ? (
                    <span className={clsx(
                      "inline-flex items-center gap-0.5 rounded-md px-2 py-1 text-xs font-bold",
                      retUp ? "bg-up/10 text-up" : "bg-down/10 text-down"
                    )}>
                      {retUp ? "▲" : "▼"} {Math.abs(ret).toFixed(1)}%
                    </span>
                  ) : (
                    <span className="text-xs text-muted">—</span>
                  )}
                </div>
              </Link>
            );
          })
        ) : (
          <div className="divide-y divide-border">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-5 py-3">
                <div className="h-7 w-7 rounded-md bg-muted/20 animate-pulse" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 w-36 rounded bg-muted/20 animate-pulse" />
                  <div className="h-2.5 w-24 rounded bg-muted/20 animate-pulse" />
                </div>
                <div className="h-4 w-14 rounded bg-muted/20 animate-pulse" />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border-t border-border px-5 py-2.5 flex items-center justify-between">
        <p className="text-[10px] text-muted">NAV via AMFI · MFapi.in · Not investment advice</p>
        <Link href="/mf" className="text-[10px] text-saffron hover:underline flex items-center gap-0.5">
          All funds <ChevronRight className="h-3 w-3" />
        </Link>
      </div>
    </SectionCard>
    </div>
  );
}

/* ─── More Markets: compact preview widgets ──────── */
function ViewAllLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="mt-2 flex items-center gap-0.5 text-[10px] text-saffron hover:underline">
      {label} <ChevronRight className="h-3 w-3" />
    </Link>
  );
}

type IpoPreview = { symbol: string; name: string; status: string; document_url?: string | null };

function IpoWidget() {
  const { data, isLoading } = useSWR<IpoPreview[]>("/api/market/ipo", fetcher, { revalidateOnFocus: false });
  const items = (data ?? []).filter((i) => i.status !== "listed").slice(0, 4);

  return (
    <SectionCard title="IPO Watch" icon={<Rocket className="h-4 w-4" />}>
      <div className="p-4">
        {isLoading ? (
          <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-4 w-full rounded" />)}</div>
        ) : items.length === 0 ? (
          <p className="text-xs text-muted">No upcoming or open IPOs right now.</p>
        ) : (
          <ul className="space-y-2">
            {items.map((ipo) => (
              <li key={ipo.symbol}>
                <Link href="/ipo" className="flex items-center justify-between gap-2 rounded-lg text-xs transition-colors hover:bg-raised/60 -mx-2 px-2 py-1">
                  <span className="truncate font-medium text-fg">{ipo.name.trim()}</span>
                  <span className="shrink-0 capitalize text-muted">{ipo.status}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <ViewAllLink href="/ipo" label="View all IPOs" />
      </div>
    </SectionCard>
  );
}

type CommodityPreview = { product: string; last_traded_price: string; per_change: number };

function CommoditiesWidget() {
  const { data, isLoading } = useSWR<CommodityPreview[]>("/api/market/commodities", fetcher, { revalidateOnFocus: false });
  const items = useMemo(() => {
    const byProduct = new Map<string, CommodityPreview>();
    for (const c of data ?? []) if (!byProduct.has(c.product)) byProduct.set(c.product, c);
    return [...byProduct.values()].slice(0, 4);
  }, [data]);

  return (
    <SectionCard title="Commodities" icon={<Flame className="h-4 w-4" />} topBorder="warn">
      <div className="p-4">
        {isLoading ? (
          <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-4 w-full rounded" />)}</div>
        ) : items.length === 0 ? (
          <p className="text-xs text-muted">Commodities data unavailable.</p>
        ) : (
          <ul className="space-y-2">
            {items.map((c) => {
              const up = c.per_change >= 0;
              return (
                <li key={c.product}>
                  <Link href="/commodities" className="flex items-center justify-between gap-2 rounded-lg text-xs transition-colors hover:bg-raised/60 -mx-2 px-2 py-1">
                    <span className="truncate font-medium text-fg">{c.product}</span>
                    <span className="nums shrink-0">
                      ₹{c.last_traded_price}{" "}
                      <span className={up ? "text-up" : "text-down"}>{up ? "+" : ""}{c.per_change?.toFixed(1)}%</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        <ViewAllLink href="/commodities" label="View all" />
      </div>
    </SectionCard>
  );
}

function FiftyTwoWeekWidget() {
  const { data, isLoading } = useSWR<{ highs: Stock[]; lows: Stock[] }>("/api/market/52week", fetcher, { revalidateOnFocus: false });
  const highs = data?.highs ?? [];
  const lows = data?.lows ?? [];

  return (
    <SectionCard title="52-Week High/Low" icon={<BarChart3 className="h-4 w-4" />} topBorder="up">
      <div className="p-4">
        {isLoading ? (
          <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-4 w-full rounded" />)}</div>
        ) : (
          <div className="space-y-1.5 text-xs">
            <p><span className="font-semibold text-up">{highs.length}</span> <span className="text-muted">new highs today</span></p>
            <p><span className="font-semibold text-down">{lows.length}</span> <span className="text-muted">new lows today</span></p>
            {highs[0] && <p className="truncate text-muted">Top high: {highs[0].name || highs[0].ticker}</p>}
            {lows[0] && <p className="truncate text-muted">Top low: {lows[0].name || lows[0].ticker}</p>}
          </div>
        )}
        <ViewAllLink href="/market#52-week" label="View all" />
      </div>
    </SectionCard>
  );
}

function PriceShockersWidget() {
  const { data, isLoading } = useSWR<Stock[]>("/api/market/price-shockers", fetcher, { revalidateOnFocus: false });
  const items = (data ?? []).slice(0, 4);

  return (
    <SectionCard title="Price Shockers" icon={<Zap className="h-4 w-4" />} topBorder="down">
      <div className="p-4">
        {isLoading ? (
          <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-4 w-full rounded" />)}</div>
        ) : items.length === 0 ? (
          <p className="text-xs text-muted">No price shockers right now.</p>
        ) : (
          <ul className="space-y-2">
            {items.map((s) => {
              const up = (s.change_pct ?? 0) >= 0;
              return (
                <li key={s.ticker}>
                  <Link href={`/stock/${encodeURIComponent(s.ticker)}`} className="flex items-center justify-between gap-2 rounded-lg text-xs transition-colors hover:bg-raised/60 -mx-2 px-2 py-1">
                    <span className="truncate font-medium text-fg">{s.name || s.ticker}</span>
                    {s.change_pct != null && (
                      <span className={clsx("nums shrink-0", up ? "text-up" : "text-down")}>
                        {up ? "+" : ""}{s.change_pct.toFixed(1)}%
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        <ViewAllLink href="/market#price-shockers" label="View all" />
      </div>
    </SectionCard>
  );
}

/* ─── Page ──────────────────────────────────────── */
export default function Home() {
  const { data, isLoading } = useSWR<OverviewData>("/api/market/overview", fetcher, {
    revalidateOnFocus: false,
    refreshInterval: 30_000,   // backend cache hit = <100 ms, so 30s feels live
  });


  const STAT_CHIPS = [
    { icon: <Zap className="h-3 w-3" />,       label: "Real-time Quotes"       },
    { icon: <Sparkles className="h-3 w-3" />,   label: "AI Concall Analysis"    },
    { icon: <BarChart3 className="h-3 w-3" />,  label: "Peer Benchmarking"      },
    { icon: <Activity className="h-3 w-3" />,   label: "5,000+ NSE/BSE Stocks"  },
  ];

  return (
    <div className="space-y-10">

      {/* ── Hero ── */}
      <section className="relative -mx-4 px-4 pb-24 pt-20 sm:-mx-6 sm:px-6 md:-mx-10 md:px-10 lg:-mx-14 lg:px-14 lg:pb-36 lg:pt-32">

        {/* Gradient mesh backdrop — Stripi signature; replaces animated blobs */}
        <div className="absolute inset-0 gradient-mesh" />

        {/* Content */}
        <div className="relative z-10 mx-auto max-w-3xl text-center">



          {/* Headline — display-xxl, weight 300, tight tracking */}
          <h1 className="hero-el mt-7 text-[2.75rem] font-light leading-[1.08] tracking-[-0.05em] sm:text-6xl lg:text-[4.25rem]">
            Stop Guessing.
            <br />
            <span className="hero-gradient-text">Start Knowing.</span>
          </h1>

          {/* Subtext */}
          <p className="hero-el mx-auto mt-6 max-w-xl text-[1.05rem] text-muted leading-[1.7]">
            Institutional-grade research for every Indian investor — AI concall summaries,
            live fundamentals, peer benchmarks &amp; portfolio intelligence,{" "}
            <span className="font-semibold text-fg">completely free.</span>
          </p>

          {/* Search bar */}
          {/* relative z-20: .hero-el's fade-up animation gives this its own
              stacking context, so without an explicit z-index it paints
              behind the later hero-el siblings (Trending row, stat chips)
              in DOM order — burying the dropdown under them. */}
          <div className="hero-el relative z-20 mx-auto mt-8 max-w-2xl">
            <SearchBox
              size="hero"
              autoFocus
              placeholder="Search any company — RELIANCE, TCS, HDFC…"
            />
          </div>

          {/* Trending tickers */}
          <div className="hero-el mt-5 flex flex-wrap items-center justify-center gap-2">
            <span className="text-xs font-semibold text-muted">Trending:</span>
            {["ITC", "RELIANCE", "HDFCBANK", "TCS", "INFY", "BAJFINANCE", "SBIN", "TATASTEEL"].map((t) => (
              <Link
                key={t}
                href={`/stock/${t}.NS`}
                className="rounded-full border border-border/60 bg-surface/70 px-3 py-1 text-xs font-semibold text-muted backdrop-blur-sm transition-all duration-200 hover:border-saffron/50 hover:bg-saffron/8 hover:text-saffron hover:-translate-y-0.5 hover:shadow-sm"
              >
                {t}
              </Link>
            ))}
          </div>

          {/* Stat chips */}
          <div className="hero-el mt-8 flex flex-wrap justify-center gap-2.5">
            {STAT_CHIPS.map((chip, i) => (
              <div
                key={chip.label}
                className="hero-chip flex items-center gap-2 rounded-xl border border-border/60 bg-surface/60 px-3.5 py-2 text-[11.5px] font-medium text-muted backdrop-blur-sm shadow-sm transition-all duration-200 hover:border-saffron/30 hover:text-fg"
                style={{ animationDelay: `${i * 0.45}s`, animationDuration: `${3.5 + i * 0.4}s` }}
              >
                <span className="flex h-5 w-5 items-center justify-center rounded-md bg-saffron/12 text-saffron">
                  {chip.icon}
                </span>
                {chip.label}
              </div>
            ))}
          </div>

          {/* Feature nav pills */}
          <div className="hero-el mt-5 flex flex-wrap justify-center gap-2">
            {[
              { href: "/concall", icon: <Sparkles className="h-3 w-3" />, text: "AI Concall",   color: "hover:border-accent/40 hover:bg-accent/8 hover:text-accent" },
              { href: "/peers",   icon: <BarChart3 className="h-3 w-3" />, text: "Peer Compare", color: "hover:border-blue-500/40 hover:bg-blue-500/8 hover:text-blue-400" },
              { href: "/ask",     icon: <Activity className="h-3 w-3" />,  text: "Ask AI",        color: "hover:border-up/40 hover:bg-up/8 hover:text-up" },
              { href: "/market",  icon: <TrendingUp className="h-3 w-3" />, text: "Market",       color: "hover:border-saffron/40 hover:bg-saffron/8 hover:text-saffron" },
            ].map((c) => (
              <Link
                key={c.text}
                href={c.href}
                className={clsx(
                  "flex items-center gap-1.5 rounded-full border border-border/70 bg-raised/50 px-3.5 py-1.5 text-xs font-medium text-muted backdrop-blur-sm",
                  "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-sm",
                  c.color
                )}
              >
                {c.icon} {c.text}
              </Link>
            ))}
          </div>

        </div>
      </section>

      {/* ── Two-column: Movers + Mutual Funds ── */}
      <div className="grid gap-6 lg:grid-cols-2">
        <MarketMovers data={data} loading={isLoading} />
        <TopMutualFunds />
      </div>

      {/* ── More Markets ── */}
      <section className="space-y-4 animate-fade-up">
        <h2 className="font-display text-xl font-semibold">More Markets</h2>
        <HoverEffectGroup
          count={4}
          layoutId="more-markets-hover-bg"
          className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
        >
          {(idx) => [
            <IpoWidget key="ipo" />,
            <CommoditiesWidget key="commodities" />,
            <FiftyTwoWeekWidget key="52week" />,
            <PriceShockersWidget key="shockers" />,
          ][idx]}
        </HoverEffectGroup>
      </section>

      {/* ── Features ── */}
      <section className="space-y-4 animate-fade-up">
        <h2 className="font-display text-xl font-semibold">Platform Features</h2>
        <HoverEffect
          items={[
            {
              icon: <Sparkles className="h-5 w-5 text-saffron" />,
              title: "AI Concall Analysis",
              description: "Quarter-wise earnings call summaries with real news context — highlights, management commentary, guidance.",
              link: "/concall",
              color: "bg-saffron/10 ring-saffron/20 group-hover:bg-saffron group-hover:text-white group-hover:ring-saffron",
              accentColor: "bg-gradient-to-r from-saffron/60 via-saffron to-saffron/60",
            },
            {
              icon: <ArrowUpRight className="h-5 w-5 text-blue-400" />,
              title: "Peer Comparison",
              description: "Compare any stock against sector peers on P/E, ROE, revenue growth — with sector median benchmarking.",
              link: "/peers",
              color: "bg-blue-500/10 ring-blue-500/20 group-hover:bg-blue-500 group-hover:text-white group-hover:ring-blue-500",
              accentColor: "bg-gradient-to-r from-blue-500/60 via-blue-500 to-blue-500/60",
            },
            {
              icon: <Activity className="h-5 w-5 text-accent" />,
              title: "Ask AI Anything",
              description: "Chat with an Indian market expert AI — taxation, sector outlook, stock analysis, FII flows and more.",
              link: "/ask",
              color: "bg-accent/10 ring-accent/20 group-hover:bg-accent group-hover:text-white group-hover:ring-accent",
              accentColor: "bg-gradient-to-r from-accent/60 via-accent to-accent/60",
            },
          ]}
        />
      </section>

    </div>
  );
}
