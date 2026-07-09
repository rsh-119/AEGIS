"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
} from "lightweight-charts";
import { Maximize2 } from "lucide-react";
import clsx from "clsx";

type Candle = {
  date: string;
  close: number;
  ma20: number | null;
  ma50: number | null;
  ma200?: number | null;
};

export type MAKey = "ma20" | "ma50" | "ma200";

const MA_CFG: Record<MAKey, { label: string; color: string; dash?: number }> = {
  ma20:  { label: "MA20",  color: "#F5A524" },
  ma50:  { label: "MA50",  color: "#7C8696", dash: 2 },
  ma200: { label: "MA200", color: "#818CF8", dash: 2 },
};

interface Props {
  candles: Candle[];
  up: boolean;
  /** Controlled from outside (stock page handles the toggle state). */
  activeMA?: Set<MAKey>;
  onMAToggle?: (key: MAKey) => void;
}

export function PriceChart({ candles, up, activeMA, onMAToggle }: Props) {
  const ref      = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const maRefs   = useRef<Partial<Record<MAKey, ISeriesApi<SeriesType>>>>({});
  const [isDark, setIsDark]   = useState(false);
  const [zoomed, setZoomed]   = useState(false);
  // Internal state when not controlled externally
  const [internalMA, setInternalMA] = useState<Set<MAKey>>(new Set(["ma20", "ma50"]));

  const shownMA  = activeMA ?? internalMA;
  const toggleMA = onMAToggle ?? ((key: MAKey) =>
    setInternalMA((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    })
  );

  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  // ── Build / rebuild chart when data or theme changes ──────────────────────
  useEffect(() => {
    if (!ref.current || !candles.length) return;

    // lightweight-charts draws on <canvas>, which can't resolve CSS custom
    // properties itself (canvas fillStyle silently no-ops on "var(...)") — so
    // read the token's computed value here and hand off a plain rgb() string.
    // lightweight-charts parses colors itself before handing off to canvas,
    // and its parser only accepts classic comma-separated rgb()/rgba() — the
    // modern space-separated form (which canvas itself accepts fine) throws
    // "Cannot parse color" here, so the values are joined with commas.
    const cssVar = (name: string) =>
      getComputedStyle(document.documentElement).getPropertyValue(name).trim().split(/\s+/).join(",");
    const borderRgb = cssVar("--color-border");
    const mutedRgb  = cssVar("--color-muted");

    const gridColor = `rgba(${borderRgb},${isDark ? 0.7 : 0.9})`;
    const borderCol = `rgb(${borderRgb})`;
    const textCol   = `rgb(${mutedRgb})`;

    chartRef.current?.remove();
    maRefs.current = {};

    const chart = createChart(ref.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: textCol,
        fontFamily: "var(--font-mono)",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: gridColor },
      },
      rightPriceScale: { borderColor: borderCol },
      timeScale: { borderColor: borderCol, timeVisible: false, rightOffset: 5 },
      crosshair: { mode: 1 },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
      height: 288,
    });
    chartRef.current = chart;

    const lineColor = up ? "#1FC77D" : "#F0454B";
    const area = chart.addAreaSeries({
      lineColor,
      topColor:    up ? "rgba(31,199,125,0.18)" : "rgba(240,69,75,0.18)",
      bottomColor: "rgba(0,0,0,0)",
      lineWidth: 2,
      priceLineVisible: false,
    });
    area.setData(
      candles
        .filter((c) => c.close != null)
        .map((c) => ({ time: c.date, value: c.close }))
    );

    // Add all three MA series
    for (const [key, cfg] of Object.entries(MA_CFG) as [MAKey, typeof MA_CFG[MAKey]][]) {
      const field = key as keyof Candle;
      const maData = candles
        .filter((c) => c[field] != null)
        .map((c) => ({ time: c.date, value: c[field] as number }));

      const series = chart.addLineSeries({
        color: cfg.color,
        lineWidth: 1,
        lineStyle: cfg.dash ?? 0,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        visible: shownMA.has(key),
      });
      series.setData(maData);
      maRefs.current[key] = series;
    }

    chart.timeScale().fitContent();
    chart.timeScale().subscribeVisibleLogicalRangeChange(() => setZoomed(true));

    const onResize = () => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth });
    };
    onResize();
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
      chartRef.current = null;
      maRefs.current = {};
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candles, up, isDark]);

  // ── Toggle MA visibility without rebuilding the chart ────────────────────
  useEffect(() => {
    for (const key of Object.keys(MA_CFG) as MAKey[]) {
      maRefs.current[key]?.applyOptions({ visible: shownMA.has(key) });
    }
  }, [shownMA]);

  function resetZoom() {
    chartRef.current?.timeScale().fitContent();
    setZoomed(false);
  }

  return (
    <div className="relative">
      {zoomed && (
        <button
          onClick={resetZoom}
          className="absolute right-3 top-2 z-10 flex items-center gap-1 rounded-md border border-border bg-surface/90 px-2 py-1 text-micro-cap font-medium text-muted shadow-sm backdrop-blur-sm transition hover:text-fg"
        >
          <Maximize2 className="h-2.5 w-2.5" />
          Reset
        </button>
      )}
      <div ref={ref} className="w-full" />

      {/* Legend + MA toggles */}
      <div className="mt-2 flex flex-wrap items-center gap-3">
        {(Object.entries(MA_CFG) as [MAKey, typeof MA_CFG[MAKey]][]).map(([key, cfg]) => {
          const active = shownMA.has(key);
          return (
            <button
              key={key}
              onClick={() => toggleMA(key)}
              className={clsx(
                "flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs transition-all",
                active
                  ? "border-transparent bg-raised text-fg"
                  : "border-border text-muted opacity-50 hover:opacity-80"
              )}
            >
              <i
                className="inline-block h-0.5 w-3 shrink-0 rounded-full"
                style={{ background: active ? cfg.color : "#6b7280" }}
              />
              {cfg.label}
            </button>
          );
        })}
        <span className="ml-auto text-[10px] text-muted/60">Scroll to zoom · Drag to pan</span>
      </div>
    </div>
  );
}
