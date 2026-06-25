"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
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

type SweepResponse = {
  queued: number;
  backtest_run_ids: string[];
  values: number[];
};

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString().slice(0, 16);
}

function isoTodayMidnight(): string {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  return d.toISOString().slice(0, 16);
}

export function SweepForm({ strategyId }: { strategyId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [paramName, setParamName] = useState("");
  const [start, setStart] = useState("10");
  const [stop, setStop] = useState("100");
  const [steps, setSteps] = useState(10);
  const [source, setSource] = useState("binance");
  const [symbols, setSymbols] = useState("BTC-PERP");
  const [timeframe, setTimeframe] = useState("1h");
  const [rangeStart, setRangeStart] = useState(isoDaysAgo(365));
  const [rangeEnd, setRangeEnd] = useState(isoTodayMidnight());
  const [initialCapital, setInitialCapital] = useState("10000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Preview the values we'll spread across.
  const startN = Number(start);
  const stopN = Number(stop);
  const valid = Number.isFinite(startN) && Number.isFinite(stopN) && steps >= 2 && steps <= 50;
  const stepSize = valid ? (stopN - startN) / (steps - 1) : 0;
  const preview = valid
    ? Array.from({ length: steps }, (_, i) => Number((startN + i * stepSize).toFixed(6)))
    : [];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!paramName.trim()) {
      setError("param name is required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api<SweepResponse>(`/backtests/strategies/${strategyId}/sweep`, {
        method: "POST",
        body: JSON.stringify({
          base: {
            source,
            symbols: symbols
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
            timeframe,
            range_start: new Date(rangeStart).toISOString(),
            range_end: new Date(rangeEnd).toISOString(),
            initial_capital: initialCapital,
            params: {},
          },
          param_name: paramName.trim(),
          start: startN,
          stop: stopN,
          steps,
        }),
      });
      setOpen(false);
      // Land on the comparison page; runs will still be pending and the
      // page will revalidate every time a run completes.
      router.push(`/backtests/compare?ids=${res.backtest_run_ids.join(",")}`);
    } catch (e) {
      setError((e as { message?: string }).message ?? "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          Sweep param
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Parameter sweep</DialogTitle>
            <DialogDescription>
              Queues one backtest per value. Strategy reads the param via{" "}
              <code>self.params.get(&quot;{paramName || "your_param"}&quot;)</code>. Lands you on
              the comparison page when submitted.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="param">Param name</Label>
                <Input
                  id="param"
                  value={paramName}
                  onChange={(e) => setParamName(e.target.value)}
                  placeholder="e.g. sma_short"
                  required
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="steps">Steps</Label>
                <Input
                  id="steps"
                  type="number"
                  min={2}
                  max={50}
                  value={steps}
                  onChange={(e) =>
                    setSteps(Math.max(2, Math.min(50, Number(e.target.value) || 10)))
                  }
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="start">Start</Label>
                <Input
                  id="start"
                  type="number"
                  step="any"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="stop">Stop (inclusive)</Label>
                <Input
                  id="stop"
                  type="number"
                  step="any"
                  value={stop}
                  onChange={(e) => setStop(e.target.value)}
                />
              </div>
            </div>

            <div className="rounded bg-muted/30 p-2 text-xs text-muted-foreground">
              {valid ? (
                <>
                  Will queue <span className="font-mono">{preview.length}</span> runs with{" "}
                  <span className="font-mono">{paramName || "<param>"} =</span>{" "}
                  <span className="font-mono">[{preview.join(", ")}]</span>.
                </>
              ) : (
                <span className="text-destructive">Need finite start/stop and 2-50 steps.</span>
              )}
            </div>

            <details className="rounded border p-2 text-sm">
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Backtest config (source, symbols, range)
              </summary>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
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
                  />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="symbols">Symbols (comma-separated)</Label>
                  <Input
                    id="symbols"
                    value={symbols}
                    onChange={(e) => setSymbols(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="r-start">Range start</Label>
                  <Input
                    id="r-start"
                    type="datetime-local"
                    value={rangeStart}
                    onChange={(e) => setRangeStart(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="r-end">Range end</Label>
                  <Input
                    id="r-end"
                    type="datetime-local"
                    value={rangeEnd}
                    onChange={(e) => setRangeEnd(e.target.value)}
                  />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="capital">Initial capital</Label>
                  <Input
                    id="capital"
                    inputMode="decimal"
                    value={initialCapital}
                    onChange={(e) => setInitialCapital(e.target.value)}
                  />
                </div>
              </div>
            </details>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={busy}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy || !valid || !paramName.trim()}>
              {busy ? "Queuing…" : `Queue ${preview.length} runs`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
