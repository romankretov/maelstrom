"use client";

import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import type { BacktestEquityPoint } from "@/lib/backtests";

export function EquityChart({ points }: { points: BacktestEquityPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const equityRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ddRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
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

    const equity = chart.addLineSeries({
      color: "#22c55e",
      lineWidth: 2,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });

    const drawdown = chart.addAreaSeries({
      topColor: "rgba(239, 68, 68, 0.25)",
      bottomColor: "rgba(239, 68, 68, 0.02)",
      lineColor: "rgba(239, 68, 68, 0.6)",
      lineWidth: 1,
      priceScaleId: "dd",
      priceFormat: { type: "percent", precision: 2, minMove: 0.01 },
    });
    chart.priceScale("dd").applyOptions({
      scaleMargins: { top: 0.75, bottom: 0 },
      borderColor: "#1f2937",
    });

    chartRef.current = chart;
    equityRef.current = equity;
    ddRef.current = drawdown;

    return () => {
      chart.remove();
      chartRef.current = null;
      equityRef.current = null;
      ddRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!equityRef.current || !ddRef.current) return;
    const eq = points.map((p) => ({
      time: (new Date(p.ts).getTime() / 1000) as Time,
      value: p.equity,
    }));
    const dd = points.map((p) => ({
      time: (new Date(p.ts).getTime() / 1000) as Time,
      value: -p.drawdown * 100, // show as negative percent for visual intuition
    }));
    equityRef.current.setData(eq);
    ddRef.current.setData(dd);
    chartRef.current?.timeScale().fitContent();
  }, [points]);

  return <div ref={containerRef} className="h-full w-full" />;
}
