"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { api, fetcher } from "@/lib/api";
import { type BacktestRun, fmtPct, statusColor } from "@/lib/backtests";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function BacktestList({ strategyId }: { strategyId: string }) {
  const { data, isLoading, error, mutate } = useSWR<BacktestRun[]>(
    `/backtests/strategies/${strategyId}`,
    fetcher,
    { refreshInterval: 4000 },
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const compareHref = `/backtests/compare?ids=${Array.from(selected).join(",")}`;

  async function deleteSelected() {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (!confirm(`Delete ${ids.length} backtest run(s)? This is permanent.`)) return;
    setDeleting(true);
    try {
      // Fire deletes in parallel; backtests are cheap to cascade-delete.
      await Promise.all(ids.map((id) => api(`/backtests/${id}`, { method: "DELETE" })));
      setSelected(new Set());
      await mutate();
    } catch (e) {
      alert((e as { message?: string }).message ?? "Some deletes failed");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm">Backtest runs</CardTitle>
        {selected.size >= 1 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{selected.size} selected</span>
            {selected.size >= 2 && (
              <Button asChild size="sm" variant="secondary" className="h-7">
                <Link href={compareHref}>Compare</Link>
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-destructive hover:text-destructive"
              onClick={deleteSelected}
              disabled={deleting}
            >
              {deleting ? "…" : "Delete"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7"
              onClick={() => setSelected(new Set())}
            >
              Clear
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-1">
        {isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
        {error && (
          <p className="text-xs text-destructive">
            {(error as { message?: string }).message ?? "Failed to load runs."}
          </p>
        )}
        {data?.length === 0 && <p className="text-xs text-muted-foreground">No runs yet.</p>}
        {data?.map((r) => {
          const checked = selected.has(r.id);
          const canCompare = r.status === "done";
          return (
            <div
              key={r.id}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary/40",
                checked && "bg-secondary/30",
              )}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={!canCompare}
                onChange={() => toggle(r.id)}
                className="h-3.5 w-3.5 accent-current"
                title={canCompare ? "Select to compare" : "Only completed runs can be compared"}
              />
              <Link href={`/backtests/${r.id}`} className="flex flex-1 items-center gap-2">
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                    statusColor(r.status),
                  )}
                >
                  {r.status}
                </span>
                <span className="font-mono text-xs">
                  {r.symbols.join(",")} · {r.timeframe}
                </span>
                <span className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
                  {r.metrics && (
                    <span
                      className={cn(
                        "tabular-nums",
                        r.metrics.total_return >= 0 ? "text-emerald-400" : "text-destructive",
                      )}
                    >
                      {fmtPct(r.metrics.total_return)}
                    </span>
                  )}
                  <span>{new Date(r.created_at).toLocaleString()}</span>
                </span>
              </Link>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
