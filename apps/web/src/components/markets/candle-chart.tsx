"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { Bar } from "@/lib/markets";

function toLwc(b: Bar) {
  return {
    time: (new Date(b.ts).getTime() / 1000) as Time,
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  };
}

export function CandleChart({ bars, liveBar }: { bars: Bar[]; liveBar?: Bar | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // Create chart once.
  useEffect(() => {
    if (!containerRef.current) return;
    // NB: lightweight-charts v4 only accepts hex or rgb()/rgba(), not hsl()
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "rgba(0,0,0,0)" },
        textColor: "#9ca3af",
        fontFamily: "ui-monospace, SFMono-Regular, monospace",
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      rightPriceScale: { borderColor: "#1f2937" },
      timeScale: { borderColor: "#1f2937", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 1 },
      autoSize: true,
    });
    const series = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Initial data load — replaces series whenever the bar array reference changes.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    series.setData(bars.map(toLwc));
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  // Live updates — much cheaper than setData on every tick.
  useEffect(() => {
    if (!liveBar) return;
    const series = seriesRef.current;
    if (!series) return;
    series.update(toLwc(liveBar));
  }, [liveBar]);

  return <div ref={containerRef} className="h-full w-full" />;
}
