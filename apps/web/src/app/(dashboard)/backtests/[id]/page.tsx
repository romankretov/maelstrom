"use client";

import { use } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import {
  type BacktestEquityPoint,
  type BacktestRun,
  type BacktestTrade,
  fmtMoney,
  fmtNum,
  fmtPct,
  statusColor,
} from "@/lib/backtests";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EquityChart } from "@/components/backtests/equity-chart";
import { DiagnosticsCard } from "@/components/backtests/diagnostics-card";
import { OptimizeDialog } from "@/components/backtests/optimize-dialog";
import { cn } from "@/lib/utils";

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "good" | "bad" | "neutral";
}) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent
        className={cn(
          "pt-0 font-mono text-xl tabular-nums",
          tone === "good" && "text-emerald-400",
          tone === "bad" && "text-destructive",
        )}
      >
        {value}
      </CardContent>
    </Card>
  );
}

export default function BacktestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: run, error } = useSWR<BacktestRun>(`/backtests/${id}`, fetcher, {
    refreshInterval: (data) =>
      data && (data.status === "done" || data.status === "failed") ? 0 : 1500,
  });
  const { data: equity } = useSWR<BacktestEquityPoint[]>(
    run && run.status === "done" ? `/backtests/${id}/equity` : null,
    fetcher,
  );
  const { data: trades } = useSWR<BacktestTrade[]>(
    run && run.status === "done" ? `/backtests/${id}/trades?limit=500` : null,
    fetcher,
  );

  if (error) {
    return (
      <p className="text-sm text-destructive">
        {(error as { message?: string }).message ?? "Failed to load backtest."}
      </p>
    );
  }
  if (!run) return <p className="text-sm text-muted-foreground">Loading…</p>;

  const m = run.metrics;
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Link
              href={`/strategies/${run.strategy_id}`}
              className="text-xs text-muted-foreground hover:underline"
            >
              ← strategy
            </Link>
            <span
              className={cn(
                "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                statusColor(run.status),
              )}
            >
              {run.status}
            </span>
          </div>
          <h1 className="font-mono text-xl font-semibold">
            {run.symbols.join(",")} · {run.timeframe} · {run.source}
          </h1>
          <p className="text-xs text-muted-foreground">
            {new Date(run.range_start).toLocaleDateString()} →{" "}
            {new Date(run.range_end).toLocaleDateString()} · capital ${run.initial_capital}
          </p>
        </div>
        {run.status === "done" && <OptimizeDialog runId={run.id} strategyId={run.strategy_id} />}
      </header>

      {run.status === "failed" && (
        <Card className="border-destructive/40">
          <CardContent className="space-y-1 p-4">
            <p className="text-sm font-medium text-destructive">Run failed</p>
            <pre className="overflow-auto whitespace-pre-wrap font-mono text-xs text-muted-foreground">
              {run.error}
            </pre>
          </CardContent>
        </Card>
      )}

      {(run.status === "pending" || run.status === "running") && (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            {run.status === "pending"
              ? "Queued — waiting for a worker to pick this up."
              : "Running — loading bars, executing on_bar for every event. This page polls automatically."}
          </CardContent>
        </Card>
      )}

      {run.status === "done" && m && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Total return"
              value={fmtPct(m.total_return)}
              tone={m.total_return >= 0 ? "good" : "bad"}
            />
            <Metric label="Sharpe" value={fmtNum(m.sharpe)} />
            <Metric label="Sortino" value={fmtNum(m.sortino)} />
            <Metric label="Max drawdown" value={fmtPct(-m.max_drawdown)} tone="bad" />
            <Metric label="Final equity" value={fmtMoney(m.final_equity)} />
            <Metric label="Win rate" value={fmtPct(m.win_rate)} />
            <Metric label="Trades" value={m.trade_count} />
            <Metric
              label="Profit factor"
              value={m.profit_factor === null ? "∞" : fmtNum(m.profit_factor)}
            />
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Equity curve & drawdown</CardTitle>
            </CardHeader>
            <CardContent className="h-72 p-2">
              {equity && equity.length > 0 ? (
                <EquityChart points={equity} />
              ) : (
                <p className="p-4 text-sm text-muted-foreground">No equity data.</p>
              )}
            </CardContent>
          </Card>

          <DiagnosticsCard runId={id} />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Trades {trades && `(${trades.length})`}</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="max-h-[60vh] overflow-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-left">Time</th>
                      <th className="px-3 py-2 text-left">Symbol</th>
                      <th className="px-3 py-2 text-left">Side</th>
                      <th className="px-3 py-2 text-right">Qty</th>
                      <th className="px-3 py-2 text-right">Price</th>
                      <th className="px-3 py-2 text-right">Fee</th>
                      <th className="px-3 py-2 text-right">PnL</th>
                      <th className="px-3 py-2 text-left">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades?.map((t) => (
                      <tr key={t.id} className="border-t text-xs">
                        <td className="px-3 py-1 font-mono text-muted-foreground">
                          {new Date(t.ts).toLocaleString()}
                        </td>
                        <td className="px-3 py-1 font-mono">{t.symbol}</td>
                        <td
                          className={cn(
                            "px-3 py-1 uppercase",
                            t.side === "buy" ? "text-emerald-400" : "text-destructive",
                          )}
                        >
                          {t.side}
                        </td>
                        <td className="px-3 py-1 text-right font-mono tabular-nums">
                          {fmtNum(t.qty, 6)}
                        </td>
                        <td className="px-3 py-1 text-right font-mono tabular-nums">
                          {fmtMoney(t.price)}
                        </td>
                        <td className="px-3 py-1 text-right font-mono tabular-nums text-muted-foreground">
                          {fmtMoney(t.fee)}
                        </td>
                        <td
                          className={cn(
                            "px-3 py-1 text-right font-mono tabular-nums",
                            t.pnl > 0 && "text-emerald-400",
                            t.pnl < 0 && "text-destructive",
                          )}
                        >
                          {t.pnl !== 0 ? fmtMoney(t.pnl) : "—"}
                        </td>
                        <td className="px-3 py-1 text-muted-foreground">{t.reason ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
