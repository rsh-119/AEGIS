"use client";

import { use, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, inr, pct, signCls, num } from "@/lib/api";
import { PriceChart } from "@/components/PriceChart";
import { ChevronLeft, TrendingUp, TrendingDown, BarChart3 } from "lucide-react";
import clsx from "clsx";
import { ChartCard } from "@/components/ui/animated-card-chart";
import { Card } from "@/components/ui/card";
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

const INDEX_META: Record<string, { name: string; desc: string; exchange: string }> = {
  nifty50:     { name: "Nifty 50", desc: "Top 50 companies by free-float market cap listed on NSE", exchange: "NSE" },
  sensex:      { name: "Sensex", desc: "30 large & financially sound companies listed on BSE", exchange: "BSE" },
  banknifty:   { name: "Bank Nifty", desc: "12 most liquid & large capitalised Indian banking stocks on NSE", exchange: "NSE" },
  niftyit:     { name: "Nifty IT", desc: "IT sector benchmark — top Indian technology companies on NSE", exchange: "NSE" },
  niftypharma: { name: "Nifty Pharma", desc: "Pharmaceutical sector benchmark on NSE", exchange: "NSE" },
};

export default function IndexPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [period, setPeriod] = useState("1y");

  const { data, isLoading } = useSWR(
    `/api/market/index/${slug}?period=${period}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  const meta = INDEX_META[slug] ?? { name: slug.toUpperCase(), desc: "Market index", exchange: "NSE" };
  const q = data?.quote ?? {};
  const hist = data?.history ?? {};
  const price = q.current_price;
  const prev = q.previous_close;
  const change = price && prev ? ((price - prev) / prev) * 100 : null;
  const up = (change ?? 0) >= 0;
  const periodLabel = PERIODS.find((p) => p.value === period)?.label ?? "1Y";

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Back nav */}
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-1.5 text-sm text-muted hover:text-fg transition-colors">
          <ChevronLeft className="h-4 w-4" /> Home
        </Link>
        <span className="text-border">/</span>
        <span className="text-sm font-medium">{meta.name}</span>
      </div>

      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-saffron/10 ring-1 ring-saffron/20">
              <BarChart3 className="h-5 w-5 text-saffron" />
            </div>
            <div>
              <h1 className="font-display text-2xl font-bold">{meta.name}</h1>
              <p className="text-xs text-muted">{meta.desc} · {meta.exchange}</p>
            </div>
          </div>
        </div>
        {price && (
          <div className="text-right">
            <div className="nums text-3xl font-bold">
              {price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            </div>
            <div className={clsx("nums text-sm font-semibold flex items-center justify-end gap-1", signCls(change))}>
              {up ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
              {pct(change)} today
              {q.previous_close && (
                <span className="ml-1 text-muted font-normal">
                  (prev {q.previous_close.toLocaleString("en-IN", { maximumFractionDigits: 2 })})
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Stats strip */}
      {price && (
        <div className="flex flex-wrap gap-2 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
          {[
            { label: "Current", value: price.toLocaleString("en-IN", { maximumFractionDigits: 2 }) },
            { label: "Prev Close", value: q.previous_close?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—" },
            { label: "Day High", value: q.day_high?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—" },
            { label: "Day Low", value: q.day_low?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—" },
            { label: "52W High", value: q.week52_high?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—" },
            { label: "52W Low", value: q.week52_low?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—" },
            { label: `${periodLabel} Change`, value: hist.pct_change != null ? `${hist.pct_change >= 0 ? "+" : ""}${hist.pct_change.toFixed(2)}%` : "—" },
          ].map((s) => (
            <Card key={s.label} className="cursor-default select-none transition-all duration-200 hover:-translate-y-0.5 hover:border-[rgba(21,128,61,0.22)] hover:shadow-[var(--shadow-md),var(--shadow-glow)] min-w-[110px] text-center shrink-0 px-3 py-2.5">
              <Label className="block">{s.label}</Label>
              <p className="nums mt-1 text-sm font-bold">{s.value}</p>
            </Card>
          ))}
        </div>
      )}

      {/* Chart */}
      <ChartCard color={up ? "#1FC77D" : "#F0454B"} className="p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-baseline gap-3">
            <h2 className="font-semibold">{meta.name} Chart</h2>
            {hist.pct_change != null && (
              <span className={clsx("nums text-sm font-semibold", signCls(hist.pct_change))}>
                {hist.pct_change >= 0 ? "+" : ""}{hist.pct_change.toFixed(2)}% · {periodLabel}
              </span>
            )}
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

        {isLoading ? (
          <div className="skeleton h-80 w-full rounded-lg" />
        ) : (
          <PriceChart candles={hist.candles ?? []} up={up} />
        )}
      </ChartCard>

      {/* About */}
      <Card className="p-5">
        <h2 className="mb-2 font-semibold">About {meta.name}</h2>
        <p className="text-sm leading-relaxed text-muted">{meta.desc}</p>
        <p className="mt-3 text-xs text-muted/60">
          Index data from Yahoo Finance · {meta.exchange} · For reference only, not investment advice.
        </p>
      </Card>
    </div>
  );
}
