"use client";

import { useMemo } from "react";
import { inr } from "@/lib/api";
import clsx from "clsx";
import { Card } from "@/components/ui/card";

type Candle = {
  close: number;
  ma20?: number | null;
  ma50?: number | null;
  ma200?: number | null;
  rsi?: number | null;
};

type Signal = "Strong Buy" | "Buy" | "Neutral" | "Sell" | "Strong Sell";

interface Indicator {
  name: string;
  value: number | null;
  signal: Signal;
  group: "ma" | "osc";
}

// ── Helpers ──────────────────────────────────────────────────

function ema(prices: number[], period: number): number {
  if (prices.length < period) return prices[prices.length - 1] ?? 0;
  const k = 2 / (period + 1);
  let val = prices.slice(0, period).reduce((s, v) => s + v, 0) / period;
  for (let i = period; i < prices.length; i++) val = prices[i] * k + val * (1 - k);
  return val;
}

function macd(prices: number[]): { macd: number; signal: number; hist: number } {
  if (prices.length < 35) return { macd: 0, signal: 0, hist: 0 };
  const k12 = 2 / 13, k26 = 2 / 27, k9 = 2 / 10;
  let e12 = prices[0], e26 = prices[0];
  const macdLine: number[] = [];
  for (let i = 1; i < prices.length; i++) {
    e12 = prices[i] * k12 + e12 * (1 - k12);
    e26 = prices[i] * k26 + e26 * (1 - k26);
    macdLine.push(e12 - e26);
  }
  let sig = macdLine[0];
  for (let i = 1; i < macdLine.length; i++) sig = macdLine[i] * k9 + sig * (1 - k9);
  const m = macdLine[macdLine.length - 1];
  return { macd: m, signal: sig, hist: m - sig };
}

function bollinger(prices: number[], period = 20) {
  if (prices.length < period) return { upper: 0, mid: 0, lower: 0, pct: 50 };
  const slice = prices.slice(-period);
  const mid   = slice.reduce((s, v) => s + v, 0) / period;
  const std   = Math.sqrt(slice.reduce((s, v) => s + (v - mid) ** 2, 0) / period);
  const upper = mid + 2 * std;
  const lower = mid - 2 * std;
  const last  = prices[prices.length - 1];
  const pct   = upper === lower ? 50 : ((last - lower) / (upper - lower)) * 100;
  return { upper, mid, lower, pct };
}

function maSig(price: number, ma: number | null | undefined): Signal {
  if (!ma || !price) return "Neutral";
  const d = (price - ma) / ma;
  if (d > 0.03)  return "Strong Buy";
  if (d > 0)     return "Buy";
  if (d < -0.03) return "Strong Sell";
  if (d < 0)     return "Sell";
  return "Neutral";
}

function rsiSig(rsi: number): Signal {
  if (rsi < 25)  return "Strong Buy";
  if (rsi < 40)  return "Buy";
  if (rsi > 75)  return "Strong Sell";
  if (rsi > 60)  return "Sell";
  return "Neutral";
}

// ── Signal badge ─────────────────────────────────────────────

const SIG_CLS: Record<Signal, string> = {
  "Strong Buy":  "bg-up/15 text-up",
  "Buy":         "bg-up/15 text-up",
  "Neutral":     "bg-muted/15 text-muted",
  "Sell":        "bg-down/15 text-down",
  "Strong Sell": "bg-red-600/15 text-red-500",
};

function Badge({ signal }: { signal: Signal }) {
  return (
    <span className={clsx("rounded-md px-2 py-0.5 text-micro-cap font-bold", SIG_CLS[signal])}>
      {signal}
    </span>
  );
}

// ── RSI Gauge ────────────────────────────────────────────────

function RSIGauge({ rsi }: { rsi: number }) {
  const clamped = Math.max(0, Math.min(100, rsi));
  // Semi-circle: 0 = left, 100 = right (180° arc)
  const angle   = (clamped / 100) * 180 - 90; // -90° to +90°
  const rad     = (angle * Math.PI) / 180;
  const r       = 52, cx = 64, cy = 64;
  const nx      = cx + r * Math.cos(rad);
  const ny      = cy + r * Math.sin(rad);

  return (
    <div className="flex flex-col items-center">
      <svg width={128} height={72} viewBox="0 0 128 72">
        {/* Track zones */}
        {[
          { start: 180, end: 252, color: "#1FC77D" },  // 0-40: Buy
          { start: 252, end: 324, color: "#7C8696" },  // 40-70: Neutral
          { start: 324, end: 360, color: "#F0454B" },  // 70-100: Sell
        ].map((z, i) => {
          const s = (z.start * Math.PI) / 180, e = (z.end * Math.PI) / 180;
          return (
            <path
              key={i}
              d={`M${cx + r * Math.cos(s)},${cy + r * Math.sin(s)} A${r},${r} 0 0 1 ${cx + r * Math.cos(e)},${cy + r * Math.sin(e)}`}
              fill="none"
              stroke={z.color}
              strokeWidth={8}
              strokeLinecap="round"
              opacity={0.35}
            />
          );
        })}
        {/* Needle */}
        <line
          x1={cx} y1={cy}
          x2={nx} y2={ny}
          stroke={clamped < 40 ? "#1FC77D" : clamped > 70 ? "#F0454B" : "#7C8696"}
          strokeWidth={2.5}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={4}
          fill={clamped < 40 ? "#1FC77D" : clamped > 70 ? "#F0454B" : "#7C8696"} />

        {/* Zone labels */}
        <text x={6}  y={68} fontSize={8} className="fill-up"   fontWeight={600}>Buy</text>
        <text x={50} y={14} fontSize={8} className="fill-muted" fontWeight={500} textAnchor="middle">Neutral</text>
        <text x={116} y={68} fontSize={8} className="fill-down" fontWeight={600} textAnchor="end">Sell</text>
      </svg>
      <div className="mt-1 text-center">
        <span className={clsx(
          "nums text-2xl font-bold",
          clamped < 40 ? "text-up" : clamped > 70 ? "text-down" : "text-muted"
        )}>
          {clamped.toFixed(1)}
        </span>
        <p className="text-[10px] text-muted mt-0.5">RSI (14)</p>
      </div>
    </div>
  );
}

// ── Summary bar ───────────────────────────────────────────────

function SummaryBar({ indicators }: { indicators: Indicator[] }) {
  const counts = { buy: 0, sell: 0, neutral: 0 };
  for (const ind of indicators) {
    if (ind.signal === "Buy" || ind.signal === "Strong Buy") counts.buy++;
    else if (ind.signal === "Sell" || ind.signal === "Strong Sell") counts.sell++;
    else counts.neutral++;
  }
  const total  = indicators.length || 1;
  const overall: Signal =
    counts.buy >= total * 0.6   ? "Strong Buy"  :
    counts.buy > counts.sell    ? "Buy"          :
    counts.sell >= total * 0.6  ? "Strong Sell"  :
    counts.sell > counts.buy    ? "Sell"         : "Neutral";

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-up font-semibold">{counts.buy} Buy</span>
        <span className="text-muted">·</span>
        <span className="text-muted font-medium">{counts.neutral} Neutral</span>
        <span className="text-muted">·</span>
        <span className="text-down font-semibold">{counts.sell} Sell</span>
      </div>
      <Badge signal={overall} />
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────

export function TechnicalsCard({
  candles,
  currentPrice,
  latestRsi,
}: {
  candles: Candle[];
  currentPrice: number | null;
  latestRsi: number | null;
}) {
  const indicators = useMemo<Indicator[]>(() => {
    if (!candles.length || !currentPrice) return [];
    const prices = candles.map((c) => c.close);
    const last   = candles[candles.length - 1];
    const price  = currentPrice;

    const ema20v  = ema(prices, 20);
    const ema50v  = ema(prices, 50);
    const ema200v = ema(prices, 200);
    const macdRes = macd(prices);
    const bollRes = bollinger(prices);
    const rsi14   = latestRsi ?? (last.rsi ?? null);

    const bollSig = (): Signal => {
      if (bollRes.pct > 80) return "Sell";
      if (bollRes.pct < 20) return "Buy";
      if (bollRes.pct > 65) return "Sell";
      if (bollRes.pct < 35) return "Buy";
      return "Neutral";
    };

    const macdSig = (): Signal => {
      if (macdRes.hist > 0 && macdRes.macd > 0) return "Strong Buy";
      if (macdRes.hist > 0) return "Buy";
      if (macdRes.hist < 0 && macdRes.macd < 0) return "Strong Sell";
      if (macdRes.hist < 0) return "Sell";
      return "Neutral";
    };

    return [
      { name: "SMA 20",  value: last.ma20  ?? null, signal: maSig(price, last.ma20),  group: "ma"  },
      { name: "SMA 50",  value: last.ma50  ?? null, signal: maSig(price, last.ma50),  group: "ma"  },
      { name: "SMA 200", value: last.ma200 ?? null, signal: maSig(price, last.ma200), group: "ma"  },
      { name: "EMA 20",  value: ema20v,             signal: maSig(price, ema20v),     group: "ma"  },
      { name: "EMA 50",  value: ema50v,             signal: maSig(price, ema50v),     group: "ma"  },
      { name: "EMA 200", value: ema200v,            signal: maSig(price, ema200v),    group: "ma"  },
      { name: "RSI (14)",value: rsi14,              signal: rsi14 != null ? rsiSig(rsi14) : "Neutral", group: "osc" },
      { name: "MACD",    value: parseFloat(macdRes.macd.toFixed(2)), signal: macdSig(), group: "osc" },
      { name: "BB %B",   value: parseFloat(bollRes.pct.toFixed(1)),  signal: bollSig(), group: "osc" },
    ];
  }, [candles, currentPrice, latestRsi]);

  const rsi14 = latestRsi ?? (candles[candles.length - 1]?.rsi ?? null);

  if (!candles.length || !currentPrice) {
    return (
      <Card className="p-5">
        <p className="text-sm text-muted">Technicals unavailable</p>
      </Card>
    );
  }

  const maIndicators  = indicators.filter((i) => i.group === "ma");
  const oscIndicators = indicators.filter((i) => i.group === "osc");

  return (
    <Card className="overflow-hidden">
      {/* Header */}
      <div className="border-b border-border bg-raised/40 px-4 py-3">
        <h3 className="text-sm font-semibold">Technical Indicators</h3>
        <p className="text-[10px] text-muted mt-0.5">Based on latest candle data</p>
      </div>

      {/* Summary */}
      <SummaryBar indicators={indicators} />

      {/* RSI Gauge */}
      {rsi14 != null && (
        <div className="flex justify-center border-b border-border py-3">
          <RSIGauge rsi={rsi14} />
        </div>
      )}

      {/* Oscillators */}
      <div className="border-b border-border">
        <p className="px-4 py-2 text-micro-cap font-bold uppercase tracking-wider text-muted bg-raised/40">
          Oscillators
        </p>
        <div className="divide-y divide-border/60">
          {oscIndicators.map((ind) => (
            <div key={ind.name} className="flex items-center justify-between px-4 py-2.5">
              <span className="text-xs text-muted">{ind.name}</span>
              <div className="flex items-center gap-3">
                <span className="nums text-xs font-semibold text-fg">
                  {ind.value != null ? ind.value : "—"}
                  {ind.name === "BB %B" ? "%" : ""}
                </span>
                <Badge signal={ind.signal} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Moving Averages */}
      <div>
        <p className="px-4 py-2 text-micro-cap font-bold uppercase tracking-wider text-muted bg-raised/40">
          Moving Averages
        </p>
        <div className="divide-y divide-border/60">
          {maIndicators.map((ind) => (
            <div key={ind.name} className="flex items-center justify-between px-4 py-2.5">
              <span className="text-xs text-muted">{ind.name}</span>
              <div className="flex items-center gap-3">
                <span className="nums text-xs font-semibold text-fg">
                  {ind.value != null ? inr(ind.value) : "—"}
                </span>
                <Badge signal={ind.signal} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
