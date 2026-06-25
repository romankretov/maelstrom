"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { type Signal, directionTone } from "@/lib/signals";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScannerControl } from "@/components/signals/scanner-control";
import { cn } from "@/lib/utils";

function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(Math.abs(score), 100);
  const pos = score >= 0;
  return (
    <div className="flex h-1.5 w-24 overflow-hidden rounded-full bg-muted">
      <div
        className={cn("h-full", pos ? "bg-emerald-500" : "bg-destructive")}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default function Signals() {
  const { data, isLoading, error } = useSWR<Signal[]>("/signals?limit=100", fetcher, {
    refreshInterval: 60_000,
  });

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Signals</h1>
        <p className="text-sm text-muted-foreground">
          AI-ranked opportunities. Not auto-traded. Adjust cadence below.
        </p>
      </header>

      <ScannerControl />

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && (
        <p className="text-sm text-destructive">
          {(error as { message?: string }).message ?? "Failed to load signals."}
        </p>
      )}
      {data && data.length === 0 && (
        <Card>
          <CardContent className="space-y-1 p-6 text-center text-sm text-muted-foreground">
            <p>No active signals. Check the scanner status above — if the last run says</p>
            <p>
              <code>no_signals</code>, the LLM is finding nothing compelling in the snapshot.
            </p>
            <p className="text-xs">
              Set an Anthropic key in <code>/settings</code> if you haven&apos;t already.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {data?.map((s) => {
          const score = Number(s.score);
          const conf = s.confidence !== null ? Number(s.confidence) : null;
          return (
            <Card key={s.id}>
              <CardHeader className="flex flex-row items-baseline justify-between pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <span className="font-mono">{s.symbol}</span>
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                      directionTone(s.direction),
                    )}
                  >
                    {s.direction}
                  </span>
                </CardTitle>
                <span className="text-xs text-muted-foreground">{relTime(s.ts)}</span>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm leading-snug">{s.rationale}</p>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <ScoreBar score={score} />
                    <span className="font-mono tabular-nums">{score.toFixed(0)}</span>
                  </div>
                  {conf !== null && (
                    <span className="font-mono tabular-nums">conf {(conf * 100).toFixed(0)}%</span>
                  )}
                  {s.horizon && <span>· {s.horizon}</span>}
                </div>
                <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                  <span>{s.source}</span>
                  <span>{s.scanner}</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
