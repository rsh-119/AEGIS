"use client";

import { use, useRef, useState } from "react";
import useSWR from "swr";
import { useRouter } from "next/navigation";
import { fetcher, inr, inrCompact, pct, num, signCls, post } from "@/lib/api";
import { useRealtimePrice } from "@/lib/useRealtimePrice";
import { useAuth } from "@/lib/auth";
import { PriceChart } from "@/components/PriceChart";
import { VolumeChart } from "@/components/VolumeChart";
import { ValuationChart } from "@/components/ValuationChart";
import { HealthCard } from "@/components/HealthCard";
import { ForecastCard } from "@/components/ForecastCard";
import { AskAI } from "@/components/AskAI";
import { ConcallCard } from "@/components/ConcallCard";
import { PeerComparison } from "@/components/PeerComparison";
import { ShareholdingPie } from "@/components/ShareholdingPie";
import { TechnicalsCard } from "@/components/TechnicalsCard";
import { ChartCard } from "@/components/ui/animated-card-chart";
import Link from "next/link";
import { Plus, ExternalLink, TrendingUp, TrendingDown, ChevronLeft, ChevronRight, BarChart3, CheckCircle2, AlertTriangle, AlertCircle, Info, Newspaper, Target, Eye, Zap, Bell, Calendar, ArrowUpRight, Gift } from "lucide-react";
import clsx from "clsx";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";

const PERIODS = [
  { label: "1M", value: "1mo" },
  { label: "3M", value: "3mo" },
  { label: "6M", value: "6mo" },
  { label: "1Y", value: "1y" },
  { label: "2Y", value: "2y" },
  { label: "5Y", value: "5y" },
  { label: "All", value: "max" },
];

export default function StockPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = use(params);
  const symbol = decodeURIComponent(ticker);
  const { user } = useAuth();
  const router = useRouter();
  const [period, setPeriod]           = useState("max");
  const [chartTab, setChartTab]       = useState<"price" | "volume">("price");
  const [valuationTab, setValuationTab] = useState<"pe" | "pb">("pe");

  // ── FAST: quote + history + signals — renders the page immediately (~0.5s) ──
  const { data: core, error, isLoading: coreLoading } = useSWR(
    `/api/stocks/${symbol}/core?period=6mo`,
    fetcher,
    { revalidateOnFocus: false }
  );

  // ── DEFERRED: news + AI + health + forecasts — fills in while page is visible ──
  const { data: ins, isLoading: insLoading } = useSWR(
    core ? `/api/stocks/${symbol}/insights` : null,  // start only after core is ready
    fetcher,
    { revalidateOnFocus: false }
  );

  // History — re-fetched when period selector changes (default 6mo already in core)
  const { data: histData, isLoading: histLoading } = useSWR(
    period !== "6mo" ? `/api/stocks/${symbol}/history?period=${period}` : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  // ── DEFERRED IndianAPI data — loads in background after core is ready ──────
  const { data: analystTargets } = useSWR(
    core ? `/api/stocks/${symbol}/analyst-targets` : null,
    fetcher,
    { revalidateOnFocus: false }
  );
  const { data: analystForecasts } = useSWR(
    core ? `/api/stocks/${symbol}/analyst-forecasts` : null,
    fetcher,
    { revalidateOnFocus: false }
  );
  const { data: announcements } = useSWR(
    core ? `/api/stocks/${symbol}/announcements` : null,
    fetcher,
    { revalidateOnFocus: false }
  );
  const { data: corpActions } = useSWR(
    core ? `/api/stocks/${symbol}/corporate-actions` : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  // Real-time price feed — WS → SSE → REST polling with auto-reconnect
  const { tick: liveTick, status: streamStatus } = useRealtimePrice(symbol);

  if (error) return <ErrorState symbol={symbol} />;
  if (coreLoading || !core) return <LoadingState />;

  const q    = core.quote;
  const hist = histData ?? core.history;
  const ai   = ins?.ai_analysis ?? {};

  // Prefer live price from stream; fall back to static quote
  const displayPrice = liveTick?.price ?? q.current_price;
  const change = displayPrice && q.previous_close
    ? ((displayPrice - q.previous_close) / q.previous_close) * 100
    : null;
  const up = (hist?.pct_change ?? 0) >= 0;

  async function addToWatchlist() {
    if (!user) {
      router.push("/login");
      return;
    }
    try {
      await post("/api/watchlist", { ticker: symbol });
      alert(`${symbol} added to watchlist`);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  const periodLabel = PERIODS.find((p) => p.value === period)?.label ?? "6M";

  return (
    <div className="space-y-6 animate-fade-up">

      {/* ── Header row ── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="font-display text-xl sm:text-2xl md:text-3xl font-bold leading-tight">{q.company_name}</h1>
            <Badge className="bg-raised text-muted ring-1 ring-border text-xs">{q.exchange}</Badge>
          </div>
          <div className="mt-1.5 flex items-center gap-2 flex-wrap text-muted">
            <span className="font-mono text-xs">{symbol}</span>
            {q.sector && (
              <>
                <span className="text-xs">·</span>
                <Badge
                  asChild
                  className="bg-raised text-muted ring-1 ring-border hover:bg-saffron/10 hover:text-saffron hover:ring-saffron/30 transition-colors text-xs"
                >
                  <Link href={`/sector/${encodeURIComponent(q.sector)}`}>{q.sector}</Link>
                </Badge>
              </>
            )}
            {q.industry && q.industry !== q.sector && (
              <span className="hidden sm:inline text-muted/60 text-xs">{q.industry}</span>
            )}
          </div>
          <div className="mt-2 flex gap-2 flex-wrap">
            <Button variant="ghost" onClick={addToWatchlist} className="flex items-center gap-1.5 text-xs py-1.5 px-3">
              <Plus className="h-3.5 w-3.5" /> Watchlist
            </Button>
            {q.website && (
              <Button variant="ghost" asChild className="flex items-center gap-1.5 text-xs py-1.5 px-3">
                <a href={q.website} target="_blank" rel="noopener">
                  <ExternalLink className="h-3.5 w-3.5" /> <span className="hidden sm:inline">Website</span>
                </a>
              </Button>
            )}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="flex items-center justify-end gap-2">
            <div className="nums text-2xl sm:text-3xl md:text-4xl font-bold">{inr(displayPrice)}</div>
            {/* Live / SSE / Polling status dot */}
            {streamStatus === "live" && (
              <span className="flex items-center gap-1 text-[10px] font-bold text-up">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-up opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-up" />
                </span>
                LIVE
              </span>
            )}
            {streamStatus === "sse" && (
              <span className="text-[10px] font-bold text-saffron">SSE</span>
            )}
          </div>
          <div className={clsx("nums mt-1 text-sm sm:text-base font-semibold flex items-center justify-end gap-1", signCls(change))}>
            {(change ?? 0) >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
            {pct(change)} today
          </div>
          {q.previous_close && (
            <p className="mt-0.5 text-xs text-muted">Prev {inr(q.previous_close)}</p>
          )}
          {(streamStatus === "offline" || streamStatus === "polling") && q.fetched_at && (
            <p className="mt-0.5 text-[10px] text-muted/60">
              As of {Math.round((Date.now() / 1000 - q.fetched_at) / 60)} min ago
            </p>
          )}
        </div>
      </div>

      {/* ── Left col (About + Chart) + Right col (all financials) ── */}
      <div className="grid gap-4 lg:grid-cols-5">

        {/* LEFT: About + Chart stacked — same width */}
        <div className="flex flex-col gap-4 lg:col-span-3">

          {/* About company */}
          {q.summary && (
            <Card className="p-5">
              <Label className="mb-2 block">About</Label>
              <AboutParagraph text={q.summary} />
              {q.officers?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-border pt-3">
                  {q.officers.slice(0, 3).map((o: { name: string; title: string }) => (
                    <span key={o.name} className="text-xs text-muted">
                      <span className="font-semibold text-fg">{o.name}</span>{" "}
                      <span className="text-muted/60">· {o.title}</span>
                    </span>
                  ))}
                </div>
              )}
            </Card>
          )}

          {/* Chart card — Price / Volume tabs */}
          <ChartCard color={up ? "#1FC77D" : "#F0454B"}>
            {/* Tab row — stacks on mobile */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-border px-4 sm:px-5 pt-3 pb-0 gap-1 sm:gap-0">
              <div className="flex gap-0">
                {(["price", "volume"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setChartTab(t)}
                    className={clsx(
                      "flex items-center gap-1.5 border-b-2 px-3 sm:px-4 pb-3 pt-1 text-sm font-medium capitalize transition-all duration-200",
                      chartTab === t
                        ? "border-saffron text-saffron"
                        : "border-transparent text-muted hover:text-fg"
                    )}
                  >
                    {t === "price" ? "Price Chart" : "Volume Chart"}
                  </button>
                ))}
              </div>
              {/* Period selector — scrollable row on mobile */}
              <div className="flex items-center gap-1 rounded-lg bg-raised p-1 self-start sm:self-auto mb-2 sm:mb-0 overflow-x-auto scrollbar-none max-w-full">
                {PERIODS.map((p) => (
                  <button
                    key={p.value}
                    onClick={() => setPeriod(p.value)}
                    className={clsx("seg shrink-0", period === p.value ? "seg-on" : "seg-off")}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Subtitle row */}
            <div className="flex items-center gap-2 px-5 py-2 border-b border-border/50">
              {chartTab === "price" ? (
                <>
                  <span className="font-semibold text-sm">{q.company_name}</span>
                  <span className={clsx("nums text-sm font-semibold", signCls(hist?.pct_change))}>
                    {pct(hist?.pct_change)} · {periodLabel}
                  </span>
                </>
              ) : (
                <>
                  <span className="font-semibold text-sm">Volume Chart</span>
                  <span className="text-xs text-muted">Red bar = 2× avg volume spike</span>
                </>
              )}
            </div>

            {/* Chart panel — crossfade both charts stay mounted */}
            <div className="px-2 pb-3 pt-3">
              {histLoading ? (
                <div className="skeleton h-80 w-full rounded-lg" />
              ) : (
                <div className="relative" style={{ minHeight: "336px" }}>
                  <div
                    style={{
                      position: "absolute", top: 0, left: 0, right: 0,
                      opacity: chartTab === "price" ? 1 : 0,
                      transform: chartTab === "price" ? "scale(1) translateY(0)" : "scale(0.97) translateY(8px)",
                      transition: "opacity 0.35s cubic-bezier(0.4,0,0.2,1), transform 0.35s cubic-bezier(0.4,0,0.2,1)",
                      pointerEvents: chartTab === "price" ? "auto" : "none",
                    }}
                  >
                    <PriceChart candles={hist?.candles || []} up={up} />
                  </div>
                  <div
                    style={{
                      position: "absolute", top: 0, left: 0, right: 0,
                      opacity: chartTab === "volume" ? 1 : 0,
                      transform: chartTab === "volume" ? "scale(1) translateY(0)" : "scale(0.97) translateY(-8px)",
                      transition: "opacity 0.35s cubic-bezier(0.4,0,0.2,1), transform 0.35s cubic-bezier(0.4,0,0.2,1)",
                      pointerEvents: chartTab === "volume" ? "auto" : "none",
                    }}
                  >
                    <VolumeChart candles={hist?.candles || []} />
                  </div>
                </div>
              )}
            </div>
          </ChartCard>
        </div>

        {/* RIGHT: All financial numbers in a 2-column compact grid */}
        <Card className="overflow-hidden lg:col-span-2">
          <div className="border-b border-border bg-raised/40 px-4 py-3">
            <h2 className="text-sm font-semibold">Financial Overview</h2>
          </div>
          <div className="overflow-y-auto" style={{ maxHeight: "calc(100% - 44px)" }}>
            <div className="grid grid-cols-2 sm:grid-cols-2 divide-x divide-border">
              {[
                { label: "Market Cap",      value: inrCompact(q.market_cap) },
                { label: "P/E (TTM)",       value: num(q.pe_ratio) },
                { label: "Forward P/E",     value: q.forward_pe != null ? num(q.forward_pe) : "—" },
                { label: "P/B",             value: num(q.pb_ratio) },
                { label: "EPS (TTM)",       value: q.eps != null ? inr(q.eps) : "—" },
                { label: "Book Value",      value: q.book_value != null ? inr(q.book_value) : "—" },
                { label: "ROE",             value: q.roe != null ? `${(q.roe * 100).toFixed(1)}%` : "—",
                  color: q.roe != null ? (q.roe > 0.15 ? "text-up" : q.roe < 0 ? "text-down" : "") : "" },
                { label: "Net Margin",      value: q.profit_margin != null ? `${(q.profit_margin * 100).toFixed(1)}%` : "—",
                  color: q.profit_margin != null ? (q.profit_margin > 0 ? "text-up" : "text-down") : "" },
                { label: "Rev Growth",      value: q.revenue_growth != null ? `${q.revenue_growth >= 0 ? "+" : ""}${(q.revenue_growth * 100).toFixed(1)}%` : "—",
                  color: q.revenue_growth != null ? (q.revenue_growth >= 0 ? "text-up" : "text-down") : "" },
                { label: "EPS Growth",      value: q.earnings_growth != null ? `${q.earnings_growth >= 0 ? "+" : ""}${(q.earnings_growth * 100).toFixed(1)}%` : "—",
                  color: q.earnings_growth != null ? (q.earnings_growth >= 0 ? "text-up" : "text-down") : "" },
                { label: "D/E Ratio",       value: q.debt_to_equity != null ? num(q.debt_to_equity) : "—" },
                { label: "Div Yield",       value: q.dividend_yield != null ? `${(q.dividend_yield * 100).toFixed(2)}%` : "—" },
                { label: "52W High",        value: inr(q.week52_high) },
                { label: "52W Low",         value: inr(q.week52_low) },
                { label: "Day High",        value: inr(q.day_high) },
                { label: "Day Low",         value: inr(q.day_low) },
                { label: "Open",            value: inr(q.open) },
                { label: "Avg Volume",      value: q.avg_volume != null ? `${(q.avg_volume / 1e6).toFixed(1)}M` : "—" },
                { label: "RSI (14)",        value: num(hist?.latest_rsi, 0) },
                { label: "Beta",            value: q.beta != null ? num(q.beta) : "—" },
                { label: "Volatility",      value: hist?.volatility_pct != null ? `${hist.volatility_pct}%` : "—" },
                { label: "Promoter %",      value: q.held_by_insiders_pct != null ? `${(q.held_by_insiders_pct * 100).toFixed(1)}%` : "—" },
                { label: "FII / Inst %",    value: q.held_by_institutions_pct != null ? `${(q.held_by_institutions_pct * 100).toFixed(1)}%` : "—" },
                { label: "Float Shares",    value: q.float_shares != null ? inrCompact(q.float_shares) : "—" },
                { label: "Short Ratio",     value: q.short_ratio != null ? num(q.short_ratio) : "—" },
              ].map((m, idx) => (
                <div
                  key={m.label}
                  className={clsx(
                    "flex flex-col gap-0.5 px-3 sm:px-4 py-2.5 transition-colors hover:bg-raised/50",
                    idx >= 2 && "border-t border-border"
                  )}
                >
                  <Label className="text-[10px]">{m.label}</Label>
                  <span className={clsx("nums text-xs sm:text-sm font-bold leading-tight", m.color ?? "text-fg")}>{m.value}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      {/* ── Valuation Charts + Shareholding ── */}
      <div className="grid gap-4 lg:grid-cols-5">

        {/* PE / PB chart — left 3 cols */}
        <ChartCard color="#3b82f6" className="lg:col-span-3">
          {/* Tab header */}
          <div className="flex items-center justify-between border-b border-border px-5 pt-3 pb-0">
            <div className="flex gap-0">
              {(["pe", "pb"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setValuationTab(t)}
                  className={clsx(
                    "flex items-center gap-1.5 border-b-2 px-4 pb-3 pt-1 text-sm font-medium transition-all duration-200",
                    valuationTab === t
                      ? "border-blue-500 text-blue-500"
                      : "border-transparent text-muted hover:text-fg"
                  )}
                >
                  {t === "pe" ? "PE Ratio" : "PB Ratio"}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1 rounded-lg bg-raised p-1">
              {PERIODS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPeriod(p.value)}
                  className={clsx("seg", period === p.value ? "seg-on" : "seg-off")}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Subtitle */}
          <div className="flex items-center gap-3 border-b border-border/50 px-5 py-2">
            {valuationTab === "pe" && q.pe_ratio != null && (
              <span className="nums text-sm text-blue-500 font-semibold">
                Current P/E: {q.pe_ratio.toFixed(1)}×
              </span>
            )}
            {valuationTab === "pb" && q.pb_ratio != null && (
              <span className="nums text-sm text-blue-500 font-semibold">
                Current P/B: {q.pb_ratio.toFixed(2)}×
              </span>
            )}
            <span className="text-xs text-muted ml-auto">
              price ÷ {valuationTab === "pe" ? "EPS (TTM)" : "Book Value"}
            </span>
          </div>

          {/* Chart — crossfade, reduced height */}
          <div className="px-2 pb-3 pt-3">
            {histLoading ? (
              <div className="skeleton h-48 w-full rounded-lg" />
            ) : (
              <div className="relative h-48">
                <div style={{
                  position: "absolute", inset: 0,
                  opacity: valuationTab === "pe" ? 1 : 0,
                  transform: valuationTab === "pe" ? "scale(1) translateY(0)" : "scale(0.97) translateY(8px)",
                  transition: "opacity 0.35s cubic-bezier(0.4,0,0.2,1), transform 0.35s cubic-bezier(0.4,0,0.2,1)",
                  pointerEvents: valuationTab === "pe" ? "auto" : "none",
                }}>
                  <ValuationChart candles={hist?.candles || []} divisor={q.eps} label="P/E" color="#3b82f6" />
                </div>
                <div style={{
                  position: "absolute", inset: 0,
                  opacity: valuationTab === "pb" ? 1 : 0,
                  transform: valuationTab === "pb" ? "scale(1) translateY(0)" : "scale(0.97) translateY(-8px)",
                  transition: "opacity 0.35s cubic-bezier(0.4,0,0.2,1), transform 0.35s cubic-bezier(0.4,0,0.2,1)",
                  pointerEvents: valuationTab === "pb" ? "auto" : "none",
                }}>
                  <ValuationChart candles={hist?.candles || []} divisor={q.book_value} label="P/B" color="#8b5cf6" />
                </div>
              </div>
            )}
          </div>
        </ChartCard>

        {/* Shareholding pie — right 2 cols */}
        <ChartCard color="#8b5cf6" className="lg:col-span-2">
          <div className="border-b border-border bg-raised/40 px-4 py-3">
            <h3 className="text-sm font-semibold">Shareholding Pattern</h3>
            <p className="text-[10px] text-muted mt-0.5">Quarterly history · hover to inspect</p>
          </div>
          <ShareholdingPie
            promoterPct={q.held_by_insiders_pct}
            institutionPct={q.held_by_institutions_pct}
            ticker={ticker}
          />
        </ChartCard>

      </div>

      {/* ── AI analysis + sidebar ── */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          {insLoading ? <div className="skeleton h-72 rounded-2xl" /> : <AIAnalysisCard ai={ai} />}
          {insLoading ? <div className="skeleton h-52 rounded-2xl" /> : <HealthCard health={ins?.health} />}
        </div>
        <div className="space-y-6">
          {insLoading ? <div className="skeleton h-48 rounded-2xl" /> : <ForecastCard forecast={ins?.forecast} />}
          <TechnicalsCard
            candles={hist?.candles ?? []}
            currentPrice={q.current_price}
            latestRsi={hist?.latest_rsi ?? null}
          />
        </div>
      </div>

      {/* ── Ratio signals ── */}
      {core.signals?.length > 0 && (
        <div>
          <div className="mb-3 flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-saffron" />
            <h2 className="font-display text-lg font-semibold">Ratio Signals</h2>
            <span className="text-xs text-muted">{core.signals.length} signals detected</span>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 stagger">
            {core.signals.map((s: RatioSignal, i: number) => (
              <SignalCard key={i} signal={s} />
            ))}
          </div>
        </div>
      )}

      {/* ── Analyst Targets + Forecasts ── */}
      {(analystTargets || analystForecasts) && (
        <div className="grid gap-4 lg:grid-cols-2">
          <AnalystTargetCard targets={analystTargets} currentPrice={q.current_price} />
          <AnalystForecastCard forecasts={analystForecasts} />
        </div>
      )}

      {/* ── Peer Comparison ── */}
      <PeerComparison ticker={symbol} selfName={q.company_name} selfData={q} />

      {/* ── Concall Summary ── */}
      <ConcallCard ticker={symbol} />

      {/* ── Announcements + Corporate Actions ── */}
      {(announcements?.length > 0 || corpActions?.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          <AnnouncementsCard items={announcements ?? []} />
          <CorporateActionsCard items={corpActions ?? []} />
        </div>
      )}

      {/* ── News + Sentiment ── */}
      {insLoading
        ? <div className="skeleton h-40 rounded-2xl" />
        : <SplitNewsCard articles={ins?.news ?? []} sentiment={ins?.sentiment ?? {}} />
      }

      {/* ── Ask AI (full width, bottom) ── */}
      <AskAI ticker={symbol} />
    </div>
  );
}

type RatioSignal = {
  title: string;
  detail: string;
  type: "positive" | "negative" | "warning";
  metric: string;
  severity: "high" | "medium" | "low";
};

function SignalCard({ signal }: { signal: RatioSignal }) {
  const styles = {
    positive: {
      border: "border-up/25",
      bg: "bg-up/5 hover:bg-up/10",
      icon: <CheckCircle2 className="h-4 w-4 text-up shrink-0 mt-0.5" />,
      pill: "bg-up/10 text-up ring-up/20",
      titleColor: "text-up",
    },
    negative: {
      border: "border-down/25",
      bg: "bg-down/5 hover:bg-down/10",
      icon: signal.severity === "high"
        ? <AlertCircle className="h-4 w-4 text-down shrink-0 mt-0.5" />
        : <AlertTriangle className="h-4 w-4 text-down shrink-0 mt-0.5" />,
      pill: "bg-down/10 text-down ring-down/20",
      titleColor: "text-down",
    },
    warning: {
      border: "border-saffron/25",
      bg: "bg-saffron/5 hover:bg-saffron/10",
      icon: <Info className="h-4 w-4 text-saffron shrink-0 mt-0.5" />,
      pill: "bg-saffron/10 text-saffron ring-saffron/20",
      titleColor: "text-saffron",
    },
  }[signal.type];

  return (
    <div className={clsx(
      "flex flex-col gap-2.5 rounded-xl border p-4 transition-all duration-200 cursor-default",
      "hover:-translate-y-0.5 hover:shadow-md",
      styles.border,
      styles.bg
    )}>
      <div className="flex items-start gap-2">
        {styles.icon}
        <p className={clsx("text-sm font-semibold leading-snug", styles.titleColor)}>{signal.title}</p>
      </div>
      <p className="text-xs leading-relaxed text-fg/75">{signal.detail}</p>
      <div className="mt-auto flex items-center justify-between gap-2">
        <Badge className={clsx("ring-1 text-[10px] font-bold", styles.pill)}>
          {signal.metric}
        </Badge>
        {signal.severity === "high" && (
          <span className="text-[10px] font-bold uppercase tracking-wider text-muted/60">HIGH</span>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4 cursor-default select-none transition-all duration-200 hover:-translate-y-0.5 hover:border-[rgba(21,128,61,0.22)] hover:shadow-[var(--shadow-md),var(--shadow-glow)]">
      <Label className="block">{label}</Label>
      <p className="nums mt-1.5 text-lg font-bold">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
    </Card>
  );
}

function Section({ label, text }: { label: string; text?: string }) {
  if (!text) return null;
  return (
    <div>
      <Label className="mb-1 block">{label}</Label>
      <p className="text-sm leading-relaxed text-fg/90">{text}</p>
    </div>
  );
}

const SIGNAL_STYLE: Record<string, string> = {
  good:    "text-up ring-up/30 bg-up/10",
  warn:    "text-saffron ring-saffron/30 bg-saffron/10",
  bad:     "text-down ring-down/30 bg-down/10",
  neutral: "text-muted ring-border bg-raised",
};
const GRADE_COLOR: Record<string, string> = {
  A: "text-up bg-up/10 ring-up/30",
  B: "text-emerald-400 bg-emerald-400/10 ring-emerald-400/30",
  C: "text-saffron bg-saffron/10 ring-saffron/30",
  D: "text-orange-400 bg-orange-400/10 ring-orange-400/30",
  F: "text-down bg-down/10 ring-down/30",
};
const VERDICT_COLOR: Record<string, string> = {
  "Undervalued":   "text-up ring-up/30 bg-up/10",
  "Fairly valued": "text-saffron ring-saffron/30 bg-saffron/10",
  "Overvalued":    "text-down ring-down/30 bg-down/10",
  "Mixed":         "text-muted ring-border bg-raised",
};

type AiMetric = {
  label: string;
  value: string;
  context: string;
  signal: "good" | "warn" | "bad" | "neutral";
  explanation: string;
};

function AIAnalysisCard({ ai }: { ai: Record<string, any> }) {
  const verdictStyle = VERDICT_COLOR[ai.verdict] ?? "text-muted ring-border bg-raised";
  const gradeStyle   = GRADE_COLOR[ai.valuation_grade] ?? "text-muted ring-border bg-raised";

  if (ai.error) {
    return (
      <Card className="p-5">
        <h2 className="font-semibold mb-3">AI Analysis</h2>
        <p className="text-sm text-muted">{ai.error}</p>
      </Card>
    );
  }

  const hasRichData = ai.key_metrics?.length > 0 || ai.bull_case || ai.what_to_watch?.length > 0;

  return (
    <Card className="p-5 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">AI Analysis</h2>
          {ai.plain_summary && (
            <p className="mt-1.5 text-sm leading-relaxed text-fg/80">{ai.plain_summary}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {ai.valuation_grade && (
            <Badge className={`ring-1 text-xs font-bold ${gradeStyle}`}>Grade {ai.valuation_grade}</Badge>
          )}
          {ai.verdict && (
            <Badge className={`ring-1 text-xs ${verdictStyle}`}>{ai.verdict}</Badge>
          )}
        </div>
      </div>

      {/* Verdict reason */}
      {ai.verdict_reason && (
        <div className="flex items-start gap-2 rounded-lg border border-border bg-raised/40 px-3.5 py-3">
          <Zap className="mt-0.5 h-4 w-4 shrink-0 text-saffron" />
          <p className="text-sm font-medium text-fg/90">{ai.verdict_reason}</p>
        </div>
      )}

      {/* Key metrics grid */}
      {ai.key_metrics?.length > 0 && (
        <div>
          <Label className="mb-3 block">Key Metrics at a Glance</Label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(ai.key_metrics as AiMetric[]).map((m) => (
              <div
                key={m.label}
                className={`rounded-xl border px-3 py-2.5 ring-1 ${SIGNAL_STYLE[m.signal] ?? SIGNAL_STYLE.neutral}`}
              >
                <p className="text-[10px] font-semibold uppercase tracking-wider opacity-70">{m.label}</p>
                <p className="nums mt-0.5 text-base font-bold">{m.value}</p>
                <p className="mt-0.5 text-[10px] opacity-60">{m.context}</p>
                <p className="mt-1.5 text-[11px] leading-snug opacity-80">{m.explanation}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Valuation deep-dive */}
      <Section label="Valuation Deep-Dive" text={ai.valuation} />

      {/* Risks & Positives */}
      {(ai.risks?.length > 0 || ai.positives?.length > 0) && (
        <div className="grid gap-4 sm:grid-cols-2">
          {ai.risks?.length > 0 && (
            <div>
              <Label className="mb-2 flex items-center gap-1.5 text-down">
                <AlertTriangle className="h-3.5 w-3.5" /> Risks
              </Label>
              <ul className="space-y-2">
                {(ai.risks as string[]).map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-fg/80">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-down/60" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {ai.positives?.length > 0 && (
            <div>
              <Label className="mb-2 flex items-center gap-1.5 text-up">
                <CheckCircle2 className="h-3.5 w-3.5" /> Positives
              </Label>
              <ul className="space-y-2">
                {(ai.positives as string[]).map((p, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-fg/80">
                    <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-up/60" />
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Bull / Bear case */}
      {(ai.bull_case || ai.bear_case) && (
        <div className="grid gap-3 sm:grid-cols-2">
          {ai.bull_case && (
            <div className="rounded-xl border border-up/20 bg-up/5 p-3.5">
              <Label className="mb-1.5 flex items-center gap-1.5 text-up">
                <TrendingUp className="h-3.5 w-3.5" /> Bull Case
              </Label>
              <p className="text-sm leading-relaxed text-fg/85">{ai.bull_case}</p>
            </div>
          )}
          {ai.bear_case && (
            <div className="rounded-xl border border-down/20 bg-down/5 p-3.5">
              <Label className="mb-1.5 flex items-center gap-1.5 text-down">
                <TrendingDown className="h-3.5 w-3.5" /> Bear Case
              </Label>
              <p className="text-sm leading-relaxed text-fg/85">{ai.bear_case}</p>
            </div>
          )}
        </div>
      )}

      {/* Outlook */}
      <Section label="Near-Term Outlook" text={ai.outlook} />

      {/* What to watch */}
      {ai.what_to_watch?.length > 0 && (
        <div>
          <Label className="mb-2 flex items-center gap-1.5">
            <Eye className="h-3.5 w-3.5 text-saffron" /> What to Watch
          </Label>
          <ul className="space-y-2">
            {(ai.what_to_watch as string[]).map((w, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-fg/80">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-saffron/60" />
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!hasRichData && !ai.plain_summary && (
        <div className="space-y-4">
          <Section label="Valuation" text={ai.valuation} />
          <Section label="Risks" text={ai.risks} />
          <Section label="Outlook" text={ai.outlook} />
        </div>
      )}
    </Card>
  );
}

function AboutParagraph({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const LIMIT = 280;
  const short = text.length > LIMIT && !expanded;
  return (
    <div>
      <p className="text-sm leading-relaxed text-fg/85">
        {short ? text.slice(0, LIMIT) + "…" : text}
      </p>
      {text.length > LIMIT && (
        <button
          onClick={() => setExpanded((e) => !e)}
          className="mt-1.5 text-xs font-medium text-saffron hover:underline"
        >
          {expanded ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}

/* SentimentCard removed — sentiment merged into SplitNewsCard */

function NewsSlider({
  articles,
  color,
}: {
  articles: any[];
  color: "up" | "down";
}) {
  const ref = useRef<HTMLDivElement>(null);

  function scroll(dir: "left" | "right") {
    if (!ref.current) return;
    ref.current.scrollBy({ left: dir === "left" ? -220 : 220, behavior: "smooth" });
  }

  if (articles.length === 0) {
    return (
      <p className="text-xs text-muted italic py-2">No headlines found.</p>
    );
  }

  const hoverCls = color === "up" ? "group-hover:text-up" : "group-hover:text-down";

  return (
    <div className="relative">
      {/* Left arrow */}
      <button
        onClick={() => scroll("left")}
        className="absolute -left-2 top-1/2 z-10 -translate-y-1/2 grid h-6 w-6 place-items-center rounded-full bg-surface border border-border shadow-sm text-muted hover:text-fg transition"
        aria-label="Scroll left"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
      </button>

      {/* Slider track */}
      <div
        ref={ref}
        className="flex gap-2.5 overflow-x-auto scroll-smooth px-4"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        {articles.map((a: any, i: number) => (
          <a
            key={i}
            href={a.link}
            target="_blank"
            rel="noopener"
            className="group flex w-52 shrink-0 flex-col justify-between rounded-xl border border-border bg-raised p-3 transition hover:border-current hover:shadow-sm"
            style={{ minHeight: "100px" }}
          >
            <p className={`text-xs font-medium leading-snug text-fg/90 ${hoverCls} line-clamp-3`}>
              {a.title}
            </p>
            <div className="mt-2 flex items-center justify-between gap-1">
              <span className="truncate text-[10px] text-muted">{a.publisher}</span>
              {a.date && (
                <span className="shrink-0 text-[10px] text-muted">{a.date}</span>
              )}
            </div>
          </a>
        ))}
      </div>

      {/* Right arrow */}
      <button
        onClick={() => scroll("right")}
        className="absolute -right-2 top-1/2 z-10 -translate-y-1/2 grid h-6 w-6 place-items-center rounded-full bg-surface border border-border shadow-sm text-muted hover:text-fg transition"
        aria-label="Scroll right"
      >
        <ChevronRight className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

function SplitNewsCard({ articles, sentiment }: { articles: any[]; sentiment: any }) {
  const positive = (articles ?? []).filter((a) => (a.sentiment ?? 0) >= 0.05);
  const negative = (articles ?? []).filter((a) => (a.sentiment ?? 0) <= -0.05);

  const sentColor =
    sentiment?.label === "Positive" ? "text-up" :
    sentiment?.label === "Negative" ? "text-down" : "text-saffron";

  return (
    <Card className="overflow-hidden">
      {/* Header with sentiment inline */}
      <div className="flex items-center justify-between border-b border-border bg-raised/40 px-5 py-3">
        <div className="flex items-center gap-2">
          <Newspaper className="h-4 w-4 text-muted" />
          <h3 className="font-semibold text-sm">News · last 1 year</h3>
          <span className="text-xs text-muted">
            {positive.length} positive · {negative.length} negative
          </span>
        </div>
        {sentiment?.label && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted">Sentiment</span>
            <span className={clsx("text-sm font-bold", sentColor)}>{sentiment.label}</span>
            <span className="flex gap-2 text-[10px]">
              <span className="text-up">▲{sentiment?.positive ?? 0}</span>
              <span className="text-down">▼{sentiment?.negative ?? 0}</span>
              <span className="text-muted">●{sentiment?.neutral ?? 0}</span>
            </span>
          </div>
        )}
      </div>

      <div className="space-y-5 p-5">
        {/* Positive */}
        <div>
          <div className="mb-2.5 flex items-center gap-1.5">
            <TrendingUp className="h-3.5 w-3.5 text-up" />
            <Label className="text-up">Positive ({positive.length})</Label>
          </div>
          <NewsSlider articles={positive} color="up" />
        </div>

        {/* Negative */}
        <div>
          <div className="mb-2.5 flex items-center gap-1.5">
            <TrendingDown className="h-3.5 w-3.5 text-down" />
            <Label className="text-down">Negative ({negative.length})</Label>
          </div>
          <NewsSlider articles={negative} color="down" />
        </div>
      </div>
    </Card>
  );
}

function AnalystTargetCard({ targets, currentPrice }: { targets: any; currentPrice: number | null }) {
  if (!targets) return null;

  const mean   = targets.mean_target   ?? targets.meanTarget   ?? targets.target_mean_price ?? null;
  const high   = targets.high_target   ?? targets.highTarget   ?? targets.target_high_price ?? null;
  const low    = targets.low_target    ?? targets.lowTarget    ?? targets.target_low_price  ?? null;
  const buy    = (targets.buy ?? 0) + (targets.strong_buy ?? targets.strongBuy ?? 0);
  const hold   = targets.hold ?? 0;
  const sell   = (targets.sell ?? 0) + (targets.strong_sell ?? targets.strongSell ?? 0);
  const total  = buy + hold + sell;
  const upside = mean && currentPrice ? ((mean - currentPrice) / currentPrice) * 100 : null;

  const buyW  = total ? Math.round((buy  / total) * 100) : 0;
  const holdW = total ? Math.round((hold / total) * 100) : 0;
  const sellW = total ? Math.round((sell / total) * 100) : 0;

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Target className="h-4 w-4 text-saffron" />
        <h3 className="font-semibold text-sm">Analyst Price Targets</h3>
        {total > 0 && <span className="text-xs text-muted ml-auto">{total} analyst{total !== 1 ? "s" : ""}</span>}
      </div>

      {mean && (
        <div className="flex items-baseline gap-3">
          <span className="nums text-2xl font-bold">{inr(mean)}</span>
          <span className="text-xs text-muted">mean target</span>
          {upside !== null && (
            <span className={clsx("nums ml-auto text-sm font-semibold flex items-center gap-0.5", upside >= 0 ? "text-up" : "text-down")}>
              <ArrowUpRight className={clsx("h-3.5 w-3.5", upside < 0 && "rotate-90")} />
              {upside >= 0 ? "+" : ""}{upside.toFixed(1)}% upside
            </span>
          )}
        </div>
      )}

      {(low || high) && (
        <div className="flex items-center gap-2 text-xs text-muted">
          <span className="text-down font-semibold">{inr(low)}</span>
          <div className="flex-1 h-1.5 rounded-full bg-border relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-r from-down via-saffron to-up rounded-full" />
            {mean && low && high && (high - low) > 0 && (
              <div
                className="absolute top-1/2 -translate-y-1/2 h-3 w-0.5 bg-fg rounded-full"
                style={{ left: `${((mean - low) / (high - low)) * 100}%` }}
              />
            )}
          </div>
          <span className="text-up font-semibold">{inr(high)}</span>
        </div>
      )}

      {total > 0 && (
        <div className="space-y-2">
          <div className="flex gap-1 h-2 rounded-full overflow-hidden">
            {buyW  > 0 && <div className="bg-up rounded-l-full"   style={{ width: `${buyW}%` }}  />}
            {holdW > 0 && <div className="bg-saffron"             style={{ width: `${holdW}%` }} />}
            {sellW > 0 && <div className="bg-down rounded-r-full" style={{ width: `${sellW}%` }} />}
          </div>
          <div className="flex gap-4 text-[10px]">
            <span className="flex items-center gap-1 text-up"><span className="h-2 w-2 rounded-full bg-up inline-block" /> Buy {buy}</span>
            <span className="flex items-center gap-1 text-saffron"><span className="h-2 w-2 rounded-full bg-saffron inline-block" /> Hold {hold}</span>
            <span className="flex items-center gap-1 text-down"><span className="h-2 w-2 rounded-full bg-down inline-block" /> Sell {sell}</span>
          </div>
        </div>
      )}
    </Card>
  );
}

function AnalystForecastCard({ forecasts }: { forecasts: any }) {
  if (!forecasts) return null;

  const periods: any[] = forecasts.periods ?? forecasts.data ?? (Array.isArray(forecasts) ? forecasts : []);
  if (periods.length === 0) return null;

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center gap-2">
        <TrendingUp className="h-4 w-4 text-blue-500" />
        <h3 className="font-semibold text-sm">Analyst Forecasts</h3>
        <span className="text-xs text-muted ml-auto">Revenue · EPS</span>
      </div>

      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-1.5 px-2 text-muted font-medium">Period</th>
              <th className="text-right py-1.5 px-2 text-muted font-medium">Revenue</th>
              <th className="text-right py-1.5 px-2 text-muted font-medium">EPS</th>
              <th className="text-right py-1.5 px-2 text-muted font-medium">Growth</th>
            </tr>
          </thead>
          <tbody>
            {periods.slice(0, 6).map((p: any, i: number) => {
              const growth = p.revenue_growth ?? p.growth ?? p.revenueGrowth ?? null;
              const rev    = p.revenue ?? p.revenue_estimate ?? null;
              const eps    = p.eps ?? p.eps_estimate ?? p.epsEstimate ?? null;
              const period = p.period ?? p.quarter ?? p.year ?? `Period ${i + 1}`;
              return (
                <tr key={i} className="border-b border-border/50 hover:bg-raised/50 transition-colors">
                  <td className="py-2 px-2 font-medium text-fg">{period}</td>
                  <td className="py-2 px-2 text-right nums">{rev ? inrCompact(rev) : "—"}</td>
                  <td className="py-2 px-2 text-right nums">{eps != null ? inr(eps) : "—"}</td>
                  <td className={clsx("py-2 px-2 text-right nums font-semibold",
                    growth != null ? (growth >= 0 ? "text-up" : "text-down") : "text-muted"
                  )}>
                    {growth != null ? `${growth >= 0 ? "+" : ""}${(growth * 100).toFixed(1)}%` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function AnnouncementsCard({ items }: { items: any[] }) {
  if (!items.length) return null;

  const typeColors: Record<string, string> = {
    "Board Meeting":    "bg-blue-500/10 text-blue-500 ring-blue-500/20",
    "Result":          "bg-up/10 text-up ring-up/20",
    "Dividend":        "bg-saffron/10 text-saffron ring-saffron/20",
    "AGM":             "bg-purple-500/10 text-purple-500 ring-purple-500/20",
    "Default":         "bg-raised text-muted ring-border",
  };

  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center gap-2">
        <Bell className="h-4 w-4 text-saffron" />
        <h3 className="font-semibold text-sm">Announcements</h3>
        <span className="text-xs text-muted ml-auto">{items.length} recent</span>
      </div>

      <div className="space-y-2">
        {items.slice(0, 6).map((a: any, i: number) => {
          const subject  = a.subject ?? a.headline ?? a.description ?? a.title ?? "—";
          const date     = a.date ?? a.timestamp ?? a.announcement_date ?? "";
          const type     = a.type ?? a.category ?? a.announcement_type ?? "";
          const typeStyle = typeColors[type] ?? typeColors["Default"];
          return (
            <div key={i} className="flex gap-2.5 items-start py-1.5 border-b border-border/50 last:border-0">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-fg/90 leading-snug line-clamp-2">{subject}</p>
                {date && (
                  <div className="flex items-center gap-1 mt-1">
                    <Calendar className="h-3 w-3 text-muted" />
                    <span className="text-[10px] text-muted">{date}</span>
                  </div>
                )}
              </div>
              {type && (
                <Badge className={clsx("ring-1 text-[10px] shrink-0 mt-0.5", typeStyle)}>{type}</Badge>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function CorporateActionsCard({ items }: { items: any[] }) {
  if (!items.length) return null;

  const typeColors: Record<string, string> = {
    "Dividend":  "bg-saffron/10 text-saffron ring-saffron/20",
    "Bonus":     "bg-up/10 text-up ring-up/20",
    "Split":     "bg-blue-500/10 text-blue-500 ring-blue-500/20",
    "Rights":    "bg-purple-500/10 text-purple-500 ring-purple-500/20",
    "Default":   "bg-raised text-muted ring-border",
  };

  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center gap-2">
        <Gift className="h-4 w-4 text-up" />
        <h3 className="font-semibold text-sm">Corporate Actions</h3>
        <span className="text-xs text-muted ml-auto">Dividends · Splits · Bonus</span>
      </div>

      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-1.5 px-2 text-muted font-medium">Date</th>
              <th className="text-left py-1.5 px-2 text-muted font-medium">Type</th>
              <th className="text-right py-1.5 px-2 text-muted font-medium">Details</th>
            </tr>
          </thead>
          <tbody>
            {items.slice(0, 8).map((a: any, i: number) => {
              const date    = a.date ?? a.ex_date ?? a.record_date ?? a.action_date ?? "";
              const type    = a.type ?? a.action_type ?? a.corporate_action_type ?? "Action";
              const details = a.details ?? a.amount ?? a.value ?? a.description ?? a.ratio ?? "—";
              const typeKey = Object.keys(typeColors).find(k => type?.toLowerCase().includes(k.toLowerCase())) ?? "Default";
              const typeStyle = typeColors[typeKey];
              return (
                <tr key={i} className="border-b border-border/50 hover:bg-raised/50 transition-colors last:border-0">
                  <td className="py-2 px-2 text-muted">{date || "—"}</td>
                  <td className="py-2 px-2">
                    <Badge className={clsx("ring-1 text-[10px]", typeStyle)}>{type}</Badge>
                  </td>
                  <td className="py-2 px-2 text-right nums font-medium">{String(details)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <div className="skeleton h-12 w-72" />
      <div className="skeleton h-[420px] w-full rounded-card" />
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="skeleton h-20 rounded-card" />
        ))}
      </div>
    </div>
  );
}

function ErrorState({ symbol }: { symbol: string }) {
  return (
    <Card className="p-8 text-center">
      <h2 className="font-display text-xl">Couldn't load {symbol}</h2>
      <p className="mt-2 text-sm text-muted">
        Yahoo Finance may be rate-limited, or this isn't a valid NSE/BSE symbol. Try again shortly.
      </p>
    </Card>
  );
}
