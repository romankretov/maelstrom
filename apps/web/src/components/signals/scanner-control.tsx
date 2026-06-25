"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, fetcher } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type ScannerConfig = {
  interval_minutes: number;
  enabled: boolean;
  last_run_at: string | null;
  last_status: string | null;
  last_signal_count: number | null;
  last_reason: string | null;
  last_call_id: string | null;
};

const INTERVAL_OPTIONS = [
  { value: 5, label: "Every 5 min" },
  { value: 15, label: "Every 15 min" },
  { value: 30, label: "Every 30 min" },
  { value: 60, label: "Every hour" },
  { value: 120, label: "Every 2 hours" },
  { value: 240, label: "Every 4 hours" },
  { value: 1440, label: "Once a day" },
];

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

export function ScannerControl() {
  const { data, mutate, error } = useSWR<ScannerConfig>("/signals/scanner-config", fetcher, {
    refreshInterval: 10_000,
  });
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const patch = async (body: Partial<ScannerConfig>) => {
    setBusy(true);
    setActionError(null);
    try {
      const next = await api<ScannerConfig>("/signals/scanner-config", {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      await mutate(next, { revalidate: false });
    } catch (e) {
      setActionError((e as { message?: string }).message ?? "Update failed");
    } finally {
      setBusy(false);
    }
  };

  const runNow = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await api<{ job_id: string }>("/signals/scanner-config/run-now", { method: "POST" });
      // Give the worker ~3s to actually run before refreshing.
      setTimeout(() => void mutate(), 3000);
    } catch (e) {
      setActionError((e as { message?: string }).message ?? "Trigger failed");
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-destructive">
          Failed to load scanner config: {(error as { message?: string }).message ?? "unknown"}
        </CardContent>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card>
        <CardContent className="p-4 text-sm text-muted-foreground">Loading scanner…</CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 p-4 pb-2">
        <CardTitle className="text-base">Scanner control</CardTitle>
        <StatusPill status={data.last_status} />
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-2 text-sm">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Last run
            </div>
            <div className="font-mono">{relTime(data.last_run_at)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Signals (last run)
            </div>
            <div className="font-mono">{data.last_signal_count ?? "—"}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Interval
            </div>
            <div className="font-mono">{data.interval_minutes}m</div>
          </div>
        </div>

        {data.last_reason && (
          <details className="rounded border bg-muted/30 p-2 text-xs">
            <summary className="cursor-pointer text-muted-foreground">Last run details</summary>
            <pre className="mt-1 whitespace-pre-wrap break-words">{data.last_reason}</pre>
          </details>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <select
            disabled={busy}
            value={data.interval_minutes}
            onChange={(e) => void patch({ interval_minutes: Number(e.target.value) })}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            {INTERVAL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          <Button
            type="button"
            variant={data.enabled ? "secondary" : "default"}
            size="sm"
            disabled={busy}
            onClick={() => void patch({ enabled: !data.enabled })}
          >
            {data.enabled ? "Disable" : "Enable"}
          </Button>

          <Button type="button" size="sm" disabled={busy} onClick={() => void runNow()}>
            {busy ? "…" : "Run now"}
          </Button>
        </div>

        {actionError && <p className="text-xs text-destructive">{actionError}</p>}
      </CardContent>
    </Card>
  );
}
