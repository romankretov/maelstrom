"use client";

import { Suspense, useMemo } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import {
  type BacktestEquityPoint,
  type BacktestRun,
  fmtMoney,
  fmtNum,
  fmtPct,
} from "@/lib/backtests";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SweepCurve } from "@/components/backtests/sweep-curve";
import { cn } from "@/lib/utils";

// Color palette for the overlay — keep it readable on dark backgrounds.
const SERIES_COLORS = [
  "#60a5fa", // blue-400
  "#34d399", // emerald-400
  "#f472b6", // pink-400
  "#fb923c", // orange-400
  "#a78bfa", // violet-400
  "#facc15", // yellow-400
];

type RunWithEquity = {
  run: BacktestRun;
  equity: BacktestEquityPoint[];
};

function useRunWithEquity(id: string): { data: RunWithEquity | null; error: unknown } {
  const { data: run, error: runErr } = useSWR<BacktestRun>(`/backtests/${id}`, fetcher);
  const { data: equity, error: eqErr } = useSWR<BacktestEquityPoint[]>(
    run?.status === "done" ? `/backtests/${id}/equity` : null,
    fetcher,
  );
  if (run && equity) {
    return { data: { run, equity }, error: null };
  }
  return { data: null, error: runErr ?? eqErr ?? null };
}

function MetricsTable({ runs }: { runs: RunWithEquity[] }) {
  const m = (r: RunWithEquity) => r.run.metrics;

  const rows: { label: string; render: (r: RunWithEquity, i: number) => React.ReactNode }[] = [
    {
      label: "Status",
      render: (r) => <span className="font-mono text-xs">{r.run.status}</span>,
    },
    {
      label: "Range",
      render: (r) => (
        <span className="font-mono text-xs">
          {new Date(r.run.range_start).toLocaleDateString()} →{" "}
          {new Date(r.run.range_end).toLocaleDateString()}
        </span>
      ),
    },
    {
      label: "Symbols",
      render: (r) => <span className="font-mono text-xs">{r.run.symbols.join(", ")}</span>,
    },
    {
      label: "Timeframe",
      render: (r) => <span className="font-mono text-xs">{r.run.timeframe}</span>,
    },
    {
      label: "Initial capital",
      render: (r) => (
        <span className="font-mono text-xs">{fmtMoney(Number(r.run.initial_capital))}</span>
      ),
    },
    {
      label: "Final equity",
      render: (r) => (
        <span className="font-mono text-xs">{m(r) ? fmtMoney(m(r)!.final_equity) : "—"}</span>
      ),
    },
    {
      label: "Total return",
      render: (r) =>
        m(r) ? (
          <span
            className={cn(
              "font-mono text-xs tabular-nums",
              m(r)!.total_return >= 0 ? "text-emerald-400" : "text-destructive",
            )}
          >
            {fmtPct(m(r)!.total_return)}
          </span>
        ) : (
          "—"
        ),
    },
    {
      label: "Sharpe",
      render: (r) => <span className="font-mono text-xs">{m(r) ? fmtNum(m(r)!.sharpe) : "—"}</span>,
    },
    {
      label: "Sortino",
      render: (r) => (
        <span className="font-mono text-xs">{m(r) ? fmtNum(m(r)!.sortino) : "—"}</span>
      ),
    },
    {
      label: "Max drawdown",
      render: (r) => (
        <span className="font-mono text-xs text-destructive">
          {m(r) ? fmtPct(m(r)!.max_drawdown) : "—"}
        </span>
      ),
    },
    {
      label: "Calmar",
      render: (r) => <span className="font-mono text-xs">{m(r) ? fmtNum(m(r)!.calmar) : "—"}</span>,
    },
    {
      label: "Win rate",
      render: (r) => (
        <span className="font-mono text-xs">{m(r) ? fmtPct(m(r)!.win_rate) : "—"}</span>
      ),
    },
    {
      label: "Trades",
      render: (r) => <span className="font-mono text-xs">{m(r)?.trade_count ?? "—"}</span>,
    },
    {
      label: "Profit factor",
      render: (r) => (
        <span className="font-mono text-xs">{m(r) ? fmtNum(m(r)!.profit_factor) : "—"}</span>
      ),
    },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">
        <thead>
          <tr className="text-xs text-muted-foreground">
            <th className="px-3 py-2 text-left">Metric</th>
            {runs.map((r, i) => (
              <th key={r.run.id} className="px-3 py-2 text-left">
                <div className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ backgroundColor: SERIES_COLORS[i % SERIES_COLORS.length] }}
                  />
                  <Link
                    href={`/backtests/${r.run.id}`}
                    className="font-mono hover:underline"
                    title={r.run.id}
                  >
                    {r.run.id.slice(0, 8)}
                  </Link>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-border/60">
              <td className="px-3 py-1.5 text-muted-foreground">{row.label}</td>
              {runs.map((r, i) => (
                <td key={r.run.id} className="px-3 py-1.5">
                  {row.render(r, i)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EquityOverlay({ runs }: { runs: RunWithEquity[] }) {
  // Normalize each series to its own initial equity (so % returns overlay
  // cleanly even when initial capital differs). x-axis is fraction-of-run
  // duration to align curves over different time windows.
  const series = useMemo(
    () =>
      runs
        .filter((r) => r.equity.length >= 2)
        .map((r, idx) => {
          const initial = r.equity[0].equity || 1;
          const tsMs = r.equity.map((p) => new Date(p.ts).getTime());
          const tMin = tsMs[0];
          const tMax = tsMs[tsMs.length - 1];
          const tSpan = tMax - tMin || 1;
          const pts = r.equity.map((p, i) => ({
            x: (tsMs[i] - tMin) / tSpan,
            y: (p.equity - initial) / initial, // return as fraction
          }));
          return { id: r.run.id, color: SERIES_COLORS[idx % SERIES_COLORS.length], pts };
        }),
    [runs],
  );

  if (series.length === 0) {
    return <div className="text-sm text-muted-foreground">No equity data to chart.</div>;
  }

  const allY = series.flatMap((s) => s.pts.map((p) => p.y));
  const yMin = Math.min(...allY, 0);
  const yMax = Math.max(...allY, 0);
  const yRange = yMax - yMin || 1;

  const w = 800;
  const h = 280;
  const padX = 30;
  const padY = 20;
  const x = (v: number) => padX + v * (w - 2 * padX);
  const y = (v: number) => padY + (1 - (v - yMin) / yRange) * (h - 2 * padY);
  const zeroY = y(0);

  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-72 w-full">
        {/* zero line */}
        <line
          x1={padX}
          x2={w - padX}
          y1={zeroY}
          y2={zeroY}
          stroke="currentColor"
          strokeOpacity="0.15"
          strokeDasharray="3 3"
        />
        {/* y labels */}
        <text x={2} y={y(yMax)} fontSize="9" fill="currentColor" fillOpacity="0.5">
          {fmtPct(yMax)}
        </text>
        <text x={2} y={y(yMin) - 2} fontSize="9" fill="currentColor" fillOpacity="0.5">
          {fmtPct(yMin)}
        </text>
        {series.map((s) => {
          const d = s.pts
            .map((p, i) => `${i === 0 ? "M" : "L"} ${x(p.x).toFixed(2)} ${y(p.y).toFixed(2)}`)
            .join(" ");
          return (
            <path
              key={s.id}
              d={d}
              fill="none"
              stroke={s.color}
              strokeWidth="1.5"
              strokeLinejoin="round"
            />
          );
        })}
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
        {series.map((s) => (
          <div key={s.id} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="font-mono">{s.id.slice(0, 8)}</span>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        x-axis: fraction of each run&apos;s duration (curves are aligned in time-of-run, not
        calendar time). y-axis: return relative to initial capital.
      </p>
    </div>
  );
}

function CompareInner() {
  const params = useSearchParams();
  const idsParam = params.get("ids") ?? "";
  const ids = idsParam
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  // Hook order must be stable, so always call useRunWithEquity up to a max.
  // Cap at 6 runs (matches palette + readable chart).
  const r1 = useRunWithEquity(ids[0] ?? "");
  const r2 = useRunWithEquity(ids[1] ?? "");
  const r3 = useRunWithEquity(ids[2] ?? "");
  const r4 = useRunWithEquity(ids[3] ?? "");
  const r5 = useRunWithEquity(ids[4] ?? "");
  const r6 = useRunWithEquity(ids[5] ?? "");
  const slots = [r1, r2, r3, r4, r5, r6].slice(0, ids.length);

  if (ids.length < 2) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          Select at least 2 backtests to compare. Pass IDs as <code>?ids=a,b,c</code>.
        </CardContent>
      </Card>
    );
  }
  if (ids.length > 6) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-destructive">Max 6 runs at once.</CardContent>
      </Card>
    );
  }

  const loaded: RunWithEquity[] = slots
    .map((s) => s.data)
    .filter((d): d is RunWithEquity => d !== null);
  const allLoaded = loaded.length === ids.length;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Backtest comparison</h1>
        <p className="text-sm text-muted-foreground">
          {ids.length} runs · equity normalized to initial capital · time-aligned by run fraction.
        </p>
      </header>

      {!allLoaded && (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">
            Loading {ids.length - loaded.length} of {ids.length}…
          </CardContent>
        </Card>
      )}

      {loaded.length >= 2 && (
        <>
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-base">Sweep curve</CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-2">
              <SweepCurve runs={loaded.map((r) => r.run)} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-base">Equity (% return)</CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-2">
              <EquityOverlay runs={loaded} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-base">Metrics</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <MetricsTable runs={loaded} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading…</p>}>
      <CompareInner />
    </Suspense>
  );
}
