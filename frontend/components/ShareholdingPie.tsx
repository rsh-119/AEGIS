"use client";

import { useState } from "react";
import useSWR from "swr";
import clsx from "clsx";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

type Segment = { label: string; pct: number; color: string };

type Quarter = {
  quarter:  string;
  promoter: number;
  fii:      number;
  dii:      number;
  public:   number;
};

type HistoryData = {
  quarters:   Quarter[];
  source:     string;
  source_url: string;
  error?:     string;
};

function polarXY(cx: number, cy: number, r: number, deg: number) {
  const rad = (deg - 90) * (Math.PI / 180);
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, a1: number, a2: number) {
  const s     = polarXY(cx, cy, r, a1);
  const e     = polarXY(cx, cy, r, a2);
  const large = a2 - a1 > 180 ? 1 : 0;
  return `M${cx},${cy} L${s.x},${s.y} A${r},${r} 0 ${large} 1 ${e.x},${e.y} Z`;
}

function DonutChart({
  segments,
  hovered,
  setHovered,
}: {
  segments: (Segment & { start: number; end: number; sweep: number })[];
  hovered:    number | null;
  setHovered: (i: number | null) => void;
}) {
  const CX = 80, CY = 80, R = 68, IR = 36;
  return (
    <svg width={160} height={160} viewBox="0 0 160 160" className="shrink-0">
      {segments.map((arc, idx) => {
        const isHov  = hovered === idx;
        const midDeg = arc.start + arc.sweep / 2;
        const midRad = (midDeg - 90) * (Math.PI / 180);
        const dx     = isHov ? Math.cos(midRad) * 5 : 0;
        const dy     = isHov ? Math.sin(midRad) * 5 : 0;
        return (
          <g key={idx} transform={`translate(${dx},${dy})`}
            onMouseEnter={() => setHovered(idx)}
            onMouseLeave={() => setHovered(null)}
            className="cursor-pointer"
          >
            <path
              d={arcPath(CX, CY, R, arc.start, arc.end)}
              fill={arc.color}
              opacity={hovered == null || isHov ? 1 : 0.55}
              style={{ transition: "opacity 0.15s, transform 0.15s" }}
            />
            <circle cx={CX} cy={CY} r={IR} fill="transparent" />
          </g>
        );
      })}
      <circle cx={CX} cy={CY} r={IR} className="fill-surface" />
      {hovered != null ? (
        <>
          <text x={CX} y={CY - 6} textAnchor="middle" className="fill-fg" fontSize={13} fontWeight={700}>
            {segments[hovered].pct.toFixed(1)}%
          </text>
          <text x={CX} y={CY + 10} textAnchor="middle" className="fill-muted" fontSize={8.5}>
            {segments[hovered].label}
          </text>
        </>
      ) : (
        <>
          <text x={CX} y={CY - 4} textAnchor="middle" className="fill-fg" fontSize={10} fontWeight={600}>
            Holding
          </text>
          <text x={CX} y={CY + 9} textAnchor="middle" className="fill-muted" fontSize={8}>
            Pattern
          </text>
        </>
      )}
    </svg>
  );
}

function TrendBadge({ current, prev }: { current: number; prev: number }) {
  const diff = current - prev;
  if (Math.abs(diff) < 0.01) return <Minus className="h-3 w-3 text-muted" />;
  if (diff > 0)
    return (
      <span className="flex items-center gap-0.5 text-micro-cap font-semibold text-up">
        <TrendingUp className="h-3 w-3" />+{diff.toFixed(2)}%
      </span>
    );
  return (
    <span className="flex items-center gap-0.5 text-micro-cap font-semibold text-down">
      <TrendingDown className="h-3 w-3" />{diff.toFixed(2)}%
    </span>
  );
}

const CATS: { key: keyof Quarter; label: string; color: string }[] = [
  { key: "promoter", label: "Promoters",    color: "#F5A524" },
  { key: "fii",      label: "FII / FPI",    color: "#3B82F6" },
  { key: "dii",      label: "DII",          color: "#8B5CF6" },
  { key: "public",   label: "Public",       color: "#1FC77D" },
];

type StaticProps = {
  promoterPct:    number | null;
  institutionPct: number | null;
  ticker:         string;
};

export function ShareholdingPie({ promoterPct, institutionPct, ticker }: StaticProps) {
  const [hovered,    setHovered]    = useState<number | null>(null);
  const [qIdx,       setQIdx]       = useState(0);

  const fetcher = (url: string) => fetch(url).then((r) => r.json());
  const { data, isLoading } = useSWR<HistoryData>(
    `/api/stocks/${encodeURIComponent(ticker)}/shareholding-history`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 86_400_000 }
  );

  const quarters = data?.quarters ?? [];
  const hasHistory = quarters.length > 0;

  // Selected quarter data (or fallback to yfinance snapshot)
  const selected = hasHistory ? quarters[qIdx] : null;

  const rawSegs: (Segment & { key: keyof Quarter })[] = hasHistory && selected
    ? CATS
        .map((c) => ({ ...c, pct: Number(selected[c.key]) || 0 }))
        .filter((s) => s.pct > 0)
    : ([
        { key: "promoter" as keyof Quarter, label: "Promoters",    color: "#F5A524", pct: promoterPct ?? 0 },
        { key: "fii"      as keyof Quarter, label: "Institutions", color: "#3B82F6", pct: institutionPct ?? 0 },
        { key: "public"   as keyof Quarter, label: "Public",       color: "#1FC77D", pct: Math.max(0, 100 - (promoterPct ?? 0) - (institutionPct ?? 0)) },
      ] as (Segment & { key: keyof Quarter })[]).filter((s) => s.pct > 0);

  let angle = 0;
  const arcs = rawSegs.map((seg) => {
    const sweep = (seg.pct / 100) * 360;
    const start = angle;
    angle       = start + sweep;
    return { ...seg, start, end: angle, sweep };
  });

  const prevQ = hasHistory && qIdx < quarters.length - 1 ? quarters[qIdx + 1] : null;

  if (arcs.length === 0 && !isLoading) {
    return (
      <div className="flex h-full items-center justify-center py-8">
        <p className="text-sm text-muted">Shareholding data unavailable</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-5">
      {/* Quarter selector */}
      {hasHistory && (
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          {quarters.map((q, i) => (
            <button
              key={i}
              onClick={() => { setQIdx(i); setHovered(null); }}
              className={clsx(
                "shrink-0 rounded-full px-2.5 py-0.5 text-micro font-medium transition-all",
                i === qIdx
                  ? "bg-saffron text-white"
                  : "bg-raised text-muted hover:text-fg"
              )}
            >
              {q.quarter}
            </button>
          ))}
        </div>
      )}

      {isLoading && !hasHistory && (
        <div className="h-1 w-full overflow-hidden rounded-full bg-raised">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-saffron/40" />
        </div>
      )}

      <div className="flex items-center gap-5">
        <DonutChart segments={arcs} hovered={hovered} setHovered={setHovered} />

        {/* Legend */}
        <div className="flex flex-col gap-2 min-w-0 flex-1">
          {arcs.map((arc, idx) => (
            <button
              key={idx}
              onMouseEnter={() => setHovered(idx)}
              onMouseLeave={() => setHovered(null)}
              className={clsx(
                "flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left transition-all",
                hovered === idx ? "ring-1" : "hover:bg-raised/60"
              )}
              style={hovered === idx ? { outline: `1px solid ${arc.color}`, backgroundColor: arc.color + "14" } : {}}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: arc.color }} />
                <span className="text-xs text-muted truncate">{arc.label}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {prevQ && (
                  <TrendBadge
                    current={Number(selected?.[arc.key as keyof Quarter]) || 0}
                    prev={Number(prevQ[arc.key as keyof Quarter]) || 0}
                  />
                )}
                <span className="nums text-sm font-bold" style={{ color: arc.color }}>
                  {arc.pct.toFixed(2)}%
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      <p className="text-[10px] text-muted/60 leading-relaxed">
        {hasHistory
          ? <>Source: <a href={data?.source_url} target="_blank" rel="noreferrer" className="underline hover:text-muted">BSE India</a> · SEBI-mandated quarterly disclosure</>
          : "Source: IndianAPI · Promoters = insider holding reported by exchange."}
      </p>
    </div>
  );
}
