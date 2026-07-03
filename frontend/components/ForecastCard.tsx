"use client";

import { useState } from "react";
import { inr, signCls } from "@/lib/api";
import { TrendingUp, TrendingDown, Minus, Activity, Cpu, Zap, BarChart2 } from "lucide-react";
import clsx from "clsx";

type Point     = { day: number; price: number; upper: number; lower: number };
type Milestone = { days: number; price: number; upper: number; lower: number; return_pct: number };
type SingleFc  = {
  available: boolean;
  reason?: string;
  model?: string;
  model_label?: string;
  last_price?: number;
  target_price?: number;
  expected_return_pct?: number;
  direction?: string;
  horizon_days?: number;
  daily_vol_pct?: number;
  annualised_trend_pct?: number;
  milestones?: Record<string, Milestone>;
  points?: Point[];
  disclaimer?: string;
};

// Analysis endpoint wraps forecasts as { holt, xgboost, lgbm }
// but the standalone /forecast endpoint returns a single object
type ForecastProp = SingleFc | { holt?: SingleFc; xgboost?: SingleFc; lgbm?: SingleFc };

function isBag(f: ForecastProp): f is { holt?: SingleFc; xgboost?: SingleFc; lgbm?: SingleFc } {
  return f != null && typeof f === "object" && ("holt" in f || "xgboost" in f || "lgbm" in f);
}

/* ─── Horizon tabs ───────────────────────────────── */
const HORIZONS = [
  { label: "1W", key: "1W", days: 7  },
  { label: "2W", key: "2W", days: 14 },
  { label: "3W", key: "3W", days: 21 },
  { label: "1M", key: "1M", days: 30 },
];

/* ─── Algo configs ───────────────────────────────── */
type AlgoKey = "holt" | "xgboost" | "lgbm";
const ALGOS: { key: AlgoKey; label: string; short: string; icon: React.ReactNode; color: string }[] = [
  {
    key: "holt", label: "Holt DES", short: "Statistical",
    icon: <BarChart2 className="h-3.5 w-3.5" />,
    color: "text-blue-500 bg-blue-500/10 ring-blue-500/30",
  },
  {
    key: "xgboost", label: "XGBoost", short: "Gradient Boost",
    icon: <Zap className="h-3.5 w-3.5" />,
    color: "text-orange-500 bg-orange-500/10 ring-orange-500/30",
  },
  {
    key: "lgbm", label: "LightGBM", short: "Leaf-wise Trees",
    icon: <Cpu className="h-3.5 w-3.5" />,
    color: "text-violet-500 bg-violet-500/10 ring-violet-500/30",
  },
];

/* ─── Mini forecast chart ────────────────────────── */
function MiniChart({ points, lastPrice, days, up }: {
  points: Point[]; lastPrice: number; days: number; up: boolean;
}) {
  const slice = points.slice(0, days);
  if (!slice.length) return null;

  const allBand = [lastPrice, ...slice.flatMap((p) => [p.upper, p.lower, p.price])];
  const mn = Math.min(...allBand);
  const mx = Math.max(...allBand);
  const rng = mx - mn || 1;

  const W = 320, H = 100;
  const px = (i: number) => (i / slice.length) * W;
  const py = (v: number) => H - ((v - mn) / rng) * (H - 10) - 5;

  const line = [`M0,${py(lastPrice)}`, ...slice.map((p, i) => `L${px(i + 1)},${py(p.price)}`)].join(" ");
  const bandTop = slice.map((p, i) => `${i === 0 ? `M${px(1)}` : `L${px(i + 1)}`},${py(p.upper)}`).join(" ");
  const bandBot = [...slice].reverse().map((_, ri) => {
    const i = slice.length - 1 - ri;
    return `L${px(i + 1)},${py(slice[i].lower)}`;
  }).join(" ");

  const stroke = up ? "#1FC77D" : "#F0454B";
  const fill   = up ? "rgba(31,199,125,0.12)" : "rgba(240,69,75,0.12)";
  const endPt  = slice[slice.length - 1];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-28 w-full">
      <path d={`${bandTop} ${bandBot} Z`} fill={fill} />
      <line x1={1} y1={0} x2={1} y2={H} stroke="rgba(128,128,128,0.4)"
        strokeWidth={0.8} strokeDasharray="3 2" />
      <path d={line} fill="none" stroke={stroke} strokeWidth={1.5}
        vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={px(slice.length)} cy={py(endPt.price)} r={3}
        fill={stroke} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/* ─── Single-algo view ───────────────────────────── */
function AlgoView({ fc, algoKey, horizon, setHorizon }: {
  fc: SingleFc; algoKey: AlgoKey;
  horizon: string; setHorizon: (h: string) => void;
}) {

  if (!fc.available) {
    return (
      <div className="px-5 py-8 text-center">
        <p className="text-sm text-muted">{fc.reason || "Forecast unavailable for this stock."}</p>
      </div>
    );
  }

  const algo  = ALGOS.find((a) => a.key === algoKey)!;
  const pts   = fc.points || [];
  const ms    = fc.milestones || {};
  const sel   = ms[horizon];
  const up    = (sel?.return_pct ?? fc.expected_return_pct ?? 0) >= 0;
  const days  = HORIZONS.find((h) => h.key === horizon)?.days ?? 30;

  const dirIcon = fc.direction === "up"
    ? <TrendingUp className="h-3.5 w-3.5 text-up" />
    : fc.direction === "down"
    ? <TrendingDown className="h-3.5 w-3.5 text-down" />
    : <Minus className="h-3.5 w-3.5 text-muted" />;

  return (
    <div className="animate-fade-up">
      {/* Horizon tabs */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-1.5 text-xs text-muted">
          {dirIcon}
          <span className={clsx("font-medium", up ? "text-up" : "text-down")}>
            {fc.direction === "flat" ? "Sideways" : fc.direction === "up" ? "Bullish" : "Bearish"}
          </span>
        </div>
        <div className="flex items-center gap-0.5 rounded-lg bg-raised p-0.5">
          {HORIZONS.map((h) => (
            <button
              key={h.key}
              onClick={() => setHorizon(h.key)}
              className={clsx(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                horizon === h.key ? "bg-surface text-fg shadow-sm" : "text-muted hover:text-fg"
              )}
            >
              {h.key}
            </button>
          ))}
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-3 divide-x divide-border border-b border-border">
        <div className="px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Current</p>
          <p className="nums mt-0.5 text-base font-bold text-fg">{inr(fc.last_price)}</p>
        </div>
        <div className="px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Target ({horizon})</p>
          <p className={clsx("nums mt-0.5 text-base font-bold", up ? "text-up" : "text-down")}>
            {inr(sel?.price ?? fc.target_price)}
          </p>
        </div>
        <div className="px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Expected</p>
          <p className={clsx("nums mt-0.5 text-base font-bold", up ? "text-up" : "text-down")}>
            {sel?.return_pct != null
              ? `${sel.return_pct >= 0 ? "+" : ""}${sel.return_pct.toFixed(2)}%`
              : "—"}
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="px-4 pt-3 pb-1">
        <MiniChart points={pts} lastPrice={fc.last_price!} days={days} up={up} />
        <div className="mt-1 flex items-center justify-between text-[10px] text-muted">
          <span>Today</span>
          <span>{HORIZONS.find((h) => h.key === horizon)?.label} ahead</span>
        </div>
      </div>

      {/* Confidence + vol */}
      {sel && (
        <div className="border-t border-border/60 grid grid-cols-2 divide-x divide-border/60">
          <div className="px-4 py-2.5">
            <p className="text-[10px] text-muted">80% Range</p>
            <p className="nums text-xs font-semibold mt-0.5">{inr(sel.lower)} – {inr(sel.upper)}</p>
          </div>
          <div className="px-4 py-2.5">
            <p className="text-[10px] text-muted">Daily Vol (EWMA)</p>
            <p className="nums text-xs font-semibold mt-0.5">
              {fc.daily_vol_pct != null ? `±${fc.daily_vol_pct.toFixed(2)}%` : "—"}
            </p>
          </div>
        </div>
      )}

      {/* All horizons quick-view */}
      <div className="border-t border-border/60 flex divide-x divide-border/60">
        {HORIZONS.map((h) => {
          const m = ms[h.key];
          if (!m) return null;
          const isUp  = m.return_pct >= 0;
          const isSel = h.key === horizon;
          return (
            <button
              key={h.key}
              onClick={() => setHorizon(h.key)}
              className={clsx(
                "flex-1 px-2 py-2 text-center transition-colors",
                isSel ? "bg-saffron/5" : "hover:bg-raised/40"
              )}
            >
              <p className={clsx("text-[10px] font-bold", isSel ? "text-saffron" : "text-muted")}>{h.key}</p>
              <p className={clsx("nums text-[11px] font-semibold mt-0.5", isUp ? "text-up" : "text-down")}>
                {m.return_pct >= 0 ? "+" : ""}{m.return_pct.toFixed(1)}%
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Main card ──────────────────────────────────── */
export function ForecastCard({ forecast: fc }: { forecast: ForecastProp | undefined | null }) {
  const [algo, setAlgo]       = useState<AlgoKey>("holt");
  const [horizon, setHorizon] = useState<string>("1M");

  if (!fc) return null;

  // Normalise: single forecast → treat as holt
  const bag: Record<AlgoKey, SingleFc | undefined> = isBag(fc)
    ? { holt: fc.holt, xgboost: fc.xgboost, lgbm: fc.lgbm }
    : { holt: fc as SingleFc, xgboost: undefined, lgbm: undefined };

  const activeFc = bag[algo];
  const activeAlgo = ALGOS.find((a) => a.key === algo)!;

  return (
    <div className="card overflow-hidden">
      {/* Header with algo switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-raised/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-saffron" />
          <div>
            <h3 className="text-sm font-semibold">Price Forecast</h3>
            <p className="text-[10px] text-muted">{activeAlgo.short}</p>
          </div>
        </div>

        {/* Algorithm toggle */}
        <div className="flex items-center gap-1">
          {ALGOS.map((a) => (
            <button
              key={a.key}
              onClick={() => setAlgo(a.key)}
              title={a.label}
              className={clsx(
                "flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold ring-1 transition-all",
                algo === a.key
                  ? a.color
                  : "text-muted ring-border hover:text-fg hover:bg-raised"
              )}
            >
              {a.icon}
              {a.label}
            </button>
          ))}
        </div>
      </div>

      {/* Per-algo view */}
      {activeFc ? (
        <AlgoView fc={activeFc} algoKey={algo} horizon={horizon} setHorizon={setHorizon} />
      ) : (
        <div className="px-5 py-8 text-center">
          <p className="text-sm text-muted">Loading {activeAlgo.label} forecast…</p>
        </div>
      )}

      <p className="border-t border-border/40 px-4 py-2 text-[10px] text-muted/70">
        {activeFc?.disclaimer ?? "Statistical projection only. Not investment advice."}
      </p>
    </div>
  );
}
