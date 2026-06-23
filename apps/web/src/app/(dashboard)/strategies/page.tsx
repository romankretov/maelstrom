"use client";

import Link from "next/link";
import useSWR from "swr";
import { Plus } from "lucide-react";
import { fetcher } from "@/lib/api";
import type { Strategy } from "@/lib/strategies";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

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

export default function Strategies() {
  const { data, isLoading, error } = useSWR<Strategy[]>("/strategies", fetcher);
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
        {data?.map((s) => (
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
                <p className="line-clamp-2 text-sm text-muted-foreground">{s.description ?? "—"}</p>
                <p className="text-xs text-muted-foreground">edited {relTime(s.updated_at)}</p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
