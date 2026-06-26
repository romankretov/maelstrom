"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { fmtMoney, fmtPct } from "@/lib/backtests";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Diagnostics = {
  fills_count: number;
  winning_fills: number;
  losing_fills: number;
  longest_winning_streak: number;
  longest_losing_streak: number;
  largest_win: number;
  largest_loss: number;
  avg_win: number;
  avg_loss: number;
  win_rate: number;
  profit_factor: number | null;
  expectancy: number;
  time_in_market_pct: number;
  max_drawdown: number;
  longest_drawdown_bars: number;
  exposure_by_symbol: Record<string, number>;
  pnl_by_symbol: Record<string, number>;
};

function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "good" | "bad";
}) {
  return (
    <div className="flex items-baseline justify-between border-b border-border/40 py-1.5 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono tabular-nums",
          tone === "good" && "text-emerald-400",
          tone === "bad" && "text-destructive",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function DiagnosticsCard({ runId }: { runId: string }) {
  const { data, error, isLoading } = useSWR<Diagnostics>(
    `/backtests/${runId}/diagnostics`,
    fetcher,
  );

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Diagnostics</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {error && (
          <p className="text-xs text-destructive">
            {(error as { message?: string }).message ?? "Failed to load"}
          </p>
        )}
        {data && (
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                Trade quality
              </div>
              <Row label="Fills" value={data.fills_count} />
              <Row label="Win rate" value={fmtPct(data.win_rate)} />
              <Row
                label="Profit factor"
                value={data.profit_factor != null ? data.profit_factor.toFixed(2) : "∞"}
              />
              <Row label="Expectancy / fill" value={fmtMoney(data.expectancy)} />
              <Row label="Avg win" value={fmtMoney(data.avg_win)} tone="good" />
              <Row label="Avg loss" value={fmtMoney(data.avg_loss)} tone="bad" />
              <Row label="Largest win" value={fmtMoney(data.largest_win)} tone="good" />
              <Row label="Largest loss" value={fmtMoney(data.largest_loss)} tone="bad" />
              <Row label="Longest winning streak" value={`${data.longest_winning_streak} fills`} />
              <Row label="Longest losing streak" value={`${data.longest_losing_streak} fills`} />
            </div>

            <div>
              <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
                Risk & exposure
              </div>
              <Row label="Max drawdown" value={fmtPct(data.max_drawdown)} tone="bad" />
              <Row label="Longest drawdown" value={`${data.longest_drawdown_bars} bars`} />
              <Row label="Time in market" value={fmtPct(data.time_in_market_pct)} />

              {Object.keys(data.pnl_by_symbol).length > 0 && (
                <>
                  <div className="mb-1 mt-3 text-[10px] uppercase tracking-wide text-muted-foreground">
                    PnL by symbol
                  </div>
                  {Object.entries(data.pnl_by_symbol)
                    .sort(([, a], [, b]) => b - a)
                    .map(([sym, p]) => (
                      <Row
                        key={sym}
                        label={sym}
                        value={fmtMoney(p)}
                        tone={p >= 0 ? "good" : "bad"}
                      />
                    ))}
                </>
              )}

              {Object.keys(data.exposure_by_symbol).length > 0 && (
                <>
                  <div className="mb-1 mt-3 text-[10px] uppercase tracking-wide text-muted-foreground">
                    Total notional traded
                  </div>
                  {Object.entries(data.exposure_by_symbol)
                    .sort(([, a], [, b]) => b - a)
                    .map(([sym, n]) => (
                      <Row key={sym} label={sym} value={fmtMoney(n)} />
                    ))}
                </>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
