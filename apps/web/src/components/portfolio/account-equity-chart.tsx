"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type EquityPoint = {
  ts: string;
  equity: string;
  cash: string;
};

function fmtMoney(n: number): string {
  if (n === 0) return "$0";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1000) return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `${sign}$${abs.toFixed(2)}`;
}

function fmtPct(n: number): string {
  const sign = n > 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(2)}%`;
}

/** Lightweight inline SVG sparkline so we don't drag lightweight-charts in here. */
function Sparkline({ points }: { points: { ts: number; value: number }[] }) {
  if (points.length < 2) {
    return (
      <div className="flex h-32 items-center justify-center text-xs text-muted-foreground">
        Not enough history yet — equity is recorded as fills land.
      </div>
    );
  }
  const w = 720;
  const h = 120;
  const padX = 6;
  const padY = 8;
  const xs = points.map((p) => p.ts);
  const ys = points.map((p) => p.value);
  const xMin = xs[0];
  const xMax = xs[xs.length - 1];
  const xSpan = xMax - xMin || 1;
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const ySpan = yMax - yMin || 1;
  const x = (i: number) => padX + ((xs[i] - xMin) / xSpan) * (w - 2 * padX);
  const y = (v: number) => padY + (1 - (v - yMin) / ySpan) * (h - 2 * padY);
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(2)} ${y(p.value).toFixed(2)}`)
    .join(" ");

  const startVal = ys[0];
  const stroke = ys[ys.length - 1] >= startVal ? "rgb(16,185,129)" : "rgb(244,63,94)";

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-32 w-full" preserveAspectRatio="none">
      {/* baseline (starting equity) */}
      <line
        x1={padX}
        x2={w - padX}
        y1={y(startVal)}
        y2={y(startVal)}
        stroke="currentColor"
        strokeOpacity="0.15"
        strokeDasharray="3 3"
      />
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" />
    </svg>
  );
}

export function AccountEquityChart({ accountId }: { accountId: string }) {
  const { data } = useSWR<EquityPoint[]>(`/accounts/${accountId}/equity?limit=2000`, fetcher, {
    refreshInterval: 30_000,
  });

  if (!data) {
    return (
      <Card>
        <CardHeader className="p-4 pb-1">
          <CardTitle className="text-sm">Equity</CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-2 text-xs text-muted-foreground">Loading…</CardContent>
      </Card>
    );
  }

  // Trim to the last 30 days so the sparkline emphasises recent history.
  const cutoff = Date.now() - 30 * 86400_000;
  const recent = data
    .map((p) => ({ ts: new Date(p.ts).getTime(), value: Number(p.equity) }))
    .filter((p) => p.ts >= cutoff);

  // Today's start: most recent point with ts < midnight UTC today.
  const todayMidnightUtc = new Date();
  todayMidnightUtc.setUTCHours(0, 0, 0, 0);
  const todayStartTs = todayMidnightUtc.getTime();
  const beforeToday = recent.filter((p) => p.ts < todayStartTs);
  const startOfToday = beforeToday.length > 0 ? beforeToday[beforeToday.length - 1].value : null;
  const current = recent.length > 0 ? recent[recent.length - 1].value : null;
  const startOfWindow = recent.length > 0 ? recent[0].value : null;

  const todayDelta = current != null && startOfToday != null ? current - startOfToday : null;
  const todayDeltaPct =
    current != null && startOfToday != null && startOfToday > 0
      ? (current - startOfToday) / startOfToday
      : null;
  const windowDelta = current != null && startOfWindow != null ? current - startOfWindow : null;
  const windowDeltaPct =
    current != null && startOfWindow != null && startOfWindow > 0
      ? (current - startOfWindow) / startOfWindow
      : null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-baseline justify-between p-4 pb-1">
        <CardTitle className="text-sm">Equity (30d)</CardTitle>
        <div className="flex gap-4 text-xs">
          <span>
            <span className="text-muted-foreground">Today </span>
            <span
              className={cn(
                "font-mono tabular-nums",
                (todayDelta ?? 0) > 0 && "text-emerald-400",
                (todayDelta ?? 0) < 0 && "text-rose-500",
              )}
            >
              {todayDelta != null ? fmtMoney(todayDelta) : "—"}
              {todayDeltaPct != null && ` (${fmtPct(todayDeltaPct)})`}
            </span>
          </span>
          <span>
            <span className="text-muted-foreground">30d </span>
            <span
              className={cn(
                "font-mono tabular-nums",
                (windowDelta ?? 0) > 0 && "text-emerald-400",
                (windowDelta ?? 0) < 0 && "text-rose-500",
              )}
            >
              {windowDelta != null ? fmtMoney(windowDelta) : "—"}
              {windowDeltaPct != null && ` (${fmtPct(windowDeltaPct)})`}
            </span>
          </span>
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-2">
        <Sparkline points={recent} />
      </CardContent>
    </Card>
  );
}
