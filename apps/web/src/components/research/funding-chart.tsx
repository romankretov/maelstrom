"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatPct, type FundingHistoryOut } from "@/lib/research";
import { cn } from "@/lib/utils";

const RANGES = [7, 14, 30, 90] as const;
type Range = (typeof RANGES)[number];

function FundingSparkline({ points }: { points: FundingHistoryOut["points"] }) {
  if (points.length < 2) {
    return (
      <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
        Need more data — the worker pulls funding rates hourly.
      </div>
    );
  }
  const rates = points.map((p) => p.rate);
  const min = Math.min(...rates, 0);
  const max = Math.max(...rates, 0);
  const range = max - min || 1;

  const w = 720;
  const h = 120;
  const padX = 4;
  const padY = 8;

  const x = (i: number) => padX + (i / (points.length - 1)) * (w - 2 * padX);
  const y = (r: number) => padY + (1 - (r - min) / range) * (h - 2 * padY);
  const zeroY = y(0);

  // Build path
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(2)} ${y(p.rate).toFixed(2)}`)
    .join(" ");

  // First/last labels
  const firstTs = new Date(points[0].ts);
  const lastTs = new Date(points[points.length - 1].ts);

  return (
    <div className="overflow-hidden">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-32 w-full" preserveAspectRatio="none">
        <line
          x1={padX}
          x2={w - padX}
          y1={zeroY}
          y2={zeroY}
          stroke="currentColor"
          strokeOpacity="0.2"
          strokeDasharray="3 3"
        />
        <path d={d} fill="none" stroke="currentColor" strokeWidth="1.4" />
        {points.map((p, i) => (
          <circle
            key={i}
            cx={x(i)}
            cy={y(p.rate)}
            r="1.2"
            fill={p.rate >= 0 ? "rgb(16,185,129)" : "rgb(244,63,94)"}
          />
        ))}
      </svg>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{firstTs.toLocaleDateString()}</span>
        <span>min {formatPct(min, 4)}</span>
        <span>max {formatPct(max, 4)}</span>
        <span>{lastTs.toLocaleDateString()}</span>
      </div>
    </div>
  );
}

export function FundingChart({ source, symbol }: { source: string; symbol: string | null }) {
  const [days, setDays] = useState<Range>(30);
  const enabled = !!symbol;
  const params = new URLSearchParams({ source, days: String(days) });
  if (symbol) params.set("symbol", symbol);

  const { data, isLoading, error } = useSWR<FundingHistoryOut>(
    enabled ? `/research/funding?${params.toString()}` : null,
    fetcher,
    { refreshInterval: 0 },
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between p-4 pb-2">
        <CardTitle className="text-base">
          {symbol ? `${symbol} funding rate (perp)` : "Funding rate (pick a symbol)"}
        </CardTitle>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setDays(r)}
              className={cn(
                "rounded px-2 py-0.5 text-xs",
                r === days
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-secondary/60",
              )}
            >
              {r}d
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-2">
        {!enabled && (
          <div className="text-sm text-muted-foreground">
            Funding rate appears once you pick a perp symbol.
          </div>
        )}
        {enabled && isLoading && <div className="text-sm text-muted-foreground">Loading…</div>}
        {enabled && error && (
          <div className="text-sm text-destructive">
            {(error as { message?: string }).message ?? "Failed to load"}
          </div>
        )}
        {enabled && data && data.points.length === 0 && (
          <div className="text-sm text-muted-foreground">
            No funding data yet. The worker syncs hourly — wait or trigger{" "}
            <code className="rounded bg-muted px-1">sync_funding_rates</code> manually.
          </div>
        )}
        {enabled && data && data.points.length > 0 && (
          <div className="space-y-3">
            <FundingSparkline points={data.points} />
            <div className="grid grid-cols-3 gap-4 text-xs">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Mean ({data.days}d)
                </div>
                <div className="font-mono">{formatPct(data.mean, 4)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Annualized
                </div>
                <div
                  className={cn(
                    "font-mono",
                    data.annualized != null && data.annualized > 0 && "text-emerald-500",
                    data.annualized != null && data.annualized < 0 && "text-rose-500",
                  )}
                >
                  {formatPct(data.annualized, 2)}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Samples
                </div>
                <div className="font-mono">{data.points.length}</div>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
