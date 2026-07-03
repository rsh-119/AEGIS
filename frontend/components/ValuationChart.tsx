"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, type IChartApi } from "lightweight-charts";

type Candle = { date: string; close: number };

type Props = {
  candles: Candle[];
  divisor: number | null;   // eps for PE, book_value for PB
  label: string;            // "P/E" or "P/B"
  color?: string;           // line + fill colour
};

export function ValuationChart({ candles, divisor, label, color = "#3b82f6" }: Props) {
  const ref   = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const check = () => setDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!ref.current || !candles.length || !divisor || divisor <= 0) return;

    const bg      = dark ? "#11151e" : "#ffffff";
    const gridCol = dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)";
    const textCol = dark ? "#7c8696" : "#6b7280";
    const fill    = color + (dark ? "28" : "22");   // hex alpha

    chart.current?.remove();
    const c = createChart(ref.current, {
      width:  ref.current.clientWidth,
      height: 192,
      layout: { background: { type: ColorType.Solid, color: bg }, textColor: textCol },
      grid:   { vertLines: { color: gridCol }, horzLines: { color: gridCol } },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.05 } },
      timeScale:       { borderVisible: false, timeVisible: false },
      crosshair:       { mode: 1 },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale:  { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    });
    chart.current = c;

    const series = c.addAreaSeries({
      lineColor:      color,
      topColor:       fill,
      bottomColor:    "transparent",
      lineWidth:      2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
    });

    const data = candles
      .map((d) => ({
        time:  d.date as string,
        value: parseFloat((d.close / divisor).toFixed(2)),
      }))
      .filter((d) => d.value > 0 && isFinite(d.value));

    series.setData(data);
    c.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (ref.current) c.applyOptions({ width: ref.current.clientWidth });
    });
    ro.observe(ref.current);
    return () => { ro.disconnect(); c.remove(); chart.current = null; };
  }, [candles, divisor, dark, color, label]);

  if (!divisor || divisor <= 0) {
    return (
      <div className="flex h-48 items-center justify-center">
        <p className="text-sm text-muted">{label} data not available for this stock</p>
      </div>
    );
  }

  return <div ref={ref} className="h-48 w-full" />;
}
