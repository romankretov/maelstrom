"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TIMEFRAMES, type Timeframe } from "@/lib/markets";
import { formatCompactNumber, formatPct, formatPrice, type MarketStats } from "@/lib/research";
import { cn } from "@/lib/utils";

function PctBadge({ value, label }: { value: number | null; label: string }) {
  const positive = value != null && value > 0;
  const negative = value != null && value < 0;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono text-sm",
          positive && "text-emerald-500",
          negative && "text-rose-500",
        )}
      >
        {formatPct(value)}
      </span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="font-mono text-sm">{value}</span>
    </div>
  );
}

export function StatsCard({
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
  const enabled = !!symbol;
  const params = new URLSearchParams({ source, timeframe });
  if (symbol) params.set("symbol", symbol);
  const { data, isLoading, error } = useSWR<MarketStats>(
    enabled ? `/research/stats?${params.toString()}` : null,
    fetcher,
    { refreshInterval: 30_000 },
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between p-4 pb-2">
        <CardTitle className="text-base">
          {symbol ? `${symbol} stats` : "Pick a symbol to load stats"}
        </CardTitle>
        <div className="flex gap-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              type="button"
              onClick={() => onTimeframe(tf)}
              className={cn(
                "rounded px-2 py-0.5 text-xs",
                tf === timeframe
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-secondary/60",
              )}
            >
              {tf}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-2">
        {!enabled && (
          <div className="text-sm text-muted-foreground">
            Stats appear once you pick a symbol from the list.
          </div>
        )}
        {enabled && isLoading && <div className="text-sm text-muted-foreground">Loading…</div>}
        {enabled && error && (
          <div className="text-sm text-destructive">
            {(error as { message?: string }).message ?? "Failed to load stats"}
          </div>
        )}
        {enabled && data && data.bar_count === 0 && (
          <div className="text-sm text-muted-foreground">
            No bars stored for this symbol/timeframe yet. Backtests now auto-backfill on demand; you
            can also kick a sync from the Markets page.
          </div>
        )}
        {enabled && data && data.bar_count > 0 && (
          <div className="space-y-4">
            <div className="flex items-baseline gap-4">
              <div className="font-mono text-3xl">{formatPrice(data.last_price)}</div>
              <div className="text-xs text-muted-foreground">
                {data.bar_count} bars · since{" "}
                {data.earliest_ts ? new Date(data.earliest_ts).toLocaleDateString() : "—"}
              </div>
            </div>
            <div className="grid grid-cols-4 gap-3">
              <PctBadge value={data.change_1h} label="1h" />
              <PctBadge value={data.change_24h} label="24h" />
              <PctBadge value={data.change_7d} label="7d" />
              <PctBadge value={data.change_30d} label="30d" />
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="24h high" value={formatPrice(data.high_24h)} />
              <Stat label="24h low" value={formatPrice(data.low_24h)} />
              <Stat label="24h volume" value={formatCompactNumber(data.volume_24h)} />
              <Stat label="Realized vol 24h (ann.)" value={formatPct(data.realized_vol_24h)} />
              <Stat label="Realized vol 7d (ann.)" value={formatPct(data.realized_vol_7d)} />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
