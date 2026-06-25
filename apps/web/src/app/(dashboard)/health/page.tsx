"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type HealthSummary = {
  scanner: {
    enabled: boolean;
    interval_minutes: number;
    last_run_at: string | null;
    last_status: string | null;
    last_signal_count: number | null;
    last_reason: string | null;
  } | null;
  streams: {
    source: string;
    symbol: string;
    timeframe: string;
    last_bar_ts: string | null;
    lag_seconds: number | null;
  }[];
  worker: { last_heartbeat_at: string | null; lag_seconds: number | null };
  llm: {
    spend_24h: number;
    spend_7d: number;
    spend_30d: number;
    calls_24h: number;
    calls_7d: number;
    by_purpose_30d: { purpose: string; spend_usd: number; calls: number }[];
  };
  live_runs: number;
  paper_accounts: number;
  live_accounts: number;
};

function relTime(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function lagTone(seconds: number | null, warnAfter: number, errAfter: number): string {
  if (seconds == null) return "text-muted-foreground";
  if (seconds > errAfter) return "text-rose-500";
  if (seconds > warnAfter) return "text-amber-500";
  return "text-emerald-500";
}

function StatusPill({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-muted-foreground">never run</span>;
  const tone =
    status === "ok"
      ? "bg-emerald-500/15 text-emerald-500"
      : status === "no_signals" || status === "no_data"
        ? "bg-amber-500/15 text-amber-500"
        : "bg-rose-500/15 text-rose-500";
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium uppercase", tone)}>
      {status.replace("_", " ")}
    </span>
  );
}

function fmtUsd(n: number): string {
  if (n === 0) return "$0";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

export default function HealthPage() {
  const { data, error, isLoading } = useSWR<HealthSummary>("/admin/health", fetcher, {
    refreshInterval: 15_000,
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) {
    const msg = (error as { message?: string; status?: number }).message ?? "Failed";
    const code = (error as { status?: number }).status;
    if (code === 403) {
      return <p className="text-sm text-muted-foreground">Admin only.</p>;
    }
    return <p className="text-sm text-destructive">{msg}</p>;
  }
  if (!data) return null;

  const staleStreams = data.streams.filter((s) => (s.lag_seconds ?? 0) > 300);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">System health</h1>
        <p className="text-sm text-muted-foreground">
          Refreshes every 15s. Stream lag warns &gt;5m, errors &gt;15m.
        </p>
      </header>

      {/* ---- top row: scanner + worker + live runs */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between p-4 pb-2">
            <CardTitle className="text-base">Scanner</CardTitle>
            <StatusPill status={data.scanner?.last_status ?? null} />
          </CardHeader>
          <CardContent className="space-y-1 p-4 pt-2 text-sm">
            {data.scanner ? (
              <>
                <div>
                  <span className="text-muted-foreground">Last run </span>
                  <span className="font-mono">{relTime(data.scanner.last_run_at)}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Signals </span>
                  <span className="font-mono">{data.scanner.last_signal_count ?? "—"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Interval </span>
                  <span className="font-mono">{data.scanner.interval_minutes}m</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Enabled </span>
                  <span
                    className={cn(
                      "font-mono",
                      data.scanner.enabled ? "text-emerald-500" : "text-rose-500",
                    )}
                  >
                    {data.scanner.enabled ? "yes" : "no"}
                  </span>
                </div>
              </>
            ) : (
              <div className="text-muted-foreground">No config row.</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-base">Worker</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 p-4 pt-2 text-sm">
            <div>
              <span className="text-muted-foreground">Last heartbeat </span>
              <span className={cn("font-mono", lagTone(data.worker.lag_seconds, 90, 300))}>
                {relTime(data.worker.last_heartbeat_at)}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground">Lag </span>
              <span className="font-mono">
                {data.worker.lag_seconds != null ? `${data.worker.lag_seconds}s` : "—"}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-base">Accounts & runs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 p-4 pt-2 text-sm">
            <div>
              <span className="text-muted-foreground">Live strategies running </span>
              <span className="font-mono">{data.live_runs}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Paper accounts </span>
              <span className="font-mono">{data.paper_accounts}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Live accounts </span>
              <span className="font-mono">{data.live_accounts}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ---- LLM spend */}
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-base">LLM spend</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4 pt-2 text-sm">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <div>
              <div className="text-[10px] uppercase text-muted-foreground">24h</div>
              <div className="font-mono">{fmtUsd(data.llm.spend_24h)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-muted-foreground">7d</div>
              <div className="font-mono">{fmtUsd(data.llm.spend_7d)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-muted-foreground">30d</div>
              <div className="font-mono">{fmtUsd(data.llm.spend_30d)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-muted-foreground">Calls 24h</div>
              <div className="font-mono">{data.llm.calls_24h}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-muted-foreground">Calls 7d</div>
              <div className="font-mono">{data.llm.calls_7d}</div>
            </div>
          </div>
          {data.llm.by_purpose_30d.length > 0 && (
            <div>
              <div className="mb-1 text-[10px] uppercase text-muted-foreground">
                By purpose (30d)
              </div>
              <table className="w-full text-xs">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="py-1 text-left">Purpose</th>
                    <th className="py-1 text-right">Calls</th>
                    <th className="py-1 text-right">Spend</th>
                  </tr>
                </thead>
                <tbody>
                  {data.llm.by_purpose_30d.map((p) => (
                    <tr key={p.purpose} className="border-t border-border/60">
                      <td className="py-1 font-mono">{p.purpose}</td>
                      <td className="py-1 text-right font-mono">{p.calls}</td>
                      <td className="py-1 text-right font-mono">{fmtUsd(p.spend_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ---- streams */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between p-4 pb-2">
          <CardTitle className="text-base">Streams</CardTitle>
          {staleStreams.length > 0 && (
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] uppercase text-amber-500">
              {staleStreams.length} stale
            </span>
          )}
        </CardHeader>
        <CardContent className="p-4 pt-2 text-sm">
          {data.streams.length === 0 ? (
            <div className="text-muted-foreground">
              No 1m bars in the last 24h. Worker streams probably aren&apos;t connected.
            </div>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="py-1 text-left">Source</th>
                  <th className="py-1 text-left">Symbol</th>
                  <th className="py-1 text-left">TF</th>
                  <th className="py-1 text-right">Last bar</th>
                  <th className="py-1 text-right">Lag</th>
                </tr>
              </thead>
              <tbody>
                {data.streams.map((s) => (
                  <tr
                    key={`${s.source}:${s.symbol}:${s.timeframe}`}
                    className="border-t border-border/60"
                  >
                    <td className="py-1 font-mono">{s.source}</td>
                    <td className="py-1 font-mono">{s.symbol}</td>
                    <td className="py-1 font-mono">{s.timeframe}</td>
                    <td className="py-1 text-right text-muted-foreground">
                      {relTime(s.last_bar_ts)}
                    </td>
                    <td
                      className={cn("py-1 text-right font-mono", lagTone(s.lag_seconds, 300, 900))}
                    >
                      {s.lag_seconds != null ? `${s.lag_seconds}s` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
