"use client";

import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, downloadAuthed, fetcher } from "@/lib/api";
import { fmtMoney, fmtNum, fmtPct } from "@/lib/backtests";
import { type Account, type PortfolioSummary, num } from "@/lib/trading";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AccountEquityChart } from "@/components/portfolio/account-equity-chart";
import { CredentialsCard } from "@/components/portfolio/credentials-form";
import { PnlAttributionCard } from "@/components/portfolio/pnl-attribution-card";
import { NewAccountDialog } from "@/components/portfolio/new-account-dialog";
import { cn } from "@/lib/utils";

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "good" | "bad" | "muted";
}) {
  return (
    <Card>
      <CardHeader className="pb-1">
        <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent
        className={cn(
          "pt-0 font-mono text-xl tabular-nums",
          tone === "good" && "text-emerald-400",
          tone === "bad" && "text-destructive",
          tone === "muted" && "text-muted-foreground",
        )}
      >
        {value}
      </CardContent>
    </Card>
  );
}

function CreateAccountCard({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("Paper account");
  const [capital, setCapital] = useState("10000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api<Account>("/accounts", {
        method: "POST",
        body: JSON.stringify({ name, kind: "paper", starting_capital: capital }),
      });
      onCreated();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>Create paper account</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={submit}>
          <div className="space-y-1">
            <Label htmlFor="name">Name</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
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
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Creating…" : "Create"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function PortfolioPage() {
  const { mutate } = useSWRConfig();
  const { data: accounts, isLoading: aLoad } = useSWR<Account[]>("/accounts", fetcher);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Per-row busy marker: e.g. "close:BTC-PERP" while a manual close is in flight.
  const [busy, setBusy] = useState<string | false>(false);

  // Auto-pick first account once they load.
  useEffect(() => {
    if (accounts && accounts.length > 0 && !selectedId) {
      setSelectedId(accounts[0].id);
    }
  }, [accounts, selectedId]);

  const { data: portfolio, isLoading: pLoad } = useSWR<PortfolioSummary>(
    selectedId ? `/accounts/${selectedId}/portfolio` : null,
    fetcher,
    { refreshInterval: 5000 },
  );

  if (aLoad) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (!accounts || accounts.length === 0) {
    return (
      <div className="space-y-4">
        <header className="flex items-center justify-between gap-2">
          <h1 className="text-2xl font-semibold">Portfolio</h1>
          <NewAccountDialog onCreated={(a) => setSelectedId(a.id)} />
        </header>
        <p className="text-sm text-muted-foreground">
          You don&apos;t have any accounts yet. Click <b>New account</b> above, or use the quick
          paper-account form below.
        </p>
        <CreateAccountCard onCreated={() => mutate("/accounts")} />
      </div>
    );
  }

  const selected = accounts.find((a) => a.id === selectedId);

  async function closePosition(symbol: string) {
    if (!selectedId) return;
    if (!confirm(`Submit a market order to close your ${symbol} position?`)) return;
    setBusy(`close:${symbol}`);
    try {
      await api(`/accounts/${selectedId}/positions/${encodeURIComponent(symbol)}/close`, {
        method: "POST",
      });
      // Give the worker a moment to land the fill, then refresh.
      setTimeout(
        () =>
          void Promise.all([
            mutate(`/accounts/${selectedId}/portfolio`),
            mutate(`/accounts/${selectedId}/pnl-attribution`),
          ]),
        1500,
      );
    } catch (e) {
      alert(
        e instanceof Error
          ? e.message
          : String((e as { message?: string }).message ?? "Close failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  async function killOrUnkill(kill: boolean) {
    if (!selectedId) return;
    const verb = kill ? "kill" : "unkill";
    if (kill && !confirm("Halt ALL strategies on this account and block new orders?")) return;
    try {
      await api(`/accounts/${selectedId}/${verb}`, { method: "POST" });
      await Promise.all([mutate("/accounts"), mutate(`/accounts/${selectedId}/portfolio`)]);
    } catch (e) {
      alert(
        e instanceof Error
          ? e.message
          : String((e as { message?: string }).message ?? `${verb} failed`),
      );
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Portfolio</h1>
        <div className="flex flex-wrap items-center gap-1">
          {accounts.map((a) => (
            <Button
              key={a.id}
              variant={a.id === selectedId ? "default" : "ghost"}
              size="sm"
              className="h-8"
              onClick={() => setSelectedId(a.id)}
            >
              <span className="font-mono text-xs">{a.name}</span>
              <span className="ml-2 rounded bg-secondary px-1 text-[10px] uppercase text-muted-foreground">
                {a.kind === "paper" ? "paper" : a.kind.replace("live_hl_", "hl ")}
              </span>
              {a.killed && (
                <span className="ml-1 rounded bg-destructive px-1 text-[10px] uppercase text-destructive-foreground">
                  killed
                </span>
              )}
            </Button>
          ))}
          <NewAccountDialog onCreated={(a) => setSelectedId(a.id)} />
        </div>
      </header>

      {selected?.killed && (
        <div className="flex items-center justify-between gap-3 rounded-md border border-destructive bg-destructive/10 px-4 py-3">
          <div className="text-sm">
            <p className="font-medium text-destructive">Account killed</p>
            <p className="text-xs text-muted-foreground">
              All running strategies are pending_stop. New orders are rejected at the broker.
            </p>
          </div>
          <Button variant="destructive" size="sm" onClick={() => killOrUnkill(false)}>
            Unkill (admin)
          </Button>
        </div>
      )}

      {selected && !selected.killed && (
        <div className="flex justify-end">
          <Button
            variant="destructive"
            size="sm"
            className="h-8"
            onClick={() => killOrUnkill(true)}
          >
            Kill account
          </Button>
        </div>
      )}

      {selected && selected.kind !== "paper" && <CredentialsCard accountId={selected.id} />}

      {selected && <AccountEquityChart accountId={selected.id} />}

      {pLoad && <p className="text-sm text-muted-foreground">Loading portfolio…</p>}
      {portfolio && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Equity" value={fmtMoney(num(portfolio.equity))} />
            <Metric
              label="Total return"
              value={fmtPct(portfolio.total_return)}
              tone={portfolio.total_return >= 0 ? "good" : "bad"}
            />
            <Metric label="Cash" value={fmtMoney(num(portfolio.cash))} tone="muted" />
            <Metric label="Open positions" value={portfolio.open_positions} />
            <Metric
              label="Realized PnL"
              value={fmtMoney(num(portfolio.realized_pnl))}
              tone={num(portfolio.realized_pnl) >= 0 ? "good" : "bad"}
            />
            <Metric
              label="Unrealized PnL"
              value={fmtMoney(num(portfolio.unrealized_pnl))}
              tone={num(portfolio.unrealized_pnl) >= 0 ? "good" : "bad"}
            />
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Open positions</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-left">Symbol</th>
                      <th className="px-3 py-2 text-right">Qty</th>
                      <th className="px-3 py-2 text-right">Avg price</th>
                      <th className="px-3 py-2 text-right">Last</th>
                      <th className="px-3 py-2 text-right">Unrealized</th>
                      <th className="px-3 py-2 text-right">Realized</th>
                      <th className="px-3 py-2 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.positions
                      .filter((p) => num(p.qty) !== 0)
                      .map((p) => {
                        const qty = num(p.qty);
                        const avg = num(p.avg_price);
                        const last = num(p.last_price);
                        const ur =
                          last === 0 ? 0 : qty > 0 ? (last - avg) * qty : (avg - last) * -qty;
                        return (
                          <tr key={p.symbol} className="border-t text-xs">
                            <td className="px-3 py-1 font-mono">{p.symbol}</td>
                            <td
                              className={cn(
                                "px-3 py-1 text-right font-mono tabular-nums",
                                qty > 0 ? "text-emerald-400" : "text-destructive",
                              )}
                            >
                              {fmtNum(qty, 6)}
                            </td>
                            <td className="px-3 py-1 text-right font-mono tabular-nums">
                              {fmtMoney(avg)}
                            </td>
                            <td className="px-3 py-1 text-right font-mono tabular-nums">
                              {last > 0 ? fmtMoney(last) : "—"}
                            </td>
                            <td
                              className={cn(
                                "px-3 py-1 text-right font-mono tabular-nums",
                                ur > 0 && "text-emerald-400",
                                ur < 0 && "text-destructive",
                              )}
                            >
                              {ur !== 0 ? fmtMoney(ur) : "—"}
                            </td>
                            <td
                              className={cn(
                                "px-3 py-1 text-right font-mono tabular-nums",
                                num(p.realized_pnl) > 0 && "text-emerald-400",
                                num(p.realized_pnl) < 0 && "text-destructive",
                              )}
                            >
                              {fmtMoney(num(p.realized_pnl))}
                            </td>
                            <td className="px-3 py-1 text-right">
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 text-xs text-destructive hover:text-destructive"
                                disabled={busy === `close:${p.symbol}`}
                                onClick={() => closePosition(p.symbol)}
                              >
                                {busy === `close:${p.symbol}` ? "…" : "Close"}
                              </Button>
                            </td>
                          </tr>
                        );
                      })}
                    {portfolio.positions.filter((p) => num(p.qty) !== 0).length === 0 && (
                      <tr>
                        <td
                          colSpan={7}
                          className="px-3 py-6 text-center text-sm text-muted-foreground"
                        >
                          No open positions.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {selected && <PnlAttributionCard accountId={selected.id} />}

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm">Recent fills</CardTitle>
              {selected && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    downloadAuthed(
                      `/accounts/${selected.id}/fills.csv?limit=5000`,
                      `${selected.name.replace(/\s+/g, "_")}_fills.csv`,
                    )
                  }
                >
                  Export CSV
                </Button>
              )}
            </CardHeader>
            <CardContent className="p-0">
              <div className="max-h-[50vh] overflow-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-left">Time</th>
                      <th className="px-3 py-2 text-left">Symbol</th>
                      <th className="px-3 py-2 text-left">Side</th>
                      <th className="px-3 py-2 text-right">Qty</th>
                      <th className="px-3 py-2 text-right">Price</th>
                      <th className="px-3 py-2 text-right">Fee</th>
                      <th className="px-3 py-2 text-right">PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio.recent_fills.map((f) => (
                      <tr key={f.id} className="border-t text-xs">
                        <td className="px-3 py-1 font-mono text-muted-foreground">
                          {new Date(f.ts).toLocaleString()}
                        </td>
                        <td className="px-3 py-1 font-mono">{f.symbol}</td>
                        <td
                          className={cn(
                            "px-3 py-1 uppercase",
                            f.side === "buy" ? "text-emerald-400" : "text-destructive",
                          )}
                        >
                          {f.side}
                        </td>
                        <td className="px-3 py-1 text-right font-mono tabular-nums">
                          {fmtNum(num(f.qty), 6)}
                        </td>
                        <td className="px-3 py-1 text-right font-mono tabular-nums">
                          {fmtMoney(num(f.price))}
                        </td>
                        <td className="px-3 py-1 text-right font-mono tabular-nums text-muted-foreground">
                          {fmtMoney(num(f.fee))}
                        </td>
                        <td
                          className={cn(
                            "px-3 py-1 text-right font-mono tabular-nums",
                            num(f.pnl) > 0 && "text-emerald-400",
                            num(f.pnl) < 0 && "text-destructive",
                          )}
                        >
                          {num(f.pnl) !== 0 ? fmtMoney(num(f.pnl)) : "—"}
                        </td>
                      </tr>
                    ))}
                    {portfolio.recent_fills.length === 0 && (
                      <tr>
                        <td
                          colSpan={7}
                          className="px-3 py-6 text-center text-sm text-muted-foreground"
                        >
                          No fills yet. Run a strategy live in P3.1.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
