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
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "hsl(215, 20%, 65%)",
        fontFamily: "ui-monospace, SFMono-Regular, monospace",
      },
      grid: {
        vertLines: { color: "hsl(217, 33%, 18%)" },
        horzLines: { color: "hsl(217, 33%, 18%)" },
      },
      rightPriceScale: { borderColor: "hsl(217, 33%, 18%)" },
      timeScale: { borderColor: "hsl(217, 33%, 18%)", timeVisible: true, secondsVisible: false },
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
