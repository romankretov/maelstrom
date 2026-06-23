"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { type BacktestRun, fmtPct, statusColor } from "@/lib/backtests";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function BacktestList({ strategyId }: { strategyId: string }) {
  const { data, isLoading, error } = useSWR<BacktestRun[]>(
    `/backtests/strategies/${strategyId}`,
    fetcher,
    { refreshInterval: 4000 },
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Backtest runs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {error && (
          <p className="text-xs text-destructive">
            {(error as { message?: string }).message ?? "Failed to load runs."}
          </p>
        )}
        {data?.length === 0 && <p className="text-xs text-muted-foreground">No runs yet.</p>}
        {data?.map((r) => (
          <Link
            key={r.id}
            href={`/backtests/${r.id}`}
            className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-secondary/40"
          >
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                  statusColor(r.status),
                )}
              >
                {r.status}
              </span>
              <span className="font-mono text-xs">
                {r.symbols.join(",")} · {r.timeframe}
              </span>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              {r.metrics && (
                <span
                  className={cn(
                    "tabular-nums",
                    r.metrics.total_return >= 0 ? "text-emerald-400" : "text-destructive",
                  )}
                >
                  {fmtPct(r.metrics.total_return)}
                </span>
              )}
              <span>{new Date(r.created_at).toLocaleString()}</span>
            </div>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}
