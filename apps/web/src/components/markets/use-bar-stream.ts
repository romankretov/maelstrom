"use client";

import { useEffect, useRef, useState } from "react";
import type { Bar } from "@/lib/markets";

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE_URL ??
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`
    : "");

export type StreamState = "idle" | "connecting" | "live" | "closed";

export function useBarStream(
  source: string | null,
  symbol: string | null,
  timeframe: string,
): { latest: Bar | null; state: StreamState } {
  const [latest, setLatest] = useState<Bar | null>(null);
  const [state, setState] = useState<StreamState>("idle");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!source || !symbol || !timeframe) {
      setState("idle");
      return;
    }
    const url = `${WS_BASE}/markets/${source}/${symbol}/${timeframe}`;
    setState("connecting");
    setLatest(null);
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      setState("closed");
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => setState("live");
    ws.onmessage = (event) => {
      try {
        const data: unknown = typeof event.data === "string" ? JSON.parse(event.data) : null;
        if (data && typeof data === "object" && "open" in data) {
          setLatest(data as Bar);
        }
      } catch {
        /* ignore non-bar frames (e.g. subscribed handshake) */
      }
    };
    ws.onclose = () => setState("closed");
    ws.onerror = () => setState("closed");

    return () => {
      try {
        ws.close();
      } catch {
        /* noop */
      }
      // Only clear the ref if it still points at the socket we created here —
      // a rapid symbol switch may have already replaced it with a newer one.
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [source, symbol, timeframe]);

  return { latest, state };
}
