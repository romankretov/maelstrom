"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Instrument, InstrumentSort } from "@/lib/markets";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

function fmtVolume(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n === 0) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toFixed(0);
}

function fmtChange(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(2)}%`;
}

export function InstrumentList({
  source,
  selected,
  onSelect,
}: {
  source: string;
  selected: string | null;
  onSelect: (symbol: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<InstrumentSort>("volume");
  const params = new URLSearchParams({ source, limit: "200", sort });
  if (query) params.set("q", query);

  const { data, isLoading, error } = useSWR<Instrument[]>(
    `/markets/instruments?${params.toString()}`,
    fetcher,
    { refreshInterval: 0 },
  );

  return (
    <div className="flex h-full flex-col gap-2">
      <Input
        placeholder="Search BTC, ETH, …"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="flex gap-1 text-xs">
        {(["volume", "change_24h", "alpha"] as InstrumentSort[]).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSort(s)}
            className={cn(
              "rounded px-2 py-0.5",
              s === sort
                ? "bg-secondary text-secondary-foreground"
                : "text-muted-foreground hover:bg-secondary/60",
            )}
          >
            {s === "volume" ? "Volume" : s === "change_24h" ? "24h Δ" : "A→Z"}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto rounded-md border">
        {isLoading && <div className="p-3 text-sm text-muted-foreground">Loading instruments…</div>}
        {error && (
          <div className="p-3 text-sm text-destructive">
            Failed to load instruments. {(error as { message?: string }).message ?? ""}
          </div>
        )}
        {!isLoading && !error && data && data.length === 0 && (
          <div className="p-3 text-sm text-muted-foreground">
            No instruments — run a sync_instruments job from a worker shell.
          </div>
        )}
        {data?.map((i) => {
          const active = i.symbol === selected;
          return (
            <button
              key={`${i.source}:${i.symbol}`}
              type="button"
              onClick={() => onSelect(i.symbol)}
              className={cn(
                "flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors",
                active ? "bg-secondary text-secondary-foreground" : "hover:bg-secondary/50",
              )}
            >
              <span className="font-mono">{i.symbol}</span>
              <span className="flex items-center gap-2 text-xs">
                {sort === "volume" && (
                  <span className="text-muted-foreground">vol {fmtVolume(i.volume_24h)}</span>
                )}
                {sort === "change_24h" && (
                  <span
                    className={cn(
                      "font-mono tabular-nums",
                      (i.change_24h ?? 0) > 0 && "text-emerald-400",
                      (i.change_24h ?? 0) < 0 && "text-rose-500",
                    )}
                  >
                    {fmtChange(i.change_24h)}
                  </span>
                )}
                {sort === "alpha" && <span className="text-muted-foreground">{i.quote}</span>}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
