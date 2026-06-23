"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Bar, Timeframe } from "@/lib/markets";
import { TIMEFRAMES } from "@/lib/markets";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CandleChart } from "./candle-chart";
import { useBarStream } from "./use-bar-stream";
import { BackfillButton } from "./backfill-button";

const LIVE_DOT: Record<string, string> = {
  idle: "bg-muted",
  connecting: "bg-yellow-500 animate-pulse",
  live: "bg-emerald-500",
  closed: "bg-destructive",
};

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
    revalidateOnFocus: false,
  });

  const { latest: liveBar, state: streamState } = useBarStream(
    symbol ? source : null,
    symbol,
    timeframe,
  );

  const lastClose = useMemo(() => {
    if (liveBar) return liveBar.close;
    if (data && data.length > 0) return data[data.length - 1].close;
    return null;
  }, [data, liveBar]);

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="font-mono text-lg font-semibold">{symbol ?? "Select a symbol"}</h2>
          {lastClose !== null && (
            <span className="text-sm tabular-nums text-muted-foreground">
              ${lastClose.toLocaleString(undefined, { maximumFractionDigits: 4 })}
            </span>
          )}
          {symbol && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <span className={cn("h-2 w-2 rounded-full", LIVE_DOT[streamState])} />
              {streamState}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {TIMEFRAMES.map((tf) => (
              <Button
                key={tf}
                variant={tf === timeframe ? "default" : "ghost"}
                size="sm"
                className="h-8 px-2 font-mono text-xs"
                onClick={() => onTimeframe(tf)}
              >
                {tf}
              </Button>
            ))}
          </div>
          {symbol && <BackfillButton source={source} symbol={symbol} timeframe={timeframe} />}
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
              No bars stored for {symbol} @ {timeframe}.
            </p>
            <p>Click the Backfill button above, or wait for live ingest if streaming.</p>
          </div>
        )}
        {symbol && data && data.length > 0 && (
          <div className="absolute inset-0 p-2">
            <CandleChart bars={data} liveBar={liveBar} />
          </div>
        )}
      </div>
    </div>
  );
}
