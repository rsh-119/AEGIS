"use client";

import { use, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetcher, inr, inrCompact, pct, num, signCls } from "@/lib/api";
import { PriceChart } from "@/components/PriceChart";
import { ChartCard } from "@/components/ui/animated-card-chart";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Newspaper, ExternalLink, TrendingUp, TrendingDown, ArrowRight } from "lucide-react";
import clsx from "clsx";
import { PERIODS_BASIC } from "@/lib/periods";

type Article = {
  title: string;
  publisher?: string;
  link?: string;
  date?: string | null;
  sentiment?: number;
};

// Same +/-0.05 VADER-score thresholds the full stock page's SplitNewsCard
// uses, so an article lands in the same bucket everywhere it's shown.
function newsRow(a: Article, i: number, tone: "up" | "down") {
  return (
    <a
      key={i}
      href={a.link}
      target="_blank"
      rel="noopener"
      className="group flex items-start gap-2.5 rounded-xl px-2.5 py-2.5 transition-colors hover:bg-raised"
    >
      <span className={clsx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", tone === "up" ? "bg-up" : "bg-down")} />
      <div className="min-w-0 flex-1">
        <p className={clsx(
          "text-sm leading-snug text-fg/90 transition-colors",
          tone === "up" ? "group-hover:text-up" : "group-hover:text-down"
        )}>
          {a.title}
        </p>
        <div className="mt-1 flex items-center gap-1.5 text-[10px] text-muted">
          {a.publisher && <span>{a.publisher}</span>}
          {a.publisher && a.date && <span>·</span>}
          {a.date && <span>{a.date}</span>}
        </div>
      </div>
      {a.link && (
        <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-muted/60 group-hover:text-saffron transition-colors" />
      )}
    </a>
  );
}

// Quick-look page for a ticker — basic price/chart info + related news,
// with a way through to the full research page. Reached from the watchlist
// (clicking a row used to jump straight to /stock/[ticker]); this fills the
// gap with a lighter view instead of the whole page.
export default function StockPreviewPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = use(params);
  const symbol = decodeURIComponent(ticker);
  const bare = symbol.replace(/\.(NS|BO)$/, "");
  const [period, setPeriod] = useState("3mo");

  const { data: core, isLoading: coreLoading, error } = useSWR(
    `/api/stocks/${symbol}/core?period=${period}`,
    fetcher,
    { revalidateOnFocus: false }
  );
  const { data: newsData, isLoading: newsLoading } = useSWR(
    `/api/stocks/${symbol}/news`,
    fetcher,
    { revalidateOnFocus: false }
  );

  if (error) return <ErrorState symbol={symbol} />;
  if (coreLoading || !core) return <LoadingState />;

  const q = core.quote;
  const hist = core.history;
  const up = (hist?.pct_change ?? 0) >= 0;
  const change =
    q.current_price && q.previous_close
      ? ((q.current_price - q.previous_close) / q.previous_close) * 100
      : null;
  const articles: Article[] = newsData?.articles ?? [];
  const positiveNews = articles.filter((a) => (a.sentiment ?? 0) >= 0.05);
  const negativeNews = articles.filter((a) => (a.sentiment ?? 0) <= -0.05);
  const sentiment = newsData?.sentiment;
  const sentColor =
    sentiment?.label === "Positive" ? "text-up" :
    sentiment?.label === "Negative" ? "text-down" : "text-saffron";

  return (
    <div className="space-y-6 animate-fade-up">
      {/* ── Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="font-display text-xl sm:text-2xl md:text-3xl font-bold leading-tight">
              {q.company_name || bare}
            </h1>
            {q.exchange && (
              <Badge className="bg-raised text-muted ring-1 ring-border text-xs">{q.exchange}</Badge>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-2 flex-wrap text-muted">
            <span className="font-mono text-xs">{symbol}</span>
            {q.sector && (
              <>
                <span className="text-xs">·</span>
                <span className="text-xs">{q.sector}</span>
              </>
            )}
          </div>
          <Button asChild className="mt-3 flex w-fit items-center gap-1.5 text-xs py-1.5 px-3">
            <Link href={`/stock/${encodeURIComponent(symbol)}`}>
              Detail view <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
        <div className="text-right shrink-0">
          <div className="nums text-2xl sm:text-3xl md:text-4xl font-bold">{inr(q.current_price)}</div>
          <div className={clsx("nums mt-1 text-sm sm:text-base font-semibold flex items-center justify-end gap-1", signCls(change))}>
            {(change ?? 0) >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
            {pct(change)} today
          </div>
          {q.previous_close && <p className="mt-0.5 text-xs text-muted">Prev {inr(q.previous_close)}</p>}
        </div>
      </div>

      {/* ── Chart ── */}
      <ChartCard color={up ? "#1FC77D" : "#F0454B"}>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-border px-4 sm:px-5 pt-3 pb-2 gap-1 sm:gap-0">
          <span className={clsx("nums text-sm font-semibold", signCls(hist?.pct_change))}>
            {pct(hist?.pct_change)} · {PERIODS_BASIC.find((p) => p.value === period)?.label ?? period}
          </span>
          <div className="flex items-center gap-1 rounded-lg bg-raised p-1 self-start sm:self-auto overflow-x-auto scrollbar-none max-w-full">
            {PERIODS_BASIC.map((p) => (
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
        <div className="px-2 pb-3 pt-3">
          <PriceChart candles={hist?.candles || []} up={up} />
        </div>
      </ChartCard>

      {/* ── Key stats ── */}
      <Card className="overflow-hidden">
        <div className="border-b border-border bg-raised/40 px-4 py-3">
          <h2 className="text-sm font-semibold">Key Stats</h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-y divide-border">
          {[
            { label: "Market Cap", value: inrCompact(q.market_cap) },
            { label: "P/E (TTM)", value: num(q.pe_ratio) },
            { label: "Div Yield", value: q.dividend_yield != null ? `${(q.dividend_yield * 100).toFixed(2)}%` : "—" },
            { label: "ROE", value: q.roe != null ? `${(q.roe * 100).toFixed(1)}%` : "—" },
            { label: "Day High", value: inr(q.day_high) },
            { label: "Day Low", value: inr(q.day_low) },
            { label: "52W High", value: inr(q.week52_high) },
            { label: "52W Low", value: inr(q.week52_low) },
          ].map((m) => (
            <div key={m.label} className="flex flex-col gap-0.5 px-3 sm:px-4 py-2.5">
              <Label className="text-micro-cap">{m.label}</Label>
              <span className="nums text-xs sm:text-sm font-bold leading-tight">{m.value}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* ── Related news, split by sentiment ── */}
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border bg-raised/40 px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Newspaper className="h-4 w-4 text-saffron" />
            <h2 className="text-sm font-semibold">Related News</h2>
            {!newsLoading && articles.length > 0 && (
              <span className="text-xs text-muted">
                {positiveNews.length} positive · {negativeNews.length} negative
              </span>
            )}
          </div>
          {sentiment?.label && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] text-muted">Sentiment</span>
              <span className={clsx("text-sm font-bold", sentColor)}>{sentiment.label}</span>
            </div>
          )}
        </div>

        <div className="p-3">
          {newsLoading && (
            <div className="space-y-2 p-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-14 w-full rounded-xl" />
              ))}
            </div>
          )}
          {!newsLoading && articles.length === 0 && (
            <p className="p-6 text-center text-sm text-muted">No recent news found for this stock.</p>
          )}
          {!newsLoading && articles.length > 0 && (
            <div className="space-y-5">
              {/* Positive */}
              <div>
                <div className="mb-1.5 flex items-center gap-1.5">
                  <TrendingUp className="h-3.5 w-3.5 text-up" />
                  <Label className="text-up">Positive ({positiveNews.length})</Label>
                </div>
                {positiveNews.length === 0 ? (
                  <p className="px-2.5 text-xs italic text-muted">No positive headlines found.</p>
                ) : (
                  <div className="space-y-1.5">{positiveNews.map((a, i) => newsRow(a, i, "up"))}</div>
                )}
              </div>

              {/* Negative */}
              <div>
                <div className="mb-1.5 flex items-center gap-1.5">
                  <TrendingDown className="h-3.5 w-3.5 text-down" />
                  <Label className="text-down">Negative ({negativeNews.length})</Label>
                </div>
                {negativeNews.length === 0 ? (
                  <p className="px-2.5 text-xs italic text-muted">No negative headlines found.</p>
                ) : (
                  <div className="space-y-1.5">{negativeNews.map((a, i) => newsRow(a, i, "down"))}</div>
                )}
              </div>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <div className="skeleton h-12 w-72" />
      <div className="skeleton h-[380px] w-full rounded-card" />
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
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
        IndianAPI may be rate-limited, or this isn't a valid NSE/BSE symbol. Try again shortly.
      </p>
    </Card>
  );
}
