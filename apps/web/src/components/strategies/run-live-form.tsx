"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import type { Account } from "@/lib/trading";
import type { LiveStrategy } from "@/lib/live-strategies";
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

export function RunLiveForm({ strategyId }: { strategyId: string }) {
  const { mutate } = useSWRConfig();
  const { data: accounts } = useSWR<Account[]>("/accounts", fetcher);
  const [open, setOpen] = useState(false);
  const [accountId, setAccountId] = useState<string>("");
  const [source, setSource] = useState("binance");
  const [symbols, setSymbols] = useState("BTC-PERP");
  const [timeframe, setTimeframe] = useState("1m");
  const [maxNotional, setMaxNotional] = useState("");
  const [shadowMode, setShadowMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const acc = accountId || accounts?.[0]?.id;
      if (!acc) throw new Error("No account selected");
      const body: Record<string, unknown> = {
        account_id: acc,
        source,
        symbols: symbols
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        timeframe,
      };
      if (maxNotional.trim()) {
        body.max_notional_per_symbol = maxNotional.trim();
      }
      body.shadow_mode = shadowMode;
      await api<LiveStrategy>(`/live-strategies/strategies/${strategyId}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setOpen(false);
      await mutate(`/live-strategies/strategies/${strategyId}`);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  const noAccounts = accounts && accounts.length === 0;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" disabled={noAccounts}>
          {noAccounts ? "Create an account first" : "Run live"}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Run strategy live</DialogTitle>
            <DialogDescription>
              Live orders route through the broker. Paper accounts simulate fills at last close +
              slippage. Live (Hyperliquid) accounts hit P3.3 once it ships.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 py-4">
            <div className="space-y-1">
              <Label>Account</Label>
              <div className="flex flex-wrap gap-1">
                {(accounts ?? []).map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => setAccountId(a.id)}
                    className={cn(
                      "rounded-md border px-2 py-1 font-mono text-xs",
                      (accountId || accounts?.[0]?.id) === a.id
                        ? "border-foreground bg-secondary"
                        : "text-muted-foreground hover:bg-secondary/40",
                    )}
                  >
                    {a.name}
                    <span className="ml-2 text-[10px] uppercase text-muted-foreground">
                      {a.kind === "paper" ? "paper" : a.kind.replace("live_hl_", "hl ")}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
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
                <Input id="symbols" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="max-notional">Max notional per symbol ($, optional)</Label>
                <Input
                  id="max-notional"
                  inputMode="decimal"
                  value={maxNotional}
                  onChange={(e) => setMaxNotional(e.target.value)}
                  placeholder="e.g. 5000 — reject if a fill would exceed this"
                />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <label className="flex items-start gap-2 rounded-md border p-3 text-sm">
                  <input
                    type="checkbox"
                    checked={shadowMode}
                    onChange={(e) => setShadowMode(e.target.checked)}
                    className="mt-0.5 h-4 w-4"
                  />
                  <span>
                    <span className="font-medium">Shadow mode</span>
                    <span className="block text-xs text-muted-foreground">
                      Subscribe to the live bar stream but record would-be fills to{" "}
                      <code>shadow_fills</code> only — never touches the broker or real positions.
                      Useful for validating against live market microstructure without capital risk.
                    </span>
                  </span>
                </label>
              </div>
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
              {busy ? "Starting…" : "Start"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
