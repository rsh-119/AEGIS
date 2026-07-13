"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import clsx from "clsx";
import { fetcher, inr, pct, signCls } from "@/lib/api";
import { Card } from "@/components/ui/card";
import {
  TrendingUp, TrendingDown, Info, ChevronDown, AlertTriangle,
  Sparkles, ExternalLink, Newspaper, Send,
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import { post } from "@/lib/api";

type BucketHolding = { ticker: string; name: string; value: number; pnl_pct: number };

type Bucket = {
  label: string;
  count: number;
  value: number;
  invested: number;
  pnl: number;
  pnl_pct: number;
  alloc_pct: number;
  holdings: BucketHolding[];
};

type NewsItem = {
  ticker: string;
  company: string;
  price: number | null;
  change_pct: number | null;
  title: string;
  url: string;
  source: string;
  date: string | null;
};

type Signal = { kind: "warning" | "info" | "positive"; metric?: string; title: string; detail: string };
type AiObservation = { severity: "risk" | "opportunity" | "neutral"; title: string; insight?: string; action: string };
type AiReview = { verdict: string | null; observations: AiObservation[] };
type GrowthPoint = { date: string; invested: number; value: number; nifty: number };
type AskExchange = { q: string; a: string };

type Analysis = {
  empty: boolean;
  growth: GrowthPoint[];
  summary: { invested: number; value: number; pnl: number; pnl_pct: number; count: number };
  xirr_pct: number | null;
  nifty_xirr_pct: number | null;
  outperformance_pct: number | null;
  cap_buckets: Bucket[];
  sector_buckets: Bucket[];
  as_of: string;
};

/* Categorical palette for donut segments — decorative N-color set, deliberately
   independent of the brand token (same precedent as StockLogo's palette). */
const SEG_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6", "#f43f5e", "#a3a3a3"];

function polarXY(cx: number, cy: number, r: number, deg: number) {
  const rad = (deg - 90) * (Math.PI / 180);
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, rOuter: number, rInner: number, a1: number, a2: number) {
  const so = polarXY(cx, cy, rOuter, a1);
  const eo = polarXY(cx, cy, rOuter, a2);
  const si = polarXY(cx, cy, rInner, a2);
  const ei = polarXY(cx, cy, rInner, a1);
  const large = a2 - a1 > 180 ? 1 : 0;
  return [
    `M${so.x},${so.y}`,
    `A${rOuter},${rOuter} 0 ${large} 1 ${eo.x},${eo.y}`,
    `L${si.x},${si.y}`,
    `A${rInner},${rInner} 0 ${large} 0 ${ei.x},${ei.y}`,
    "Z",
  ].join(" ");
}

function Donut({ buckets, hovered, setHovered }: {
  buckets: Bucket[];
  hovered: number | null;
  setHovered: (i: number | null) => void;
}) {
  const CX = 80, CY = 80, RO = 72, RI = 44;
  let angle = 0;

  // A single ~100% bucket degenerates as an arc path (start ≈ end point), so
  // draw it as a stroked ring instead.
  if (buckets.length === 1) {
    return (
      <svg width={160} height={160} viewBox="0 0 160 160" className="shrink-0" aria-hidden>
        <circle
          cx={CX} cy={CY} r={(RO + RI) / 2}
          fill="none"
          stroke={SEG_COLORS[0]}
          strokeWidth={RO - RI}
          opacity={hovered === null || hovered === 0 ? 1 : 0.35}
          onMouseEnter={() => setHovered(0)}
          onMouseLeave={() => setHovered(null)}
          className="cursor-pointer transition-opacity duration-200"
        />
      </svg>
    );
  }

  return (
    <svg width={160} height={160} viewBox="0 0 160 160" className="shrink-0" aria-hidden>
      {buckets.map((b, i) => {
        const sweep = Math.max((b.alloc_pct / 100) * 360, 0.5);
        const start = angle;
        angle += sweep;
        const gap = buckets.length > 1 ? 1.5 : 0;   // hairline gap between segments
        const isHov = hovered === i;
        const midRad = ((start + sweep / 2) - 90) * (Math.PI / 180);
        const dx = isHov ? Math.cos(midRad) * 4 : 0;
        const dy = isHov ? Math.sin(midRad) * 4 : 0;
        return (
          <path
            key={b.label}
            d={arcPath(CX, CY, RO, RI, start + gap / 2, start + sweep - gap / 2)}
            fill={SEG_COLORS[i % SEG_COLORS.length]}
            opacity={hovered === null || isHov ? 1 : 0.35}
            transform={`translate(${dx},${dy})`}
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}
            className="cursor-pointer transition-opacity duration-200"
          />
        );
      })}
    </svg>
  );
}

function AllocationCard({ title, buckets }: { title: string; buckets: Bucket[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  return (
    <Card className="p-5">
      <h3 className="font-semibold text-fg">{title}</h3>
      <div className="mt-4 flex flex-col items-center gap-5 sm:flex-row sm:items-start">
        <Donut buckets={buckets} hovered={hovered} setHovered={setHovered} />
        <div className="w-full min-w-0 flex-1 divide-y divide-border">
          {buckets.map((b, i) => (
            <div key={b.label}>
              <button
                onClick={() => setExpanded(expanded === i ? null : i)}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                aria-expanded={expanded === i}
                className={clsx(
                  "flex w-full items-center gap-3 py-2.5 text-left transition-colors",
                  hovered === i && "bg-raised/40",
                )}
              >
                <span
                  className="h-6 w-1 shrink-0 rounded-full"
                  style={{ backgroundColor: SEG_COLORS[i % SEG_COLORS.length]}}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-fg">{b.label}</p>
                  <p className="text-[11px] text-muted">{b.count} {b.count === 1 ? "stock" : "stocks"}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="nums text-sm text-fg">{inr(b.value)}</p>
                  <p className="nums text-[11px] text-muted">{b.alloc_pct.toFixed(1)}%</p>
                </div>
                <div className={clsx("nums w-14 shrink-0 text-right text-sm font-medium sm:w-20", signCls(b.pnl))}>
                  {pct(b.pnl_pct)}
                </div>
                <ChevronDown className={clsx(
                  "h-3.5 w-3.5 shrink-0 text-muted transition-transform duration-200",
                  expanded === i && "rotate-180",
                )} />
              </button>
              {/* Drill-down: the holdings inside this bucket, each linking out */}
              {expanded === i && (
                <div className="flex flex-wrap gap-2 pb-3 pl-4">
                  {b.holdings.map((h) => (
                    <Link
                      key={h.ticker}
                      href={`/stock/${encodeURIComponent(h.ticker)}`}
                      className="group flex items-center gap-2 rounded-full border border-border bg-raised/50 px-3 py-1.5 text-xs transition-all hover:border-saffron/50 hover:bg-saffron/8"
                    >
                      <span className="font-medium text-fg group-hover:text-saffron">{h.name}</span>
                      <span className={clsx("nums font-semibold", signCls(h.pnl_pct))}>{pct(h.pnl_pct)}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

export function AnalysisPanel() {
  const { data, isLoading } = useSWR<Analysis>("/api/portfolio/analysis", fetcher, {
    revalidateOnFocus: false,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
          <div className="skeleton h-44 rounded-2xl" />
          <div className="skeleton h-44 rounded-2xl" />
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="skeleton h-64 rounded-2xl" />
          <div className="skeleton h-64 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (!data || data.empty) {
    return (
      <Card className="p-10 text-center">
        <p className="text-sm text-muted">
          Add a holding first — analysis needs at least one stock in your portfolio.
        </p>
      </Card>
    );
  }

  const { summary, xirr_pct, nifty_xirr_pct, outperformance_pct } = data;
  const outperforming = (outperformance_pct ?? 0) >= 0;

  return (
    <div className="space-y-4">
      {/* XIRR vs Nifty hero */}
      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <Card className="p-6">
          {xirr_pct !== null ? (
            <>
              <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-saffron">True returns</p>
              <h3 className="mt-2 font-display text-2xl font-medium tracking-tight text-fg">
                {nifty_xirr_pct !== null && outperformance_pct !== null ? (
                  <>Portfolio is {outperforming ? "outperforming" : "trailing"} Nifty 50 by{" "}
                    <span className={outperforming ? "text-up" : "text-down"}>
                      {Math.abs(outperformance_pct).toFixed(2)}%
                    </span>
                  </>
                ) : (
                  "Your money-weighted return"
                )}
              </h3>
              <div className="mt-5 flex flex-wrap gap-8">
                <div>
                  <p className="text-xs text-muted">Portfolio XIRR</p>
                  <p className={clsx("nums mt-1 flex items-center gap-1 text-3xl font-semibold", signCls(xirr_pct))}>
                    {xirr_pct >= 0
                      ? <TrendingUp className="h-5 w-5" />
                      : <TrendingDown className="h-5 w-5" />}
                    {pct(xirr_pct)}
                  </p>
                </div>
                {nifty_xirr_pct !== null && (
                  <div>
                    <p className="text-xs text-muted">Nifty 50 (same cashflows)</p>
                    <p className={clsx("nums mt-1 text-3xl font-semibold", signCls(nifty_xirr_pct))}>
                      {pct(nifty_xirr_pct)}
                    </p>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-saffron">True returns</p>
              <h3 className="mt-2 font-display text-2xl font-medium tracking-tight text-fg">
                XIRR needs a little history
              </h3>
              <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
                Money-weighted returns become meaningful once your holdings are at least a
                day old. Check back tomorrow — total P&amp;L below is live already.
              </p>
            </>
          )}
        </Card>

        <Card className="flex flex-col justify-between p-6">
          <div className="grid grid-cols-2 gap-x-6 gap-y-5">
            <div>
              <p className="text-xs text-muted">Invested</p>
              <p className="nums mt-1 text-xl font-semibold text-fg">{inr(summary.invested)}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Current value</p>
              <p className="nums mt-1 text-xl font-semibold text-fg">{inr(summary.value)}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Total returns</p>
              <p className={clsx("nums mt-1 text-xl font-semibold", signCls(summary.pnl))}>
                {inr(summary.pnl)} <span className="text-sm">({pct(summary.pnl_pct)})</span>
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Holdings</p>
              <p className="nums mt-1 text-xl font-semibold text-fg">{summary.count}</p>
            </div>
          </div>
          <p className="mt-4 flex items-start gap-1.5 text-[11px] leading-relaxed text-muted">
            <Info className="mt-0.5 h-3 w-3 shrink-0" />
            XIRR factors in every buy and its date — your true annualised return.
            The Nifty figure invests the same rupees on the same dates into the index.
          </p>
        </Card>
      </div>

      {/* Growth vs Nifty */}
      {data.growth && data.growth.length > 2 && <GrowthChart points={data.growth} />}

      {/* Aegis Intelligence — decision support */}
      <InsightsCard />

      {/* Allocations — rows expand to show the holdings inside each bucket */}
      <div className="grid gap-4 lg:grid-cols-2">
        <AllocationCard title="Market cap" buckets={data.cap_buckets} />
        <AllocationCard title="Sector allocation" buckets={data.sector_buckets} />
      </div>

      {/* News on your holdings */}
      <NewsCard />

      {/* Ask anything about this portfolio */}
      <AskPortfolioCard />

      <p className="text-right font-mono text-[10px] uppercase tracking-[0.14em] text-muted/60">
        As of {data.as_of} · computed from live quotes
      </p>
    </div>
  );
}

const SIGNAL_STYLE: Record<Signal["kind"], { icon: React.ElementType; cls: string }> = {
  warning:  { icon: AlertTriangle, cls: "text-accent bg-accent/10 ring-accent/20" },
  info:     { icon: Info,          cls: "text-saffron bg-saffron/10 ring-saffron/20" },
  positive: { icon: TrendingUp,    cls: "text-up bg-up/10 ring-up/20" },
};

const AI_STYLE: Record<AiObservation["severity"], { icon: React.ElementType; cls: string; label: string }> = {
  risk:        { icon: AlertTriangle, cls: "text-accent bg-accent/10 ring-accent/20",   label: "Risk" },
  opportunity: { icon: TrendingUp,    cls: "text-up bg-up/10 ring-up/20",               label: "Opportunity" },
  neutral:     { icon: Info,          cls: "text-saffron bg-saffron/10 ring-saffron/20", label: "Note" },
};

function InsightsCard() {
  const { data, isLoading } = useSWR<{ empty: boolean; signals: Signal[]; ai: AiReview | null }>(
    "/api/portfolio/insights", fetcher, { revalidateOnFocus: false },
  );
  const [aiReview, setAiReview] = useState<AiReview | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiBusy, setAiBusy] = useState(false);

  async function runAiReview() {
    setAiBusy(true);
    setAiError(null);
    try {
      const res = await fetcher("/api/portfolio/insights?ai=1");
      if (res.ai?.observations?.length > 0) {
        setAiReview(res.ai);
      } else {
        setAiError("The reviewer had nothing to add right now — try again later.");
      }
    } catch {
      setAiError("Couldn't reach the AI reviewer — please try again.");
    } finally {
      setAiBusy(false);
    }
  }

  if (isLoading) return <div className="skeleton h-48 rounded-2xl" />;
  if (!data || data.empty || data.signals.length === 0) return null;

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-saffron">Aegis Intelligence</p>
          <h3 className="mt-1 font-display text-xl font-medium tracking-tight text-fg">
            What your portfolio is telling you
          </h3>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(["warning", "positive", "info"] as const).map((kind) => {
              const n = data.signals.filter((sg) => sg.kind === kind).length;
              if (!n) return null;
              const S = SIGNAL_STYLE[kind];
              return (
                <span key={kind} className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.08em] ring-1", S.cls)}>
                  <S.icon className="h-2.5 w-2.5" />
                  {n} {kind === "warning" ? (n > 1 ? "risks" : "risk") : kind === "positive" ? (n > 1 ? "strengths" : "strength") : (n > 1 ? "notes" : "note")}
                </span>
              );
            })}
          </div>
        </div>
        <button
          onClick={runAiReview}
          disabled={aiBusy}
          className="flex items-center gap-1.5 rounded-full bg-fg px-4 py-2 text-xs font-semibold text-ink shadow-sm transition-all hover:-translate-y-0.5 disabled:opacity-60"
        >
          <Sparkles className="h-3.5 w-3.5" />
          {aiBusy ? "Reviewing…" : aiReview ? "Run again" : "Run AI review"}
        </button>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        {data.signals.map((sig, i) => {
          const S = SIGNAL_STYLE[sig.kind];
          return (
            <div
              key={i}
              className={clsx(
                "flex gap-3 rounded-xl border border-border border-l-2 bg-raised/30 p-4 transition-colors hover:bg-raised/50",
                sig.kind === "warning" && "border-l-accent/60",
                sig.kind === "positive" && "border-l-up/60",
                sig.kind === "info" && "border-l-saffron/60",
              )}
            >
              <span className={clsx("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ring-1", S.cls)}>
                <S.icon className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold leading-snug text-fg">{sig.title}</p>
                  {sig.metric && (
                    <span className={clsx("nums shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[10px] font-semibold ring-1", S.cls)}>
                      {sig.metric}
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">{sig.detail}</p>
              </div>
            </div>
          );
        })}
      </div>

      {(aiReview || aiError) && (
        <div className="mt-4 rounded-xl border border-saffron/20 bg-saffron/5 p-4 sm:p-5">
          <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-saffron">
            <Sparkles className="h-3 w-3" /> AI review
          </p>
          {aiError ? (
            <p className="mt-2 text-sm text-muted">{aiError}</p>
          ) : (
            <>
              {aiReview!.verdict && (
                <p className="mt-2.5 font-display text-lg font-medium leading-snug tracking-tight text-fg">
                  &ldquo;{aiReview!.verdict}&rdquo;
                </p>
              )}
              <div className={clsx(
                "mt-4 grid gap-3",
                aiReview!.observations.length >= 4 ? "sm:grid-cols-2" : "sm:grid-cols-3",
              )}>
                {aiReview!.observations.map((o, i) => {
                  const S = AI_STYLE[o.severity] ?? AI_STYLE.neutral;
                  return (
                    <div key={i} className="flex flex-col rounded-xl border border-border bg-surface p-4">
                      <span className={clsx(
                        "inline-flex w-fit items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.1em] ring-1",
                        S.cls,
                      )}>
                        <S.icon className="h-3 w-3" /> {S.label}
                      </span>
                      <p className="mt-2.5 text-sm font-semibold leading-snug text-fg">{o.title}</p>
                      {o.insight && (
                        <p className="mt-1.5 flex-1 text-xs leading-relaxed text-muted">{o.insight}</p>
                      )}
                      <p className="mt-3 border-t border-border pt-2.5 text-xs font-medium leading-relaxed text-fg">
                        <span className="text-saffron">→ </span>{o.action}
                      </p>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}

      <p className="mt-4 text-[11px] text-muted/70">
        Signals are rule-based checks on concentration, drawdowns and benchmark gaps; the AI
        review is a model&apos;s opinion. Neither is investment advice — always do your own research.
      </p>
    </Card>
  );
}

function NewsCard() {
  const { data, isLoading } = useSWR<{ items: NewsItem[] }>("/api/portfolio/news", fetcher, {
    revalidateOnFocus: false,
  });

  if (isLoading) return <div className="skeleton h-56 rounded-2xl" />;
  if (!data || data.items.length === 0) return null;

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border bg-raised/40 px-5 py-3.5">
        <Newspaper className="h-4 w-4 text-saffron" />
        <h3 className="text-sm font-semibold text-fg">News on your holdings</h3>
      </div>
      <div className="divide-y divide-border">
        {data.items.map((n, i) => (
          <div key={i} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 px-4 py-3.5 sm:gap-4 sm:px-5">
            <Link
              href={`/stock/${encodeURIComponent(n.ticker)}`}
              className="w-16 shrink-0 truncate font-mono text-xs font-semibold text-muted transition-colors hover:text-saffron sm:w-24"
              title={n.company}
            >
              {n.ticker.replace(/\.(NS|BO)$/, "")}
            </Link>
            {n.url ? (
              <a
                href={n.url}
                target="_blank"
                rel="noreferrer"
                className="group min-w-0"
              >
                <p className="truncate text-sm text-fg transition-colors group-hover:text-saffron sm:whitespace-normal sm:line-clamp-2">
                  {n.title}
                  <ExternalLink className="mb-0.5 ml-1.5 inline h-3 w-3 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                </p>
                <p className="mt-0.5 text-[11px] text-muted">
                  {[n.source, n.date].filter(Boolean).join(" · ")}
                </p>
              </a>
            ) : (
              <div className="min-w-0">
                <p className="truncate text-sm text-fg sm:whitespace-normal sm:line-clamp-2">{n.title}</p>
                <p className="mt-0.5 text-[11px] text-muted">{[n.source, n.date].filter(Boolean).join(" · ")}</p>
              </div>
            )}
            <div className="shrink-0 text-right">
              {n.price != null && <p className="nums text-sm font-semibold text-fg">₹{n.price.toLocaleString("en-IN")}</p>}
              {n.change_pct != null && (
                <p className={clsx("nums text-[11px] font-medium", signCls(n.change_pct))}>{pct(n.change_pct)}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

/* Line colors are fixed hexes (categorical, theme-safe in both modes) —
   same precedent as the donut palette. */
const LINE_PORTFOLIO = "#3b82f6";
const LINE_NIFTY = "#a3a3a3";

function fmtMonth(d: string) {
  const dt = new Date(d);
  return dt.toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
}

function GrowthChart({ points }: { points: GrowthPoint[] }) {
  const last = points[points.length - 1];
  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="font-semibold text-fg">Growth vs Nifty 50</h3>
        <div className="flex flex-wrap items-center gap-4 text-[11px] text-muted">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: LINE_PORTFOLIO }} />
            Your portfolio <span className="nums font-semibold text-fg">{inr(last.value)}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: LINE_NIFTY }} />
            Same money in Nifty <span className="nums font-semibold text-fg">{inr(last.nifty)}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 border-t border-dashed border-muted" />
            Invested <span className="nums font-semibold text-fg">{inr(last.invested)}</span>
          </span>
        </div>
      </div>
      <div className="mt-4 h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 6, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--color-border))" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={fmtMonth}
              tick={{ fontSize: 10, fill: "rgb(var(--color-muted))" }}
              tickLine={false}
              axisLine={{ stroke: "rgb(var(--color-border))" }}
              minTickGap={48}
            />
            <YAxis
              tickFormatter={(v: number) => `₹${(v / 1000).toFixed(0)}k`}
              tick={{ fontSize: 10, fill: "rgb(var(--color-muted))" }}
              tickLine={false}
              axisLine={false}
              width={52}
              domain={["auto", "auto"]}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as GrowthPoint;
                return (
                  <div className="rounded-xl border border-border bg-surface px-3 py-2 text-xs shadow-lg">
                    <p className="font-mono text-[10px] uppercase tracking-wide text-muted">{fmtMonth(String(label))}</p>
                    <p className="nums mt-1" style={{ color: LINE_PORTFOLIO }}>Portfolio {inr(p.value)}</p>
                    <p className="nums" style={{ color: LINE_NIFTY }}>Nifty {inr(p.nifty)}</p>
                    <p className="nums text-muted">Invested {inr(p.invested)}</p>
                  </div>
                );
              }}
            />
            <Line type="monotone" dataKey="invested" stroke="rgb(var(--color-muted))" strokeDasharray="4 4" strokeWidth={1} dot={false} />
            <Line type="monotone" dataKey="nifty" stroke={LINE_NIFTY} strokeWidth={1.5} dot={false} />
            <Line type="monotone" dataKey="value" stroke={LINE_PORTFOLIO} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-muted/70">
        Reconstructed from each holding&apos;s price history — positions enter the line on their
        buy date. The grey line puts the same rupees into the Nifty 50 on the same dates.
      </p>
    </Card>
  );
}

const STARTER_QUESTIONS = [
  "What's my biggest risk right now?",
  "Which stock is dragging my returns?",
  "How diversified am I really?",
];

function AskPortfolioCard() {
  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<AskExchange[]>([]);
  const [followups, setFollowups] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(q: string) {
    const trimmed = q.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setQuestion("");
    try {
      const res = await post<{ answer: string; followups: string[] }>("/api/portfolio/ask", { question: trimmed });
      setThread((t) => [...t, { q: trimmed, a: res.answer }]);
      setFollowups(res.followups || []);
    } catch {
      setThread((t) => [...t, { q: trimmed, a: "Something went wrong — please try again." }]);
      setFollowups([]);
    } finally {
      setBusy(false);
    }
  }

  const suggestions = followups.length > 0 ? followups : thread.length === 0 ? STARTER_QUESTIONS : [];

  return (
    <section className="relative overflow-hidden rounded-[2rem] border border-border bg-surface px-5 py-10 shadow-sm sm:px-10">
      {/* Light, airy: faint dot grid + a whisper of brand glow along the top */}
      <div className="panel-dots absolute inset-0 opacity-40" aria-hidden />
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-40"
        style={{ background: "radial-gradient(ellipse 65% 100% at 50% 0%, rgb(var(--color-saffron)/0.07), transparent 75%)" }}
        aria-hidden
      />

      <div className="relative mx-auto max-w-2xl">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-saffron">Ask Aegis</p>
        <h3 className="mt-2 font-display text-2xl font-medium tracking-tight text-fg sm:text-3xl">
          Ask anything about this portfolio.
        </h3>

        {/* Thread */}
        {thread.length > 0 && (
          <div className="mt-6 space-y-4">
            {thread.slice(-4).map((x, i) => (
              <div key={i} className="space-y-2">
                <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-saffron/10 px-4 py-2 text-sm text-fg">
                  {x.q}
                </p>
                <p className="w-fit max-w-[92%] rounded-2xl rounded-bl-sm border border-border bg-raised/60 px-4 py-2.5 text-sm leading-relaxed text-fg">
                  {x.a}
                </p>
              </div>
            ))}
            {busy && <p className="animate-pulse text-sm text-muted">Reading your portfolio…</p>}
          </div>
        )}

        {/* Input */}
        <form
          onSubmit={(e) => { e.preventDefault(); ask(question); }}
          className="mt-6 flex items-center gap-2 rounded-full border border-border bg-raised/50 p-1.5 pl-5 shadow-sm focus-within:border-saffron/60"
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={500}
            placeholder="e.g. Should I be worried about my sector concentration?"
            className="w-full bg-transparent text-sm text-fg outline-none placeholder:text-muted/70"
          />
          <button
            type="submit"
            disabled={busy || !question.trim()}
            aria-label="Ask"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-saffron text-white transition-all hover:-translate-y-0.5 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </form>

        {/* Suggestions / follow-ups */}
        {suggestions.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {suggestions.map((sq) => (
              <button
                key={sq}
                onClick={() => ask(sq)}
                disabled={busy}
                className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-muted transition-all hover:border-saffron/60 hover:text-saffron disabled:opacity-50"
              >
                {sq}
              </button>
            ))}
          </div>
        )}

        <p className="mt-4 text-[11px] text-muted/70">
          Answers are grounded in your live holdings snapshot. Not investment advice.
        </p>
      </div>
    </section>
  );
}
