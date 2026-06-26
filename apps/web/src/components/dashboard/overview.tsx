"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type LiveRun = {
  id: string;
  strategy_id: string;
  strategy_name: string | null;
  account_name: string | null;
  symbols: string[];
  timeframe: string;
  status: string;
};

type Fill = {
  ts: string;
  account_name: string | null;
  strategy_name: string | null;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  pnl: number;
};

type Signal = {
  id: string;
  ts: string;
  symbol: string;
  direction: string;
  score: number;
  confidence: number | null;
  horizon: string | null;
};

type Overview = {
  total_equity: number;
  total_cash: number;
  today_pnl: number;
  running_strategies: number;
  open_positions: number;
  runs: LiveRun[];
  fills: Fill[];
  signals: Signal[];
};

function fmtMoney(n: number): string {
  if (n === 0) return "$0";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1000) return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `${sign}$${abs.toFixed(2)}`;
}

function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function MetricCard({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "good" | "bad" | "neutral";
}) {
  return (
    <Card>
      <CardHeader className="p-4 pb-1">
        <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <div
          className={cn(
            "font-mono text-2xl tabular-nums",
            tone === "good" && "text-emerald-400",
            tone === "bad" && "text-rose-500",
          )}
        >
          {value}
        </div>
        {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

export function DashboardOverview() {
  const { data, error } = useSWR<Overview>("/admin/dashboard", fetcher, {
    refreshInterval: 10_000,
  });

  if (error) {
    return (
      <p className="text-sm text-destructive">
        {(error as { message?: string }).message ?? "Failed to load overview"}
      </p>
    );
  }
  if (!data) return null;

  const pnlTone = data.today_pnl > 0 ? "good" : data.today_pnl < 0 ? "bad" : "neutral";

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Equity"
          value={fmtMoney(data.total_equity)}
          sub={`cash ${fmtMoney(data.total_cash)}`}
        />
        <MetricCard label="Today's P&L" value={fmtMoney(data.today_pnl)} tone={pnlTone} />
        <MetricCard label="Open positions" value={data.open_positions} />
        <MetricCard label="Active strategies" value={data.running_strategies} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-sm">Running strategies</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-2">
            {data.runs.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nothing live right now.</p>
            ) : (
              <ul className="space-y-1.5 text-sm">
                {data.runs.map((r) => (
                  <li key={r.id} className="flex items-center justify-between">
                    <Link
                      href={`/strategies/${r.strategy_id}/runs/${r.id}`}
                      className="font-mono text-xs hover:underline"
                    >
                      {r.strategy_name ?? r.strategy_id.slice(0, 8)}
                    </Link>
                    <span className="text-[10px] text-muted-foreground">
                      {r.symbols.join(",")} · {r.timeframe} · {r.account_name ?? "—"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="p-4 pb-1">
            <CardTitle className="text-sm">Recent fills</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-2">
            {data.fills.length === 0 ? (
              <p className="text-xs text-muted-foreground">No fills yet.</p>
            ) : (
              <ul className="space-y-1 font-mono text-xs">
                {data.fills.slice(0, 5).map((f, i) => (
                  <li key={i} className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 truncate">
                      <span
                        className={cn(
                          "rounded px-1 py-0.5 text-[10px] uppercase",
                          f.side === "buy"
                            ? "bg-emerald-500/15 text-emerald-400"
                            : "bg-rose-500/15 text-rose-500",
                        )}
                      >
                        {f.side}
                      </span>
                      <span>{f.symbol}</span>
                      <span className="text-muted-foreground">{f.strategy_name ?? "manual"}</span>
                    </span>
                    <span className="text-muted-foreground">{relTime(f.ts)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between p-4 pb-1">
          <CardTitle className="text-sm">Latest signals</CardTitle>
          <Link href="/signals" className="text-xs text-muted-foreground hover:underline">
            view all →
          </Link>
        </CardHeader>
        <CardContent className="p-4 pt-2">
          {data.signals.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No active signals. Check the scanner status on /signals.
            </p>
          ) : (
            <ul className="space-y-1.5 text-xs">
              {data.signals.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                        s.direction === "long"
                          ? "bg-emerald-500/15 text-emerald-400"
                          : s.direction === "short"
                            ? "bg-rose-500/15 text-rose-500"
                            : "bg-muted text-muted-foreground",
                      )}
                    >
                      {s.direction}
                    </span>
                    <span className="font-mono">{s.symbol}</span>
                    {s.horizon && (
                      <span className="text-[10px] text-muted-foreground">· {s.horizon}</span>
                    )}
                  </span>
                  <span className="font-mono text-muted-foreground">
                    score {s.score.toFixed(0)} · {relTime(s.ts)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
