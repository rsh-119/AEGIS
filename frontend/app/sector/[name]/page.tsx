"use client";

import { use, useState } from "react";
import useSWR from "swr";
import { fetcher, num } from "@/lib/api";
import { ChevronLeft, Building2 } from "lucide-react";
import clsx from "clsx";
import Link from "next/link";
import { PriceChart } from "@/components/PriceChart";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { findSectorCfg } from "@/lib/sectors";
import { PERIODS_BASIC as PERIODS } from "@/lib/periods";
import { StockConstituentsTable, type ConstituentStock } from "@/components/StockConstituentsTable";

type SectorData = {
  sector: string;
  stocks: ConstituentStock[];
  stats: {
    median_pe: number | null;
    median_pb: number | null;
    median_return_1y: number | null;
    count: number;
  };
};

function StatBox({ label, value, up }: { label: string; value: string; up?: boolean }) {
  return (
    <Card className="p-4 cursor-default select-none text-center transition-all duration-200 hover:-translate-y-0.5 hover:border-[rgb(var(--color-saffron)/0.22)] hover:shadow-[var(--shadow-md),var(--shadow-glow)]">
      <Label className="block">{label}</Label>
      <p className={clsx("nums mt-1.5 text-xl font-bold", up ? "text-up" : "text-fg")}>{value}</p>
    </Card>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function SectorPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = use(params);
  const sector = decodeURIComponent(name);
  const cfg = findSectorCfg(sector);

  const { data, isLoading, error } = useSWR<SectorData>(
    `/api/market/sector/${encodeURIComponent(sector)}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  const [period, setPeriod] = useState("1y");

  const { data: indexData, isLoading: indexLoading } = useSWR(
    cfg?.indexSlug ? `/api/market/index/${cfg.indexSlug}?period=${period}` : null,
    fetcher,
    { revalidateOnFocus: false }
  );
  const indexQ    = indexData?.quote ?? {};
  const indexHist = indexData?.history ?? {};
  const indexUp   = (indexHist.pct_change ?? 0) >= 0;
  const indexCandles = indexHist.candles ?? [];

  return (
    <div className="space-y-6 animate-fade-up">
      {/* Back nav */}
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-1.5 text-sm text-muted hover:text-fg transition-colors">
          <ChevronLeft className="h-4 w-4" /> Home
        </Link>
        <span className="text-border">/</span>
        <span className="text-sm text-muted">Sectors</span>
        <span className="text-border">/</span>
        <span className="text-sm font-medium">{sector}</span>
      </div>

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className={clsx(
          "flex h-10 w-10 items-center justify-center rounded-xl ring-1",
          cfg ? cfg.color : "bg-saffron/10 text-saffron", cfg ? cfg.accent : "ring-saffron/20"
        )}>
          {cfg ? <cfg.icon className="h-5 w-5" /> : <Building2 className="h-5 w-5" />}
        </div>
        <div>
          <h1 className="font-display text-2xl font-bold">{sector}</h1>
          <p className="text-sm text-muted">
            {data ? `${data.stocks.length} companies tracked` : "Loading…"}
          </p>
        </div>
      </div>

      {/* Sector index chart */}
      {cfg?.indexSlug && (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
            <div>
              <p className="text-xs text-muted">Sector Index</p>
              <p className="font-semibold text-fg">{sector} Index</p>
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

      {/* Sector stats */}
      {data?.stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatBox label="Companies" value={String(data.stats.count)} />
          <StatBox label="Median P/E" value={data.stats.median_pe != null ? num(data.stats.median_pe) : "—"} />
          <StatBox label="Median P/B" value={data.stats.median_pb != null ? num(data.stats.median_pb) : "—"} />
          <StatBox
            label="Median 1Y Return"
            value={data.stats.median_return_1y != null
              ? `${data.stats.median_return_1y >= 0 ? "+" : ""}${data.stats.median_return_1y.toFixed(1)}%`
              : "—"}
            up={data.stats.median_return_1y != null && data.stats.median_return_1y >= 0}
          />
        </div>
      )}

      {/* Skeletons */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="skeleton h-14 rounded-xl" style={{ opacity: 1 - i * 0.08 }} />
          ))}
        </div>
      )}

      {error && (
        <Card className="p-8 text-center">
          <p className="text-muted">Could not load sector data. Try again shortly.</p>
        </Card>
      )}

      <StockConstituentsTable
        stocks={data?.stocks ?? []}
        medianPe={data?.stats.median_pe}
        title={`${sector} Stocks`}
        footnote="P/E < sector median highlighted green · ROE > 15% highlighted green · Returns are price-only · Click any column header to sort ↑↓"
      />

      {data?.stocks?.length === 0 && !isLoading && (
        <Card className="p-8 text-center">
          <Building2 className="mx-auto mb-3 h-8 w-8 text-muted/30" />
          <p className="text-muted">No tracked stocks found for <strong>{sector}</strong>.</p>
        </Card>
      )}
    </div>
  );
}
