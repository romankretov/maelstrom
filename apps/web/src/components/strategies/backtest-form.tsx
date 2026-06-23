"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { BacktestRun } from "@/lib/backtests";
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

export function BacktestForm({ strategyId }: { strategyId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState("binance");
  const [symbols, setSymbols] = useState("BTC-PERP");
  const [timeframe, setTimeframe] = useState("1h");
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
        <Button size="sm">Run backtest</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>New backtest</DialogTitle>
            <DialogDescription>Uses the latest version of this strategy.</DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 py-4 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="source">Source</Label>
              <Input id="source" value={source} onChange={(e) => setSource(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="timeframe">Timeframe</Label>
              <Input
                id="timeframe"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                placeholder="1m / 5m / 15m / 1h / 4h / 1d"
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="symbols">Symbols (comma-separated)</Label>
              <Input
                id="symbols"
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
                placeholder="BTC-PERP,ETH-PERP"
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
