"use client";

import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";

export type WatchlistEntry = { source: string; symbol: string };

export function useWatchlist() {
  const { data, mutate } = useSWR<WatchlistEntry[]>("/watchlist", fetcher, {
    revalidateOnFocus: false,
  });
  const { mutate: mutateGlobal } = useSWRConfig();

  const isPinned = (source: string, symbol: string): boolean =>
    !!data?.some((e) => e.source === source && e.symbol === symbol);

  async function toggle(source: string, symbol: string): Promise<void> {
    const pinned = isPinned(source, symbol);
    if (pinned) {
      await api(`/watchlist/${encodeURIComponent(source)}/${encodeURIComponent(symbol)}`, {
        method: "DELETE",
      });
    } else {
      await api("/watchlist", {
        method: "POST",
        body: JSON.stringify({ source, symbol }),
      });
    }
    await mutate();
    // Nudge any list that depends on watchlist ordering.
    await mutateGlobal((k) => typeof k === "string" && k.startsWith("/markets/instruments"));
  }

  return { entries: data ?? [], isPinned, toggle };
}
