"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Instrument } from "@/lib/markets";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

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
  const params = new URLSearchParams({ source, limit: "200" });
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
              <span className="text-xs text-muted-foreground">{i.quote}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
