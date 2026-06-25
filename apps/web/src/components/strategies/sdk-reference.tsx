"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Entry = { name: string; sig: string; doc: string };
type Section = { title: string; entries: Entry[] };

// Generated from apps/worker/src/maelstrom_worker/engine/sdk.py — keep
// in lockstep. If you change the SDK signature, update this list too.
const SECTIONS: Section[] = [
  {
    title: "Lifecycle",
    entries: [
      {
        name: "on_init",
        sig: "on_init(self) -> None",
        doc: "Runs once before the first bar. Initialize counters / state here.",
      },
      {
        name: "on_bar",
        sig: "on_bar(self, bar: EngineBar) -> None",
        doc: "Runs for every bar in time order. Implement your trading logic here.",
      },
    ],
  },
  {
    title: "Class attributes",
    entries: [
      {
        name: "symbols",
        sig: "symbols = ('BTC-PERP',)",
        doc: "Tuple of symbols this strategy subscribes to.",
      },
      {
        name: "timeframe",
        sig: 'timeframe = "1h"',
        doc: '"1m" | "5m" | "15m" | "1h" | "4h" | "1d"',
      },
    ],
  },
  {
    title: "Orders (market only)",
    entries: [
      {
        name: "self.buy",
        sig: "self.buy(symbol, *, notional=USD, reason=...)",
        doc: "Open or add to a long position.",
      },
      {
        name: "self.sell",
        sig: "self.sell(symbol, *, notional=USD, reason=...)",
        doc: "Open or add to a short position.",
      },
      {
        name: "self.close",
        sig: "self.close(symbol, *, reason=...)",
        doc: "Close any open position for the symbol (long or short).",
      },
    ],
  },
  {
    title: "State (read-only)",
    entries: [
      {
        name: "self.position",
        sig: "self.position(symbol) -> Position",
        doc: ".qty (signed), .avg_price, .unrealized_pnl",
      },
      {
        name: "self.history",
        sig: "self.history(symbol, n=N) -> list[Bar]",
        doc: "Last N bars NEWEST FIRST, capped at N. NOT an ever-growing counter.",
      },
      {
        name: "self.cash",
        sig: "self.cash -> float",
        doc: "Available USDC cash balance.",
      },
      {
        name: "self.equity",
        sig: "self.equity -> float",
        doc: "Cash + mark-to-market value of open positions.",
      },
      {
        name: "self.params",
        sig: "self.params -> dict",
        doc: "Per-run params dict (set on the backtest / live form).",
      },
    ],
  },
  {
    title: "Bar fields",
    entries: [
      {
        name: "bar.ts",
        sig: "datetime",
        doc: "Bar close timestamp (UTC, tz-aware).",
      },
      { name: "bar.open", sig: "float", doc: "Open price." },
      { name: "bar.high", sig: "float", doc: "High price within the bar." },
      { name: "bar.low", sig: "float", doc: "Low price within the bar." },
      { name: "bar.close", sig: "float", doc: "Close price (final, on_bar fires AFTER close)." },
      { name: "bar.volume", sig: "float", doc: "Bar volume." },
      { name: "bar.symbol", sig: "str", doc: 'Symbol name, e.g. "BTC-PERP".' },
    ],
  },
  {
    title: "Gotchas",
    entries: [
      {
        name: "history(n=N) is capped",
        sig: "",
        doc: "Returns AT MOST N bars. For first N-1 bars you'll get fewer — guard with `if len(history) < N: return`.",
      },
      {
        name: "No built-in bar counter",
        sig: "",
        doc: "If you need 'bars since start', increment your own in on_init.",
      },
      {
        name: "Backtest ≡ live",
        sig: "",
        doc: "Same on_bar runs in both. Make it idempotent — don't keep external state.",
      },
    ],
  },
];

export function SdkReference() {
  return (
    <Card className="h-fit">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">SDK reference</CardTitle>
      </CardHeader>
      <CardContent className="max-h-[60vh] space-y-3 overflow-y-auto text-xs">
        {SECTIONS.map((s) => (
          <div key={s.title}>
            <div className="mb-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              {s.title}
            </div>
            <ul className="space-y-1.5">
              {s.entries.map((e) => (
                <li key={e.name} className="space-y-0.5">
                  {e.sig && (
                    <code className="block break-all rounded bg-muted/50 px-1.5 py-0.5 font-mono text-[10px]">
                      {e.sig}
                    </code>
                  )}
                  <div className="text-muted-foreground">{e.doc}</div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
