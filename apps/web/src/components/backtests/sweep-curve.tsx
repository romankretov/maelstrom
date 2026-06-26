"use client";

import { useMemo, useState } from "react";
import type { BacktestRun } from "@/lib/backtests";
import { fmtNum, fmtPct } from "@/lib/backtests";

type Metric = "total_return" | "sharpe" | "sortino" | "max_drawdown" | "win_rate" | "trade_count";

const METRIC_LABEL: Record<Metric, string> = {
  total_return: "Total return",
  sharpe: "Sharpe",
  sortino: "Sortino",
  max_drawdown: "Max drawdown",
  win_rate: "Win rate",
  trade_count: "Trade count",
};

const METRIC_FMT: Record<Metric, (n: number) => string> = {
  total_return: fmtPct,
  sharpe: (n) => fmtNum(n),
  sortino: (n) => fmtNum(n),
  max_drawdown: fmtPct,
  win_rate: fmtPct,
  trade_count: (n) => String(Math.round(n)),
};

/**
 * Detect which param varies across the run set. Returns the name of the
 * single varying param (and its values), or null if 0 or >1 params differ.
 *
 * Sweeps are constructed server-side with exactly one varying param, so in
 * practice this always finds it — but we guard against compare-page misuse
 * where the user threw in unrelated runs.
 */
function detectSweepParam(
  runs: BacktestRun[],
): { name: string; values: (number | string)[] } | null {
  if (runs.length < 2) return null;
  const keys = new Set<string>();
  for (const r of runs) for (const k of Object.keys(r.params)) keys.add(k);
  const varying: string[] = [];
  for (const k of keys) {
    const vs = new Set<string>();
    for (const r of runs) vs.add(JSON.stringify(r.params[k] ?? null));
    if (vs.size > 1) varying.push(k);
  }
  if (varying.length !== 1) return null;
  const name = varying[0];
  const values = runs.map((r) => {
    const v = r.params[name];
    return typeof v === "number" ? v : String(v);
  });
  return { name, values };
}

export function SweepCurve({ runs }: { runs: BacktestRun[] }) {
  const [metric, setMetric] = useState<Metric>("sharpe");

  const sweep = useMemo(() => detectSweepParam(runs), [runs]);

  const data = useMemo(() => {
    if (!sweep) return [];
    const pairs = runs
      .map((r, i) => ({
        param: sweep.values[i],
        metric: r.metrics ? (r.metrics[metric] as number | null) : null,
        run: r,
      }))
      .filter(
        (p): p is { param: number | string; metric: number; run: BacktestRun } =>
          p.metric !== null && Number.isFinite(p.metric),
      );
    // If param is numeric, sort by it so the curve makes sense.
    const numeric = pairs.every((p) => typeof p.param === "number");
    if (numeric) {
      return [...pairs].sort((a, b) => (a.param as number) - (b.param as number));
    }
    return pairs;
  }, [runs, sweep, metric]);

  if (!sweep) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        Need exactly one varying parameter across runs to draw a sweep curve. (These look like
        unrelated backtests.)
      </div>
    );
  }
  if (data.length < 2) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        Not enough completed runs yet — at least 2 need to finish before the curve can render.
      </div>
    );
  }

  const numericX = data.every((p) => typeof p.param === "number");
  const xs = data.map((_, i) => i);
  const ys = data.map((p) => p.metric);
  const yMin = Math.min(...ys, 0);
  const yMax = Math.max(...ys, 0);
  const yRange = yMax - yMin || 1;

  const w = 800;
  const h = 280;
  const padX = 50;
  const padY = 30;
  const xPos = (i: number) =>
    data.length === 1 ? w / 2 : padX + (i / (data.length - 1)) * (w - 2 * padX);
  const yPos = (v: number) => padY + (1 - (v - yMin) / yRange) * (h - 2 * padY);
  const zeroY = yPos(0);
  const bestIdx = ys.indexOf(metric === "max_drawdown" ? Math.min(...ys) : Math.max(...ys));

  const path = xs
    .map((i) => `${i === 0 ? "M" : "L"} ${xPos(i).toFixed(2)} ${yPos(ys[i]).toFixed(2)}`)
    .join(" ");

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">
          <span className="font-mono">{sweep.name}</span> swept across {data.length} runs · best:{" "}
          <span className="font-mono">{String(data[bestIdx].param)}</span> →{" "}
          <span className="font-mono">{METRIC_FMT[metric](ys[bestIdx])}</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {(Object.keys(METRIC_LABEL) as Metric[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMetric(m)}
              className={
                "rounded px-2 py-0.5 text-xs " +
                (metric === m
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-secondary/60")
              }
            >
              {METRIC_LABEL[m]}
            </button>
          ))}
        </div>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-72 w-full">
        <line
          x1={padX}
          x2={w - padX}
          y1={zeroY}
          y2={zeroY}
          stroke="currentColor"
          strokeOpacity="0.15"
          strokeDasharray="3 3"
        />
        <text x={4} y={yPos(yMax) + 4} fontSize="10" fill="currentColor" fillOpacity="0.5">
          {METRIC_FMT[metric](yMax)}
        </text>
        <text x={4} y={yPos(yMin) - 2} fontSize="10" fill="currentColor" fillOpacity="0.5">
          {METRIC_FMT[metric](yMin)}
        </text>
        <path d={path} fill="none" stroke="#60a5fa" strokeWidth="2" strokeLinejoin="round" />
        {data.map((p, i) => (
          <g key={p.run.id}>
            <circle
              cx={xPos(i)}
              cy={yPos(p.metric)}
              r={i === bestIdx ? 5 : 3}
              fill={i === bestIdx ? "#34d399" : "#60a5fa"}
            >
              <title>
                {String(p.param)} → {METRIC_FMT[metric](p.metric)} ({p.run.id.slice(0, 8)})
              </title>
            </circle>
            <text
              x={xPos(i)}
              y={h - padY + 14}
              textAnchor="middle"
              fontSize="9"
              fill="currentColor"
              fillOpacity="0.5"
            >
              {numericX
                ? Number(p.param).toLocaleString(undefined, { maximumFractionDigits: 4 })
                : String(p.param)}
            </text>
          </g>
        ))}
      </svg>
      <p className="text-xs text-muted-foreground">
        x-axis: <span className="font-mono">{sweep.name}</span>. Tap a dot for the exact value &
        backtest id.
      </p>
    </div>
  );
}
