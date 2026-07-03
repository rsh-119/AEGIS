"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, type IChartApi } from "lightweight-charts";
import { Maximize2 } from "lucide-react";

type Candle = { date: string; volume?: number; close: number };

export function VolumeChart({ candles }: { candles: Candle[] }) {
  const ref      = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [dark, setDark] = useState(false);
  const [zoomed, setZoomed] = useState(false);

  useEffect(() => {
    const check = () => setDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!ref.current || !candles.length) return;

    const bg        = "transparent";
    const gridColor = dark ? "rgba(31,38,50,0.7)" : "rgba(226,230,236,0.9)";
    const borderCol = dark ? "#1F2632" : "#E2E6EC";
    const textCol   = dark ? "#7C8696" : "#636e7d";

    chartRef.current?.remove();
    const c = createChart(ref.current, {
      layout: {
        background: { type: ColorType.Solid, color: bg },
        textColor: textCol,
        fontFamily: "var(--font-mono)",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: gridColor },
      },
      rightPriceScale: {
        borderColor: borderCol,
        scaleMargins: { top: 0.1, bottom: 0.02 },
        // format volumes as compact numbers (e.g. 12.4M)
        mode: 0,
      },
      timeScale: {
        borderColor: borderCol,
        timeVisible: false,
        rightOffset: 5,
        barSpacing: 6,
        minBarSpacing: 1,
      },
      crosshair: { mode: 1 },
      // ── Interactivity enabled (same as PriceChart defaults) ──
      handleScroll: {
        mouseWheel:   true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch:      true,
      },
      height: 288,
    });
    chartRef.current = c;

    const vols    = candles.map((d) => d.volume ?? 0).filter((v) => v > 0);
    const avgVol  = vols.length ? vols.reduce((s, v) => s + v, 0) / vols.length : 1;
    const spikeThresh = avgVol * 2;

    const volSeries = c.addHistogramSeries({
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: {
        type: "custom",
        formatter: (v: number) =>
          v >= 1e7 ? `${(v / 1e7).toFixed(1)}Cr` :
          v >= 1e5 ? `${(v / 1e5).toFixed(1)}L` :
          v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v),
        minMove: 1,
      },
    });

    const data = candles
      .filter((d) => d.volume != null && d.volume > 0)
      .map((d) => ({
        time:  d.date as string,
        value: d.volume!,
        color: d.volume! >= spikeThresh
          ? "#ef4444"               // red spike — 2× average
          : dark ? "#f59e0b99" : "#f59e0bcc", // amber, slightly transparent
      }));

    volSeries.setData(data);

    // 20-day moving average of volume as an overlay line
    const window20 = 20;
    const maData: { time: string; value: number }[] = [];
    for (let i = window20 - 1; i < data.length; i++) {
      const slice = data.slice(i - window20 + 1, i + 1);
      const ma = slice.reduce((s, d) => s + d.value, 0) / window20;
      maData.push({ time: data[i].time, value: ma });
    }
    const maSeries = c.addLineSeries({
      color: dark ? "#7C8696" : "#9CA8B8",
      lineWidth: 1,
      lineStyle: 2,   // dashed
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
    });
    maSeries.setData(maData);

    c.timeScale().fitContent();

    // Track when user zooms so we can show the reset button
    c.timeScale().subscribeVisibleLogicalRangeChange(() => setZoomed(true));

    const ro = new ResizeObserver(() => {
      if (ref.current) c.applyOptions({ width: ref.current.clientWidth });
    });
    ro.observe(ref.current);

    return () => {
      ro.disconnect();
      c.remove();
      chartRef.current = null;
    };
  }, [candles, dark]);

  function resetZoom() {
    chartRef.current?.timeScale().fitContent();
    setZoomed(false);
  }

  return (
    <div className="relative">
      {/* Reset zoom button — appears after user zooms */}
      {zoomed && (
        <button
          onClick={resetZoom}
          className="absolute right-3 top-2 z-10 flex items-center gap-1 rounded-md border border-border bg-surface/90 px-2 py-1 text-[10px] font-medium text-muted shadow-sm backdrop-blur-sm transition hover:text-fg"
        >
          <Maximize2 className="h-2.5 w-2.5" />
          Reset
        </button>
      )}
      <div ref={ref} className="h-72 w-full" />
      <div className="mt-2 flex gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-500/80" />
          Volume
        </span>
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-0.5 w-4" style={{ background: "repeating-linear-gradient(to right, #9CA8B8 0, #9CA8B8 3px, transparent 3px, transparent 6px)" }} />
          20-day avg
        </span>
        <span className="flex items-center gap-1.5">
          <i className="inline-block h-2.5 w-2.5 rounded-sm bg-red-500" />
          Spike (2× avg)
        </span>
        <span className="ml-auto text-[10px] text-muted/60">Scroll to zoom · Drag to pan</span>
      </div>
    </div>
  );
}
