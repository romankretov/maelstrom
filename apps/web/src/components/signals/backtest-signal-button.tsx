"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

type BacktestResponse = { strategy_id: string; backtest_run_id: string };

export function BacktestSignalButton({ signalId }: { signalId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api<BacktestResponse>(`/signals/${signalId}/backtest`, {
        method: "POST",
        body: JSON.stringify({ days: 90, notional: 1000, initial_capital: 10_000 }),
      });
      router.push(`/backtests/${res.backtest_run_id}`);
    } catch (err) {
      setError((err as { message?: string }).message ?? "Failed");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <Button
        size="sm"
        variant="secondary"
        className="h-7 w-full text-xs"
        disabled={busy}
        onClick={run}
      >
        {busy ? "Scaffolding…" : "Backtest this signal"}
      </Button>
      {error && <p className="text-[10px] text-destructive">{error}</p>}
    </div>
  );
}
