"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type DryRunResponse = {
  compiled: boolean;
  on_init_ran: boolean;
  bars_fed: number;
  orders_queued: number;
  fills: number;
  rejects: number;
  sample_orders: {
    ts: string;
    symbol: string;
    side: string;
    qty: number;
    price: number;
    pnl: number;
    reason: string | null;
  }[];
  last_error: string | null;
};

function Checkbox({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span
        className={cn(
          "inline-flex h-4 w-4 items-center justify-center rounded text-[10px] font-bold",
          ok ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-500",
        )}
      >
        {ok ? "✓" : "✗"}
      </span>
      {label}
    </div>
  );
}

export function DryRunButton({ code }: { code: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DryRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    setResult(null);
    setOpen(true);
    try {
      const res = await api<DryRunResponse>("/strategies/dry-run", {
        method: "POST",
        body: JSON.stringify({
          code,
          source: "hyperliquid",
          symbol: "BTC-PERP",
          timeframe: "1h",
          hours: 24,
        }),
      });
      setResult(res);
    } catch (e) {
      setError((e as { message?: string }).message ?? "Dry-run failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={run} disabled={busy}>
        {busy ? "Dry-running…" : "Dry-run"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Dry-run results</DialogTitle>
            <DialogDescription>
              Ran the current code against the last 24h of BTC-PERP 1h bars from your DB. Nothing
              was persisted; no exchange calls were made.
            </DialogDescription>
          </DialogHeader>

          {busy && <p className="text-sm text-muted-foreground">Running…</p>}
          {error && <p className="text-sm text-destructive">{error}</p>}

          {result && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <Checkbox ok={result.compiled} label="Compiled" />
                <Checkbox ok={result.on_init_ran} label="on_init ran" />
                <Checkbox ok={result.bars_fed > 0} label={`${result.bars_fed} bars fed`} />
                <Checkbox
                  ok={result.last_error === null}
                  label={result.last_error ? "Raised an error" : "No errors"}
                />
              </div>

              <div className="grid grid-cols-3 gap-2 text-sm">
                <div className="rounded border bg-muted/30 p-2">
                  <div className="text-[10px] uppercase text-muted-foreground">Bars fed</div>
                  <div className="font-mono">{result.bars_fed}</div>
                </div>
                <div className="rounded border bg-muted/30 p-2">
                  <div className="text-[10px] uppercase text-muted-foreground">Orders</div>
                  <div className="font-mono">{result.orders_queued}</div>
                </div>
                <div className="rounded border bg-muted/30 p-2">
                  <div className="text-[10px] uppercase text-muted-foreground">Fills (sim)</div>
                  <div className="font-mono">{result.fills}</div>
                </div>
              </div>

              {result.last_error && (
                <div>
                  <div className="text-[10px] uppercase text-muted-foreground">Error</div>
                  <pre className="whitespace-pre-wrap break-words rounded bg-rose-500/10 p-2 font-mono text-xs text-rose-400">
                    {result.last_error}
                  </pre>
                </div>
              )}

              {result.sample_orders.length > 0 && (
                <div>
                  <div className="mb-1 text-[10px] uppercase text-muted-foreground">
                    First {result.sample_orders.length} simulated fills
                  </div>
                  <table className="w-full text-xs">
                    <thead className="text-muted-foreground">
                      <tr>
                        <th className="px-2 py-1 text-left">When</th>
                        <th className="px-2 py-1 text-left">Symbol</th>
                        <th className="px-2 py-1 text-left">Side</th>
                        <th className="px-2 py-1 text-right">Qty</th>
                        <th className="px-2 py-1 text-right">Price</th>
                        <th className="px-2 py-1 text-left">Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.sample_orders.map((o, i) => (
                        <tr key={i} className="border-t border-border/60 font-mono">
                          <td className="px-2 py-1 text-muted-foreground">
                            {new Date(o.ts).toLocaleTimeString()}
                          </td>
                          <td className="px-2 py-1">{o.symbol}</td>
                          <td className="px-2 py-1">{o.side}</td>
                          <td className="px-2 py-1 text-right">{o.qty.toFixed(4)}</td>
                          <td className="px-2 py-1 text-right">{o.price.toFixed(2)}</td>
                          <td className="px-2 py-1 text-muted-foreground">{o.reason ?? ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
