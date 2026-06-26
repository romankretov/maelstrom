"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { api, fetcher } from "@/lib/api";
import type { BacktestRun } from "@/lib/backtests";
import type { Source, Timeframe } from "@/lib/markets";
import { TIMEFRAMES } from "@/lib/markets";
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
import { SymbolAutocomplete } from "@/components/symbol-autocomplete";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString().slice(0, 16); // datetime-local format
}

function isoTodayMidnight(): string {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString().slice(0, 16);
}

export function BacktestForm({
  strategyId,
  dirty = false,
  onSaveFirst,
}: {
  strategyId: string;
  /** True if there are unsaved code edits in the parent editor. */
  dirty?: boolean;
  /** Called before submit when `dirty` is true. Must save a new version. */
  onSaveFirst?: () => Promise<void>;
}) {
  const router = useRouter();
  const { data: sources } = useSWR<Source[]>("/markets/sources", fetcher);
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState("hyperliquid");
  const [symbols, setSymbols] = useState("BTC-PERP");
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [rangeStart, setRangeStart] = useState(isoDaysAgo(365));
  const [rangeEnd, setRangeEnd] = useState(isoTodayMidnight());
  const [initialCapital, setInitialCapital] = useState("10000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // If the parent editor has unsaved changes, persist them as a new
      // version first so the backtest runs against what's actually on
      // screen rather than the stale latest version.
      if (dirty && onSaveFirst) {
        await onSaveFirst();
      }
      const run = await api<BacktestRun>(`/backtests/strategies/${strategyId}`, {
        method: "POST",
        body: JSON.stringify({
          source,
          symbols: symbols
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          timeframe,
          range_start: new Date(rangeStart).toISOString(),
          range_end: new Date(rangeEnd).toISOString(),
          initial_capital: initialCapital,
        }),
      });
      setOpen(false);
      router.push(`/backtests/${run.id}`);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : String((e as { message?: string }).message ?? "Failed to start backtest"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">{dirty ? "Save & backtest" : "Run backtest"}</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>New backtest</DialogTitle>
            <DialogDescription>
              {dirty
                ? "Your editor has unsaved changes — Run will save a new version first, then backtest against it."
                : "Uses the latest saved version of this strategy."}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 py-4 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="source">Source</Label>
              <select
                id="source"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
              >
                {(sources ?? [{ name: "hyperliquid", label: "Hyperliquid" }]).map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="timeframe">Timeframe</Label>
              <select
                id="timeframe"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value as Timeframe)}
                className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
              >
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="symbols">Symbols (comma-separated)</Label>
              <SymbolAutocomplete
                id="symbols"
                source={source}
                value={symbols}
                onChange={setSymbols}
                multi
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="start">Range start (UTC)</Label>
              <Input
                id="start"
                type="datetime-local"
                value={rangeStart}
                onChange={(e) => setRangeStart(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="end">Range end (UTC)</Label>
              <Input
                id="end"
                type="datetime-local"
                value={rangeEnd}
                onChange={(e) => setRangeEnd(e.target.value)}
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="capital">Initial capital (USDT)</Label>
              <Input
                id="capital"
                inputMode="decimal"
                value={initialCapital}
                onChange={(e) => setInitialCapital(e.target.value)}
              />
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={busy}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy}>
              {busy ? "Submitting…" : "Run"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
