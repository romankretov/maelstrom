"use client";

import { use } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type LiveEvent = {
  id: string;
  ts: string;
  kind: string;
  payload: Record<string, unknown>;
};

type Position = {
  symbol: string;
  qty: number;
  avg_price: number;
  last_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
};

type RecentFill = {
  ts: string;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  fee: number;
  pnl: number;
  reason: string | null;
};

type Snapshot = {
  live_strategy_id: string;
  status: string;
  error: string | null;
  started_at: string | null;
  cash: number | null;
  equity: number | null;
  realized_pnl: number | null;
  positions: Position[];
  recent_fills: RecentFill[];
  events: LiveEvent[];
};

function relTime(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function fmtMoney(n: number | null | undefined): string {
  if (n == null) return "—";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1000) return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `${sign}$${abs.toFixed(2)}`;
}

function statusTone(status: string): string {
  if (status === "running") return "bg-emerald-500/15 text-emerald-400";
  if (status === "failed") return "bg-rose-500/15 text-rose-500";
  if (status === "stopped") return "bg-muted text-muted-foreground";
  return "bg-yellow-500/15 text-yellow-400 animate-pulse";
}

function eventTone(kind: string): string {
  if (kind === "fill") return "bg-emerald-500/15 text-emerald-400";
  if (kind === "reject" || kind === "on_bar_error") return "bg-rose-500/15 text-rose-500";
  if (kind === "submit") return "bg-blue-500/15 text-blue-400";
  return "bg-muted text-muted-foreground";
}

export default function LiveRuntimePage({
  params,
}: {
  params: Promise<{ id: string; liveId: string }>;
}) {
  const { id, liveId } = use(params);
  const { data, error, isLoading } = useSWR<Snapshot>(
    `/live-strategies/${liveId}/snapshot`,
    fetcher,
    { refreshInterval: 3_000 },
  );

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error)
    return (
      <p className="text-sm text-destructive">
        {(error as { message?: string }).message ?? "Failed to load runtime"}
      </p>
    );
  if (!data) return null;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <Link
            href={`/strategies/${id}`}
            className="text-xs text-muted-foreground hover:underline"
          >
            ← back to strategy
          </Link>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            Live run
            <span
              className={cn(
                "rounded px-2 py-0.5 text-xs font-medium uppercase",
                statusTone(data.status),
              )}
            >
              {data.status.replace("_", " ")}
            </span>
          </h1>
          <p className="text-xs text-muted-foreground">
            Started {relTime(data.started_at)} · refresh every 3s
          </p>
        </div>
      </header>

      {data.error && (
        <Card>
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-sm text-destructive">Error</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-1">
            <pre className="whitespace-pre-wrap break-words rounded bg-muted/50 p-2 font-mono text-xs">
              {data.error}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Top row — account state */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-sm">Equity</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="font-mono text-2xl">{fmtMoney(data.equity)}</div>
            <div className="text-xs text-muted-foreground">
              cash {fmtMoney(data.cash)} · realized {fmtMoney(data.realized_pnl)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-sm">Positions</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-sm">
            {data.positions.length === 0 ? (
              <div className="text-muted-foreground">No open positions.</div>
            ) : (
              <ul className="space-y-1">
                {data.positions.map((p) => (
                  <li key={p.symbol} className="flex justify-between font-mono text-xs">
                    <span>
                      {p.symbol}{" "}
                      <span className="text-muted-foreground">@ {p.avg_price.toFixed(4)}</span>
                    </span>
                    <span className={cn(p.qty > 0 ? "text-emerald-400" : "text-rose-500")}>
                      {p.qty.toFixed(4)} | {fmtMoney(p.unrealized_pnl)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-sm">Recent fills ({data.recent_fills.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0 text-xs">
            {data.recent_fills.length === 0 ? (
              <div className="text-muted-foreground">No fills yet.</div>
            ) : (
              <ul className="space-y-1">
                {data.recent_fills.slice(0, 5).map((f, i) => (
                  <li key={i} className="flex justify-between font-mono">
                    <span>
                      {f.symbol} {f.side === "buy" ? "BUY" : "SELL"} {f.qty.toFixed(4)}
                    </span>
                    <span className="text-muted-foreground">{relTime(f.ts)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Event log */}
      <Card>
        <CardHeader className="p-4 pb-1">
          <CardTitle className="text-sm">
            Event log <span className="text-muted-foreground">(newest first)</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {data.events.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted-foreground">
              No events yet. The runner emits an event when the strategy queues an order, gets a
              fill/reject, or raises in on_bar. Quiet ticks aren&apos;t logged.
            </p>
          ) : (
            <div className="max-h-[60vh] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-card text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left">When</th>
                    <th className="px-3 py-2 text-left">Kind</th>
                    <th className="px-3 py-2 text-left">Payload</th>
                  </tr>
                </thead>
                <tbody>
                  {data.events.map((e) => (
                    <tr key={e.id} className="border-t border-border/60">
                      <td className="whitespace-nowrap px-3 py-1.5 font-mono text-muted-foreground">
                        {relTime(e.ts)}
                      </td>
                      <td className="px-3 py-1.5">
                        <span
                          className={cn(
                            "rounded px-1.5 py-0.5 font-medium uppercase",
                            eventTone(e.kind),
                          )}
                        >
                          {e.kind}
                        </span>
                      </td>
                      <td className="px-3 py-1.5 font-mono">
                        {Object.entries(e.payload || {})
                          .filter(([, v]) => v !== null && v !== undefined && v !== "")
                          .map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`)
                          .join("  ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
