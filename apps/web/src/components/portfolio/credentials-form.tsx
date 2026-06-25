"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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

type CredentialState = {
  has_credentials: boolean;
  wallet_address: string | null;
};

export function CredentialsCard({ accountId }: { accountId: string }) {
  const { mutate } = useSWRConfig();
  const { data } = useSWR<CredentialState>(`/accounts/${accountId}/credentials`, fetcher);
  const [open, setOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [wallet, setWallet] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/accounts/${accountId}/credentials`, {
        method: "POST",
        body: JSON.stringify({ wallet_address: wallet, private_key: privateKey }),
      });
      setOpen(false);
      setPrivateKey("");
      await mutate(`/accounts/${accountId}/credentials`);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    if (!confirm("Clear the encrypted private key for this account? Live runs will fail.")) return;
    try {
      await api(`/accounts/${accountId}/credentials`, { method: "DELETE" });
      await mutate(`/accounts/${accountId}/credentials`);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-4">
        <div className="space-y-0.5">
          <p className="text-sm font-medium">Exchange credentials</p>
          {data?.has_credentials ? (
            <p className="text-xs text-muted-foreground">
              wallet:{" "}
              <span className="font-mono">
                {data.wallet_address?.slice(0, 6)}…{data.wallet_address?.slice(-4)}
              </span>{" "}
              · key encrypted in DB
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              No credentials set. Live trading won&apos;t start without them.
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {data?.has_credentials && (
            <Button
              variant="ghost"
              size="sm"
              disabled={syncing}
              onClick={async () => {
                setSyncing(true);
                try {
                  await api(`/accounts/${accountId}/sync-balance`, { method: "POST" });
                  await mutate(`/accounts/${accountId}/portfolio`);
                  await mutate("/accounts");
                } catch (e) {
                  alert(
                    e instanceof Error
                      ? e.message
                      : String((e as { message?: string }).message ?? "Failed"),
                  );
                } finally {
                  setSyncing(false);
                }
              }}
            >
              {syncing ? "Syncing…" : "Sync balance"}
            </Button>
          )}
          {data?.has_credentials && (
            <Button variant="ghost" size="sm" onClick={clear}>
              Clear
            </Button>
          )}
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button size="sm" variant={data?.has_credentials ? "outline" : "default"}>
                {data?.has_credentials ? "Replace" : "Add credentials"}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <form onSubmit={submit}>
                <DialogHeader>
                  <DialogTitle>Hyperliquid credentials</DialogTitle>
                  <DialogDescription>
                    Pair an <b>agent wallet</b> with your <b>master wallet</b>: the agent&apos;s
                    private key signs trades, but funds live on the master. The private key is
                    encrypted with the VPS master key (libsodium SecretBox) before it touches
                    Postgres. It&apos;s never returned by any API.
                  </DialogDescription>
                </DialogHeader>

                <div className="grid gap-3 py-4">
                  <div className="space-y-1">
                    <Label htmlFor="wallet">Master wallet address</Label>
                    <Input
                      id="wallet"
                      value={wallet}
                      onChange={(e) => setWallet(e.target.value)}
                      placeholder="0x… (the wallet that holds your USDC)"
                      required
                    />
                    <p className="text-[10px] text-muted-foreground">
                      This is the wallet you funded via faucet/deposit — NOT the agent wallet
                      address. We query this address for equity and route orders to it via the
                      agent&apos;s signature.
                    </p>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="key">Agent private key</Label>
                    <Input
                      id="key"
                      type="password"
                      value={privateKey}
                      onChange={(e) => setPrivateKey(e.target.value)}
                      placeholder="0x… (encrypted on submit)"
                      required
                    />
                    <p className="text-[10px] text-muted-foreground">
                      Generate this in the HL UI: Settings → API → &quot;Generate an agent
                      wallet&quot;. The agent can place orders but not withdraw funds.
                    </p>
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
                    {busy ? "Saving…" : "Save (encrypted)"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </CardContent>
    </Card>
  );
}
