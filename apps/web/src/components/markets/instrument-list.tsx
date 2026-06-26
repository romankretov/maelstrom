"use client";

import { useState } from "react";
import useSWR from "swr";
import { Star } from "lucide-react";
import { fetcher } from "@/lib/api";
import type { Instrument, InstrumentSort } from "@/lib/markets";
import { Input } from "@/components/ui/input";
import { useWatchlist } from "@/lib/watchlist";
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
  const { isPinned, toggle: togglePin } = useWatchlist();

  // Re-sort the loaded list with pinned symbols at the top, preserving
  // the backend's sort within each group.
  const sorted = data
    ? [...data].sort((a, b) => {
        const ap = isPinned(a.source, a.symbol) ? 1 : 0;
        const bp = isPinned(b.source, b.symbol) ? 1 : 0;
        if (ap !== bp) return bp - ap; // pinned first
        return 0;
      })
    : undefined;

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
        {sorted?.map((i) => {
          const active = i.symbol === selected;
          const pinned = isPinned(i.source, i.symbol);
          return (
            <div
              key={`${i.source}:${i.symbol}`}
              className={cn(
                "flex w-full items-center gap-1 px-3 py-2 text-sm transition-colors",
                active ? "bg-secondary text-secondary-foreground" : "hover:bg-secondary/50",
              )}
            >
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  void togglePin(i.source, i.symbol);
                }}
                title={pinned ? "Unpin from watchlist" : "Pin to watchlist"}
                className={cn(
                  "shrink-0 rounded p-0.5 transition-colors",
                  pinned ? "text-amber-400" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Star className="h-3.5 w-3.5" fill={pinned ? "currentColor" : "none"} />
              </button>
              <button
                type="button"
                onClick={() => onSelect(i.symbol)}
                className="flex flex-1 items-center justify-between text-left"
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
            </div>
          );
        })}
      </div>
    </div>
  );
}
