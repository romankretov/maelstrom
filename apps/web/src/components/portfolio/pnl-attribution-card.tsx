"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type PnlAttributionRow = {
  live_strategy_id: string | null;
  strategy_id: string | null;
  strategy_name: string | null;
  symbol: string;
  realized_pnl: number;
  fees: number;
  fills: number;
  first_fill: string | null;
  last_fill: string | null;
};

type PnlAttribution = {
  account_id: string;
  rows: PnlAttributionRow[];
  total_realized: number;
  total_fees: number;
};

function fmtMoney(n: number): string {
  if (n === 0) return "$0";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1000) {
    return `${sign}$${abs.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
  return `${sign}$${abs.toFixed(2)}`;
}

export function PnlAttributionCard({ accountId }: { accountId: string }) {
  const { data, error, isLoading } = useSWR<PnlAttribution>(
    `/accounts/${accountId}/pnl-attribution`,
    fetcher,
    { refreshInterval: 10_000 },
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm">PnL attribution</CardTitle>
        {data && (
          <span className="text-xs text-muted-foreground">
            net{" "}
            <span className={cn("font-mono", data.total_realized < 0 && "text-destructive")}>
              {" "}
              {fmtMoney(data.total_realized - data.total_fees)}
            </span>{" "}
            (fees {fmtMoney(data.total_fees)})
          </span>
        )}
      </CardHeader>
      <CardContent className="p-0">
        {isLoading && <p className="px-4 py-3 text-xs text-muted-foreground">Loading…</p>}
        {error && (
          <p className="px-4 py-3 text-xs text-destructive">
            {(error as { message?: string }).message ?? "Failed to load"}
          </p>
        )}
        {data && data.rows.length === 0 && (
          <p className="px-4 py-3 text-xs text-muted-foreground">No fills yet on this account.</p>
        )}
        {data && data.rows.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left">Strategy</th>
                  <th className="px-3 py-2 text-left">Symbol</th>
                  <th className="px-3 py-2 text-right">Realized</th>
                  <th className="px-3 py-2 text-right">Fees</th>
                  <th className="px-3 py-2 text-right">Net</th>
                  <th className="px-3 py-2 text-right">Fills</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => {
                  const net = r.realized_pnl - r.fees;
                  return (
                    <tr
                      key={`${r.live_strategy_id ?? "none"}-${r.symbol}-${i}`}
                      className="border-t border-border/60"
                    >
                      <td className="px-3 py-1.5">
                        {r.strategy_id && r.strategy_name ? (
                          <Link
                            href={`/strategies/${r.strategy_id}`}
                            className="font-mono hover:underline"
                          >
                            {r.strategy_name}
                          </Link>
                        ) : (
                          <span className="italic text-muted-foreground">unattributed</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 font-mono">{r.symbol}</td>
                      <td
                        className={cn(
                          "px-3 py-1.5 text-right font-mono tabular-nums",
                          r.realized_pnl >= 0 ? "text-emerald-400" : "text-destructive",
                        )}
                      >
                        {fmtMoney(r.realized_pnl)}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted-foreground">
                        {fmtMoney(r.fees)}
                      </td>
                      <td
                        className={cn(
                          "px-3 py-1.5 text-right font-mono tabular-nums",
                          net >= 0 ? "text-emerald-400" : "text-destructive",
                        )}
                      >
                        {fmtMoney(net)}
                      </td>
                      <td className="px-3 py-1.5 text-right font-mono">{r.fills}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
