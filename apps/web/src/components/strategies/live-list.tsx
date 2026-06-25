"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import { type LiveStatus, type LiveStrategy, liveStatusColor } from "@/lib/live-strategies";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function isStoppable(s: LiveStatus): boolean {
  return s === "running" || s === "pending_start";
}

export function LiveList({ strategyId }: { strategyId: string }) {
  const { mutate } = useSWRConfig();
  const { data, isLoading, error } = useSWR<LiveStrategy[]>(
    `/live-strategies/strategies/${strategyId}`,
    fetcher,
    { refreshInterval: 3000 },
  );
  const [busy, setBusy] = useState<string | null>(null);

  async function stop(id: string) {
    setBusy(id);
    try {
      await api(`/live-strategies/${id}/stop`, { method: "POST" });
      await mutate(`/live-strategies/strategies/${strategyId}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Live runs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {error && (
          <p className="text-xs text-destructive">
            {(error as { message?: string }).message ?? "Failed to load."}
          </p>
        )}
        {data?.length === 0 && (
          <p className="text-xs text-muted-foreground">Not running anywhere.</p>
        )}
        {data?.map((l) => (
          <div key={l.id} className="flex items-center justify-between rounded-md px-2 py-1.5">
            <div className="flex items-center gap-2 text-sm">
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                  liveStatusColor(l.status),
                )}
              >
                {l.status.replace("_", " ")}
              </span>
              {l.shadow_mode && (
                <span
                  className="rounded bg-violet-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase text-violet-300"
                  title="Shadow mode — broker calls go to shadow_fills only, no real orders"
                >
                  shadow
                </span>
              )}
              <span className="font-mono text-xs">
                {l.symbols.join(",")} · {l.timeframe} · {l.source}
              </span>
              {l.error && (
                <span className="truncate text-xs text-destructive" title={l.error}>
                  {l.error.slice(0, 60)}
                </span>
              )}
            </div>
            {isStoppable(l.status) && (
              <Button
                size="sm"
                variant="ghost"
                className="h-6 text-xs"
                onClick={() => stop(l.id)}
                disabled={busy === l.id}
              >
                {busy === l.id ? "…" : "Stop"}
              </Button>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
