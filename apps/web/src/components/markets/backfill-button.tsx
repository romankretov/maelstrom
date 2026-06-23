"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import type { Timeframe } from "@/lib/markets";
import { Button } from "@/components/ui/button";

type BackfillJob = {
  id: string;
  status: "pending" | "running" | "done" | "failed";
  bars_written: number;
  error: string | null;
};

const TIMEFRAME_DAYS: Record<Timeframe, number> = {
  "1m": 7,
  "5m": 30,
  "15m": 90,
  "1h": 365,
  "4h": 730,
  "1d": 1825,
};

export function BackfillButton({
  source,
  symbol,
  timeframe,
}: {
  source: string;
  symbol: string;
  timeframe: Timeframe;
}) {
  const { mutate } = useSWRConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pollUntilDone(jobId: string) {
    for (let i = 0; i < 60; i++) {
      // up to ~2 min
      const job = await api<BackfillJob>(`/markets/backfill/${jobId}`);
      if (job.status === "done") return job;
      if (job.status === "failed") throw new Error(job.error ?? "backfill failed");
      await new Promise((r) => setTimeout(r, 2000));
    }
    throw new Error("backfill timed out");
  }

  async function handleClick() {
    setBusy(true);
    setError(null);
    try {
      const days = TIMEFRAME_DAYS[timeframe];
      const until = new Date();
      const since = new Date(until.getTime() - days * 86400 * 1000);
      const job = await api<BackfillJob>("/markets/backfill", {
        method: "POST",
        body: JSON.stringify({
          source,
          symbol,
          timeframe,
          range_start: since.toISOString(),
          range_end: until.toISOString(),
        }),
      });
      await pollUntilDone(job.id);
      // Re-fetch the chart bars now that the DB has data.
      await mutate(
        (k) =>
          typeof k === "string" && k.startsWith(`/markets/ohlcv?source=${source}&symbol=${symbol}`),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={handleClick} disabled={busy} variant="outline" size="sm" className="h-8">
        {busy ? "Backfilling…" : `Backfill ${TIMEFRAME_DAYS[timeframe]}d`}
      </Button>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
}
