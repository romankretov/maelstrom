"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TIMEFRAMES, type Timeframe } from "@/lib/markets";
import type { CorrelationOut } from "@/lib/research";
import { cn } from "@/lib/utils";

function correlationColor(c: number | null): string {
  if (c == null || !Number.isFinite(c)) return "rgba(120, 120, 120, 0.15)";
  // Diverging colormap: red (-1) → neutral (0) → green (+1)
  const clamped = Math.max(-1, Math.min(1, c));
  const intensity = Math.round(Math.abs(clamped) * 200) + 30;
  if (clamped >= 0) return `rgba(16, ${intensity}, 80, ${0.15 + Math.abs(clamped) * 0.6})`;
  return `rgba(${intensity}, 30, 60, ${0.15 + Math.abs(clamped) * 0.6})`;
}

export function CorrelationMatrix({ source }: { source: string }) {
  const [symbols, setSymbols] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [timeframe, setTimeframe] = useState<Timeframe>("1h");
  const [days, setDays] = useState(30);
  const [data, setData] = useState<CorrelationOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addSymbol = () => {
    const sym = draft.trim();
    if (!sym) return;
    if (symbols.includes(sym)) {
      setDraft("");
      return;
    }
    if (symbols.length >= 20) return;
    setSymbols([...symbols, sym]);
    setDraft("");
  };

  const removeSymbol = (s: string) => setSymbols(symbols.filter((x) => x !== s));

  const compute = async () => {
    setError(null);
    setLoading(true);
    try {
      const result = await api<CorrelationOut>("/research/correlation", {
        method: "POST",
        body: JSON.stringify({ source, symbols, timeframe, days }),
      });
      setData(result);
    } catch (e) {
      setError((e as { message?: string }).message ?? "Failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="text-base">Correlation matrix</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-2">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Add symbol</label>
            <div className="flex gap-2">
              <Input
                value={draft}
                placeholder="BTCUSDT"
                onChange={(e) => setDraft(e.target.value.toUpperCase())}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addSymbol();
                  }
                }}
                className="w-36 font-mono"
              />
              <Button type="button" variant="secondary" size="sm" onClick={addSymbol}>
                Add
              </Button>
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Timeframe</label>
            <div className="flex gap-1">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  onClick={() => setTimeframe(tf)}
                  className={cn(
                    "rounded px-2 py-1 text-xs",
                    tf === timeframe
                      ? "bg-secondary text-secondary-foreground"
                      : "text-muted-foreground hover:bg-secondary/60",
                  )}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">Lookback (days)</label>
            <Input
              type="number"
              min={1}
              max={365}
              value={days}
              onChange={(e) => setDays(Math.max(1, Math.min(365, Number(e.target.value) || 30)))}
              className="w-24"
            />
          </div>
          <Button
            type="button"
            onClick={compute}
            disabled={symbols.length < 2 || loading}
            className="ml-auto"
          >
            {loading ? "Computing…" : "Compute"}
          </Button>
        </div>

        {symbols.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {symbols.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => removeSymbol(s)}
                className="flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 font-mono text-xs hover:bg-secondary/70"
              >
                {s} <span className="text-muted-foreground">×</span>
              </button>
            ))}
          </div>
        )}

        {symbols.length < 2 && (
          <div className="text-xs text-muted-foreground">
            Add at least 2 symbols to compute correlations.
          </div>
        )}

        {error && <div className="text-sm text-destructive">{error}</div>}

        {data && (
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-xs">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left text-muted-foreground"></th>
                  {data.symbols.map((s) => (
                    <th key={s} className="px-2 py-1 text-left font-mono text-muted-foreground">
                      {s}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.symbols.map((rowSym, i) => (
                  <tr key={rowSym}>
                    <td className="px-2 py-1 font-mono text-muted-foreground">{rowSym}</td>
                    {data.matrix[i].map((cell, j) => (
                      <td
                        key={`${i}-${j}`}
                        className="px-2 py-1 text-center font-mono"
                        style={{ backgroundColor: correlationColor(cell) }}
                        title={`samples: ${data.samples[i][j]}`}
                      >
                        {cell == null ? "—" : cell.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-2 text-xs text-muted-foreground">
              {data.timeframe} log-returns · {data.days}d lookback · aligned overlap only ·{" "}
              {new Date(data.computed_at).toLocaleString()}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
