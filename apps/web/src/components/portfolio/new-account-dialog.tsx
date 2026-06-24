"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import type { Account } from "@/lib/trading";
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

type Kind = "paper" | "live_hl_testnet" | "live_hl_main";

const KIND_OPTIONS: { id: Kind; label: string; description: string }[] = [
  {
    id: "paper",
    label: "Paper",
    description:
      "Simulated fills at last close. No funds at risk. Default starting capital is virtual.",
  },
  {
    id: "live_hl_testnet",
    label: "Hyperliquid testnet",
    description:
      "Real orders on the Hyperliquid testnet — uses test USDC. Same code path as mainnet so you can rehearse without funds at risk.",
  },
  {
    id: "live_hl_main",
    label: "Hyperliquid mainnet",
    description:
      "Real money. Server requires MAELSTROM_ALLOW_MAINNET=1 set on the VPS to allow this kind.",
  },
];

export function NewAccountDialog({ onCreated }: { onCreated?: (a: Account) => void }) {
  const { mutate } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Kind>("paper");
  const [capital, setCapital] = useState("10000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (kind === "live_hl_main") {
      const ok = confirm(
        "Mainnet accounts use real money. Continue?\n\n" +
          "Reminder: you also need MAELSTROM_ALLOW_MAINNET=1 set on the VPS — otherwise the server will refuse.",
      );
      if (!ok) return;
    }
    setBusy(true);
    setError(null);
    try {
      // For live accounts we omit starting_capital — the server fetches it
      // from the exchange when credentials are added (see set_credentials).
      const body: Record<string, unknown> = { name, kind };
      if (kind === "paper") body.starting_capital = capital;
      const a = await api<Account>("/accounts", {
        method: "POST",
        body: JSON.stringify(body),
      });
      await mutate("/accounts");
      setOpen(false);
      setName("");
      setCapital("10000");
      setKind("paper");
      onCreated?.(a);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  const isLive = kind !== "paper";
  const isMainnet = kind === "live_hl_main";

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">+ New account</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Create trading account</DialogTitle>
            <DialogDescription>
              Paper for backtests + dry runs, Hyperliquid for real execution. You can have many
              accounts side-by-side and run different strategies on each.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-4">
            <div className="space-y-2">
              <Label>Kind</Label>
              <div className="space-y-2">
                {KIND_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setKind(opt.id)}
                    className={cn(
                      "flex w-full flex-col items-start rounded-md border px-3 py-2 text-left",
                      kind === opt.id
                        ? "border-foreground bg-secondary/40"
                        : "hover:bg-secondary/20",
                    )}
                  >
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <span>{opt.label}</span>
                      {opt.id === "live_hl_main" && (
                        <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-[10px] uppercase text-destructive">
                          real money
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">{opt.description}</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={120}
                placeholder={isLive ? "hl-testnet (or your wallet label)" : "Paper account"}
              />
            </div>

            {!isLive && (
              <div className="space-y-1">
                <Label htmlFor="capital">Starting capital (USDT)</Label>
                <Input
                  id="capital"
                  inputMode="decimal"
                  value={capital}
                  onChange={(e) => setCapital(e.target.value)}
                  required
                />
              </div>
            )}
            {isLive && (
              <p className="text-xs text-muted-foreground">
                Maelstrom will auto-fetch your Hyperliquid equity once you add credentials and use
                that as the return-% baseline. No need to guess a number.
              </p>
            )}

            {isLive && (
              <div className="space-y-1 rounded-md border border-yellow-500/30 bg-yellow-500/5 p-3 text-xs">
                <div className="flex items-center gap-2 font-medium text-yellow-400">
                  <AlertTriangle className="h-3 w-3" /> Next step after Create
                </div>
                <p className="text-muted-foreground">
                  1. Add Hyperliquid <b>wallet address</b> + <b>private key</b> via the Credentials
                  card (encrypted at rest).
                </p>
                <p className="text-muted-foreground">
                  2. Open any strategy → <b>Run live</b> → pick this account.
                </p>
                <p className="text-muted-foreground">
                  3. Set <b>Max notional per symbol</b> on the run-live form for a hard safety belt.
                </p>
                {isMainnet && (
                  <p className="font-medium text-destructive">
                    Mainnet requires admin role AND MAELSTROM_ALLOW_MAINNET=1 on the VPS. Otherwise
                    Create returns 403.
                  </p>
                )}
              </div>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={busy}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
