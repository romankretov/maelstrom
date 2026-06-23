"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Bar, Timeframe } from "@/lib/markets";
import { TIMEFRAMES } from "@/lib/markets";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CandleChart } from "./candle-chart";

export function ChartPanel({
  source,
  symbol,
  timeframe,
  onTimeframe,
}: {
  source: string;
  symbol: string | null;
  timeframe: Timeframe;
  onTimeframe: (tf: Timeframe) => void;
}) {
  const key = symbol
    ? `/markets/ohlcv?source=${source}&symbol=${symbol}&timeframe=${timeframe}&limit=500`
    : null;

  const { data, isLoading, error } = useSWR<Bar[]>(key, fetcher, {
    refreshInterval: 30_000,
  });

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="font-mono text-lg font-semibold">{symbol ?? "Select a symbol"}</h2>
          {data && data.length > 0 && (
            <span className="text-sm tabular-nums text-muted-foreground">
              {data.length} bars · last close ${data[data.length - 1].close.toLocaleString()}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {TIMEFRAMES.map((tf) => (
            <Button
              key={tf}
              variant={tf === timeframe ? "default" : "ghost"}
              size="sm"
              className={cn("h-8 px-2 font-mono text-xs")}
              onClick={() => onTimeframe(tf)}
            >
              {tf}
            </Button>
          ))}
        </div>
      </div>
      <div className="relative flex-1 rounded-md border bg-card">
        {!symbol && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Pick a symbol from the left to see its chart.
          </div>
        )}
        {symbol && isLoading && (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Loading bars…
          </div>
        )}
        {symbol && error && (
          <div className="flex h-full items-center justify-center text-sm text-destructive">
            {(error as { message?: string }).message ?? "Failed to load bars."}
          </div>
        )}
        {symbol && data && data.length === 0 && !isLoading && (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
            <p>
              No bars stored yet for {symbol} @ {timeframe}.
            </p>
            <p>Trigger a backfill from the API or wait for live ingest (Phase 1.4).</p>
          </div>
        )}
        {symbol && data && data.length > 0 && (
          <div className="absolute inset-0 p-2">
            <CandleChart bars={data} />
          </div>
        )}
      </div>
    </div>
  );
}
