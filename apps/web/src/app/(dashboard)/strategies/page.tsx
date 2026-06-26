"use client";

import { useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Plus } from "lucide-react";
import { fetcher } from "@/lib/api";
import type { Strategy } from "@/lib/strategies";
import type { LiveStatus } from "@/lib/live-strategies";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type LiveRow = {
  id: string;
  strategy_id: string;
  status: LiveStatus;
  realized_pnl: number;
};

function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function fmtMoney(n: number): string {
  if (n === 0) return "$0";
  const sign = n < 0 ? "-" : n > 0 ? "+" : "";
  const abs = Math.abs(n);
  if (abs >= 1000) {
    return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
  return `${sign}$${abs.toFixed(2)}`;
}

type LiveStats = { active: number; totalRuns: number; realized: number };

export default function Strategies() {
  const { data, isLoading, error } = useSWR<Strategy[]>("/strategies", fetcher);
  const { data: live } = useSWR<LiveRow[]>("/live-strategies", fetcher, {
    refreshInterval: 5000,
  });

  // Aggregate live runs by strategy_id so each card can show its live
  // footprint at a glance — # active runs and net realized PnL.
  const liveByStrategy = useMemo(() => {
    const m = new Map<string, LiveStats>();
    for (const r of live ?? []) {
      const cur = m.get(r.strategy_id) ?? { active: 0, totalRuns: 0, realized: 0 };
      cur.totalRuns += 1;
      if (r.status === "running" || r.status === "pending_start") cur.active += 1;
      cur.realized += r.realized_pnl;
      m.set(r.strategy_id, cur);
    }
    return m;
  }, [live]);

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Strategies</h1>
        <Link href="/strategies/new">
          <Button size="sm">
            <Plus className="h-4 w-4" /> New strategy
          </Button>
        </Link>
      </header>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && (
        <p className="text-sm text-destructive">
          {(error as { message?: string }).message ?? "Failed to load strategies."}
        </p>
      )}
      {data && data.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            No strategies yet. Hit <span className="font-medium">New strategy</span> to start.
          </CardContent>
        </Card>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {data?.map((s) => {
          const stats = liveByStrategy.get(s.id);
          return (
            <Link key={s.id} href={`/strategies/${s.id}`}>
              <Card className="h-full transition-colors hover:bg-card/80">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-baseline justify-between gap-2">
                    <span className="truncate">{s.name}</span>
                    {s.latest_version && (
                      <span className="font-mono text-xs text-muted-foreground">
                        v{s.latest_version.version}
                      </span>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1">
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {s.description ?? "—"}
                  </p>
                  <div className="flex flex-wrap items-center justify-between gap-1 text-xs">
                    {stats ? (
                      <span className="flex items-center gap-1.5">
                        {stats.active > 0 && (
                          <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-medium uppercase text-emerald-400">
                            {stats.active} live
                          </span>
                        )}
                        {stats.totalRuns > stats.active && (
                          <span className="text-muted-foreground">
                            {stats.totalRuns - stats.active} stopped
                          </span>
                        )}
                        <span
                          className={cn(
                            "font-mono tabular-nums",
                            stats.realized > 0 && "text-emerald-400",
                            stats.realized < 0 && "text-destructive",
                            stats.realized === 0 && "text-muted-foreground",
                          )}
                        >
                          realized {fmtMoney(stats.realized)}
                        </span>
                      </span>
                    ) : (
                      <span className="text-muted-foreground">no live runs</span>
                    )}
                    <span className="text-muted-foreground">edited {relTime(s.updated_at)}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
