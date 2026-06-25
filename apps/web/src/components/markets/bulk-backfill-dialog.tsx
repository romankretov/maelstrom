"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import { TIMEFRAMES, type Instrument, type Timeframe } from "@/lib/markets";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type BulkResponse = { queued: number; job_ids: string[] };

const PRESET_RANGES: { label: string; days: number }[] = [
  { label: "7d", days: 7 },
  { label: "30d", days: 30 },
  { label: "90d", days: 90 },
  { label: "1y", days: 365 },
  { label: "2y", days: 730 },
];

export function BulkBackfillDialog({ source }: { source: string }) {
  const { mutate } = useSWRConfig();
  const { data: instruments } = useSWR<Instrument[]>(
    `/markets/instruments?source=${source}&limit=200`,
    fetcher,
  );

  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [selectedSymbols, setSelectedSymbols] = useState<Set<string>>(new Set());
  const [selectedTfs, setSelectedTfs] = useState<Set<Timeframe>>(new Set(["1h"]));
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BulkResponse | null>(null);

  const filtered =
    instruments?.filter((i) => !filter || i.symbol.toLowerCase().includes(filter.toLowerCase())) ??
    [];
  const jobsCount = selectedSymbols.size * selectedTfs.size;

  function toggleSym(sym: string) {
    setSelectedSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym);
      else next.add(sym);
      return next;
    });
  }
  function toggleTf(tf: Timeframe) {
    setSelectedTfs((prev) => {
      const next = new Set(prev);
      if (next.has(tf)) next.delete(tf);
      else next.add(tf);
      return next;
    });
  }
  function selectTopN(n: number) {
    setSelectedSymbols(new Set(filtered.slice(0, n).map((i) => i.symbol)));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const until = new Date();
      const since = new Date(until.getTime() - days * 86400 * 1000);
      const res = await api<BulkResponse>("/markets/backfill/bulk", {
        method: "POST",
        body: JSON.stringify({
          source,
          symbols: Array.from(selectedSymbols),
          timeframes: Array.from(selectedTfs),
          range_start: since.toISOString(),
          range_end: until.toISOString(),
        }),
      });
      setResult(res);
      // Nudge the markets page to refresh once any of these complete.
      void mutate((k) => typeof k === "string" && k.startsWith(`/markets/ohlcv?source=${source}`));
    } catch (e) {
      setError((e as { message?: string }).message ?? "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) {
          setResult(null);
          setError(null);
        }
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="h-8">
          Bulk backfill
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Bulk backfill ({source})</DialogTitle>
          <DialogDescription>
            Queue one job per symbol × timeframe. Cap is 100 jobs per call.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Timeframes</Label>
              <div className="flex flex-wrap gap-1">
                {TIMEFRAMES.map((tf) => {
                  const on = selectedTfs.has(tf);
                  return (
                    <button
                      key={tf}
                      type="button"
                      onClick={() => toggleTf(tf)}
                      className={cn(
                        "rounded px-2 py-1 font-mono text-xs",
                        on
                          ? "bg-secondary text-secondary-foreground"
                          : "text-muted-foreground hover:bg-secondary/60",
                      )}
                    >
                      {tf}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1">
              <Label>Lookback (days)</Label>
              <div className="flex flex-wrap items-center gap-1">
                {PRESET_RANGES.map((p) => (
                  <button
                    key={p.label}
                    type="button"
                    onClick={() => setDays(p.days)}
                    className={cn(
                      "rounded px-2 py-1 text-xs",
                      days === p.days
                        ? "bg-secondary text-secondary-foreground"
                        : "text-muted-foreground hover:bg-secondary/60",
                    )}
                  >
                    {p.label}
                  </button>
                ))}
                <Input
                  type="number"
                  min={1}
                  max={3650}
                  value={days}
                  onChange={(e) =>
                    setDays(Math.max(1, Math.min(3650, Number(e.target.value) || 30)))
                  }
                  className="ml-1 h-7 w-20"
                />
              </div>
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Label className="flex-1">Symbols ({selectedSymbols.size} selected)</Label>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 text-xs"
                onClick={() => selectTopN(10)}
              >
                Top 10
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 text-xs"
                onClick={() => selectTopN(20)}
              >
                Top 20
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-6 text-xs"
                onClick={() => setSelectedSymbols(new Set())}
              >
                Clear
              </Button>
            </div>
            <Input
              placeholder="Filter — BTC, ETH, …"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="h-8"
            />
            <div className="max-h-56 overflow-y-auto rounded border">
              {filtered.length === 0 && (
                <p className="p-3 text-xs text-muted-foreground">No instruments match.</p>
              )}
              {filtered.map((i) => {
                const on = selectedSymbols.has(i.symbol);
                return (
                  <button
                    key={i.symbol}
                    type="button"
                    onClick={() => toggleSym(i.symbol)}
                    className={cn(
                      "flex w-full items-center justify-between px-3 py-1.5 text-left text-sm",
                      on ? "bg-secondary" : "hover:bg-secondary/40",
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <input type="checkbox" readOnly checked={on} className="h-3.5 w-3.5" />
                      <span className="font-mono text-xs">{i.symbol}</span>
                    </span>
                    <span className="text-[10px] text-muted-foreground">{i.quote}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="rounded bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            Will queue <span className="font-mono">{jobsCount}</span> job(s)
            {jobsCount > 100 && (
              <span className="ml-1 text-destructive">— over the 100-job cap</span>
            )}
            .
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {result && (
            <p className="text-sm text-emerald-400">
              Queued {result.queued} jobs. Track with{" "}
              <code>GET /markets/backfill/{`{job_id}`}</code>.
            </p>
          )}
        </div>

        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="ghost" disabled={busy}>
              Close
            </Button>
          </DialogClose>
          <Button
            type="button"
            onClick={submit}
            disabled={busy || jobsCount === 0 || jobsCount > 100}
          >
            {busy ? "Queuing…" : `Queue ${jobsCount}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
