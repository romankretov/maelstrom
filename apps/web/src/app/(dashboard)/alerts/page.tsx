"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, fetcher } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type Alert = {
  id: string;
  label: string;
  source: string;
  symbol: string;
  condition: string;
  threshold: number;
  cooldown_minutes: number;
  enabled: boolean;
  last_triggered_at: string | null;
  last_value: number | null;
  trigger_count: number;
  created_at: string;
};

const CONDITIONS: { value: string; label: string; help: string }[] = [
  { value: "price_above", label: "Price above", help: "absolute price, e.g. 65000" },
  { value: "price_below", label: "Price below", help: "absolute price, e.g. 60000" },
  {
    value: "change_24h_above",
    label: "24h change above",
    help: "fraction, 0.05 = +5%",
  },
  {
    value: "change_24h_below",
    label: "24h change below",
    help: "fraction, -0.05 = -5%",
  },
  {
    value: "funding_above",
    label: "Funding rate above",
    help: "per-window fraction, 0.0005 ≈ +0.05%",
  },
  {
    value: "funding_below",
    label: "Funding rate below",
    help: "per-window fraction, -0.0005 ≈ -0.05%",
  },
];

const SOURCES = ["binance", "hyperliquid"];

function relTime(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatThreshold(condition: string, n: number): string {
  if (condition.startsWith("price_")) return n.toLocaleString();
  return `${(n * 100).toFixed(2)}%`;
}

function AlertForm({ onCreated }: { onCreated: () => void }) {
  const [label, setLabel] = useState("");
  const [source, setSource] = useState(SOURCES[0]);
  const [symbol, setSymbol] = useState("BTC-PERP");
  const [condition, setCondition] = useState(CONDITIONS[0].value);
  const [threshold, setThreshold] = useState("");
  const [cooldown, setCooldown] = useState(60);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const help = CONDITIONS.find((c) => c.value === condition)?.help;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api<Alert>("/alerts", {
        method: "POST",
        body: JSON.stringify({
          label,
          source,
          symbol: symbol.toUpperCase(),
          condition,
          threshold: Number(threshold),
          cooldown_minutes: cooldown,
        }),
      });
      setLabel("");
      setThreshold("");
      onCreated();
    } catch (err) {
      setError((err as { message?: string }).message ?? "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-base">New alert</CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-2">
        <form onSubmit={submit} className="space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="label">Label</Label>
              <Input
                id="label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="BTC breakdown watch"
                required
                maxLength={120}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="source">Source / Symbol</Label>
              <div className="flex gap-2">
                <select
                  id="source"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  className="rounded-md border bg-background px-2 py-1 text-sm"
                >
                  {SOURCES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <Input
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  className="font-mono"
                  required
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="cond">Condition</Label>
              <select
                id="cond"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                className="w-full rounded-md border bg-background px-2 py-1 text-sm"
              >
                {CONDITIONS.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="thr">Threshold</Label>
              <Input
                id="thr"
                type="number"
                step="any"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                required
              />
              {help && <p className="text-[10px] text-muted-foreground">{help}</p>}
            </div>
            <div className="space-y-1">
              <Label htmlFor="cd">Cooldown (min)</Label>
              <Input
                id="cd"
                type="number"
                min={1}
                max={10080}
                value={cooldown}
                onChange={(e) => setCooldown(Math.max(1, Number(e.target.value) || 60))}
              />
            </div>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={busy}>
            {busy ? "Creating…" : "Create alert"}
          </Button>
        </form>
        <p className="mt-3 text-xs text-muted-foreground">
          Fires through any notification channel subscribed to <code>price_alert</code>. Set
          channels up in{" "}
          <a className="underline" href="/settings">
            Settings
          </a>
          .
        </p>
      </CardContent>
    </Card>
  );
}

export default function AlertsPage() {
  const { data, mutate, error, isLoading } = useSWR<Alert[]>("/alerts", fetcher, {
    refreshInterval: 15_000,
  });
  const [busy, setBusy] = useState<string | null>(null);

  async function toggle(a: Alert) {
    setBusy(a.id);
    try {
      const next = await api<Alert>(`/alerts/${a.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !a.enabled }),
      });
      await mutate((prev) => prev?.map((x) => (x.id === a.id ? next : x)), { revalidate: false });
    } finally {
      setBusy(null);
    }
  }

  async function remove(a: Alert) {
    if (!confirm(`Delete alert "${a.label}"?`)) return;
    setBusy(a.id);
    try {
      await api(`/alerts/${a.id}`, { method: "DELETE" });
      await mutate((prev) => prev?.filter((x) => x.id !== a.id), { revalidate: false });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Alerts</h1>
        <p className="text-sm text-muted-foreground">
          Price, 24h change, and funding rate conditions. Evaluator runs every minute.
        </p>
      </header>

      <AlertForm onCreated={() => void mutate()} />

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && (
        <p className="text-sm text-destructive">
          {(error as { message?: string }).message ?? "Failed to load"}
        </p>
      )}
      {data && data.length === 0 && (
        <Card>
          <CardContent className="p-6 text-center text-sm text-muted-foreground">
            No alerts yet. Create one above.
          </CardContent>
        </Card>
      )}
      {data && data.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Label</th>
                  <th className="px-3 py-2 text-left">Target</th>
                  <th className="px-3 py-2 text-left">Condition</th>
                  <th className="px-3 py-2 text-right">Threshold</th>
                  <th className="px-3 py-2 text-right">Last fired</th>
                  <th className="px-3 py-2 text-right">Fires</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr
                    key={a.id}
                    className={cn(
                      "border-t border-border/60",
                      !a.enabled && "text-muted-foreground",
                    )}
                  >
                    <td className="px-3 py-2">{a.label}</td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {a.source}:{a.symbol}
                    </td>
                    <td className="px-3 py-2 text-xs">{a.condition.replace(/_/g, " ")}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">
                      {formatThreshold(a.condition, a.threshold)}
                    </td>
                    <td className="px-3 py-2 text-right text-xs">{relTime(a.last_triggered_at)}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">{a.trigger_count}</td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy === a.id}
                          onClick={() => void toggle(a)}
                        >
                          {a.enabled ? "Disable" : "Enable"}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          disabled={busy === a.id}
                          onClick={() => void remove(a)}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
