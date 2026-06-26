"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import type { Account } from "@/lib/trading";
import type { LiveStrategy } from "@/lib/live-strategies";
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
import { cn } from "@/lib/utils";

export function RunLiveForm({ strategyId }: { strategyId: string }) {
  const { mutate } = useSWRConfig();
  const { data: accounts } = useSWR<Account[]>("/accounts", fetcher);
  const { data: sources } = useSWR<Source[]>("/markets/sources", fetcher);
  const [open, setOpen] = useState(false);
  const [accountId, setAccountId] = useState<string>("");
  // Source is auto-derived from the selected account's kind: hl
  // accounts force hyperliquid, paper accounts default to whatever's
  // available. User can override but the dropdown removes typos.
  const [source, setSource] = useState<string>("hyperliquid");
  const [symbols, setSymbols] = useState("BTC-PERP");
  const [timeframe, setTimeframe] = useState<Timeframe>("1m");
  const [maxNotional, setMaxNotional] = useState("");
  const [maxPositionQty, setMaxPositionQty] = useState("");
  const [shadowMode, setShadowMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When the user picks an account, derive a sensible source default.
  // Hyperliquid accounts only make sense against the hyperliquid source.
  const selectedAccount = useMemo(
    () => accounts?.find((a) => a.id === (accountId || accounts?.[0]?.id)),
    [accounts, accountId],
  );
  useEffect(() => {
    if (!selectedAccount) return;
    if (selectedAccount.kind.startsWith("live_hl_")) {
      setSource("hyperliquid");
    }
  }, [selectedAccount?.id, selectedAccount?.kind]); // eslint-disable-line react-hooks/exhaustive-deps

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
      if (maxPositionQty.trim()) {
        body.max_position_qty = maxPositionQty.trim();
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
                <select
                  id="source"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  disabled={selectedAccount?.kind.startsWith("live_hl_") ?? false}
                  className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                >
                  {(sources ?? [{ name: "hyperliquid", label: "Hyperliquid" }]).map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.label}
                    </option>
                  ))}
                </select>
                {selectedAccount?.kind.startsWith("live_hl_") && (
                  <p className="text-[10px] text-muted-foreground">
                    Locked to <code>hyperliquid</code> for HL accounts.
                  </p>
                )}
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
                <Input id="symbols" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label className="text-xs uppercase text-muted-foreground">Risk controls</Label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor="max-notional" className="text-xs">
                      Max notional per symbol ($)
                    </Label>
                    <Input
                      id="max-notional"
                      inputMode="decimal"
                      value={maxNotional}
                      onChange={(e) => setMaxNotional(e.target.value)}
                      placeholder="e.g. 5000"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Reject any single order that would push position notional past this cap. Leave
                      blank for no limit.
                    </p>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="max-qty" className="text-xs">
                      Max position quantity
                    </Label>
                    <Input
                      id="max-qty"
                      inputMode="decimal"
                      value={maxPositionQty}
                      onChange={(e) => setMaxPositionQty(e.target.value)}
                      placeholder="e.g. 0.5 (BTC)"
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Reject any order that would push absolute position size past this. Useful when
                      notional cap isn&apos;t precise enough (e.g. price-volatile assets).
                    </p>
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Account-level limits (daily loss %, kill switch) are managed from{" "}
                  <a className="underline" href="/portfolio">
                    Portfolio
                  </a>{" "}
                  and apply to all strategies on the account.
                </p>
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
