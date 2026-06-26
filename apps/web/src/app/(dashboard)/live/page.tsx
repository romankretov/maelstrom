"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import { type LiveStatus, liveStatusColor } from "@/lib/live-strategies";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type LiveRow = {
  id: string;
  strategy_id: string;
  account_id: string;
  source: string;
  symbols: string[];
  timeframe: string;
  status: LiveStatus;
  error: string | null;
  shadow_mode: boolean;
  started_at: string | null;
  stopped_at: string | null;
  created_at: string;
  strategy_name: string | null;
  account_name: string | null;
  account_kind: string | null;
  realized_pnl: number;
};

const STATUS_OPTIONS: { label: string; value: string | null }[] = [
  { label: "Active", value: null },
  { label: "Running", value: "running" },
  { label: "Pending start", value: "pending_start" },
  { label: "Pending stop", value: "pending_stop" },
  { label: "Stopped", value: "stopped" },
  { label: "Failed", value: "failed" },
];

function fmtMoney(n: number): string {
  if (n === 0) return "$0";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1000) {
    return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
  return `${sign}$${abs.toFixed(2)}`;
}

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

export default function LivePage() {
  const { mutate } = useSWRConfig();
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const key =
    "/live-strategies" + (statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "");
  const { data, isLoading, error } = useSWR<LiveRow[]>(key, fetcher, { refreshInterval: 3000 });
  const [busy, setBusy] = useState<string | null>(null);

  async function stop(id: string) {
    setBusy(id);
    try {
      await api(`/live-strategies/${id}/stop`, { method: "POST" });
      await mutate(key);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Live runs</h1>
          <p className="text-sm text-muted-foreground">
            Every live strategy you can see, across all accounts. Refreshes every 3s.
          </p>
        </div>
        <div className="flex gap-1">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => setStatusFilter(s.value)}
              className={cn(
                "rounded px-2 py-1 text-xs",
                statusFilter === s.value
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-secondary/60",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
      </header>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && (
        <p className="text-sm text-destructive">
          {(error as { message?: string }).message ?? "Failed to load"}
        </p>
      )}
      {data && data.length === 0 && (
        <Card>
          <CardContent className="p-6 text-center text-sm text-muted-foreground">
            Nothing matches that filter.
          </CardContent>
        </Card>
      )}
      {data && data.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">{data.length} runs</CardTitle>
            <span className="text-xs text-muted-foreground">
              net realized{" "}
              <span
                className={cn(
                  "font-mono",
                  data.reduce((acc, r) => acc + r.realized_pnl, 0) < 0 && "text-destructive",
                )}
              >
                {fmtMoney(data.reduce((acc, r) => acc + r.realized_pnl, 0))}
              </span>
            </span>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-left">Strategy</th>
                    <th className="hidden px-3 py-2 text-left sm:table-cell">Account</th>
                    <th className="hidden px-3 py-2 text-left md:table-cell">Symbols · TF</th>
                    <th className="px-3 py-2 text-right">Realized</th>
                    <th className="hidden px-3 py-2 text-right md:table-cell">Started</th>
                    <th className="px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((r) => (
                    <tr key={r.id} className="border-t border-border/60">
                      <td className="px-3 py-1.5">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={cn(
                              "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                              liveStatusColor(r.status),
                            )}
                          >
                            {r.status.replace("_", " ")}
                          </span>
                          {r.shadow_mode && (
                            <span
                              className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase text-violet-300"
                              title="Shadow mode — broker calls go to shadow_fills only"
                            >
                              shadow
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-1.5">
                        {r.strategy_name ? (
                          <Link
                            href={`/strategies/${r.strategy_id}`}
                            className="font-mono hover:underline"
                          >
                            {r.strategy_name}
                          </Link>
                        ) : (
                          <span className="font-mono text-muted-foreground">
                            {r.strategy_id.slice(0, 8)}
                          </span>
                        )}
                      </td>
                      <td className="hidden px-3 py-1.5 text-xs sm:table-cell">
                        <div className="flex flex-col">
                          <span className="font-mono">{r.account_name ?? "—"}</span>
                          <span className="text-[10px] text-muted-foreground">
                            {r.account_kind ?? ""}
                          </span>
                        </div>
                      </td>
                      <td className="hidden px-3 py-1.5 font-mono text-xs md:table-cell">
                        {r.symbols.join(",")} · {r.timeframe} · {r.source}
                      </td>
                      <td
                        className={cn(
                          "px-3 py-1.5 text-right font-mono tabular-nums",
                          r.realized_pnl >= 0 ? "text-emerald-400" : "text-destructive",
                        )}
                      >
                        {fmtMoney(r.realized_pnl)}
                      </td>
                      <td className="hidden px-3 py-1.5 text-right text-xs text-muted-foreground md:table-cell">
                        {relTime(r.started_at ?? r.created_at)}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        {(r.status === "running" || r.status === "pending_start") && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-6 text-xs"
                            disabled={busy === r.id}
                            onClick={() => stop(r.id)}
                          >
                            {busy === r.id ? "…" : "Stop"}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
