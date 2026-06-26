"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import type { Instrument } from "@/lib/markets";
import { Input } from "@/components/ui/input";
import { useWatchlist } from "@/lib/watchlist";
import { cn } from "@/lib/utils";

type SingleProps = {
  source: string;
  value: string;
  onChange: (next: string) => void;
  multi?: false;
  placeholder?: string;
  className?: string;
  id?: string;
  required?: boolean;
};

type MultiProps = {
  source: string;
  value: string; // comma-separated
  onChange: (next: string) => void;
  multi: true;
  placeholder?: string;
  className?: string;
  id?: string;
  required?: boolean;
};

type Props = SingleProps | MultiProps;

/**
 * Symbol picker with autocomplete fed by /markets/instruments?source=...
 *
 * Two modes:
 *  - single: one symbol per input (run-live needs only one for now)
 *  - multi: comma-separated list, picking an option appends/replaces
 *    the last token in the input
 *
 * Free text is still allowed (in case the catalog is incomplete) but the
 * dropdown emphasises canonical symbols so typos get caught visually.
 */
export function SymbolAutocomplete(props: Props) {
  const { source, value, onChange, placeholder, className, id, required } = props;
  const multi = "multi" in props && props.multi === true;

  const { data: instruments } = useSWR<Instrument[]>(
    source ? `/markets/instruments?source=${source}&limit=500` : null,
    fetcher,
    { revalidateOnFocus: false },
  );
  const { isPinned } = useWatchlist();

  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click.
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // For multi mode, autocomplete operates on the LAST token after the
  // final comma. For single mode, on the whole value.
  const { activeQuery, prefix } = useMemo(() => {
    if (!multi) return { activeQuery: value.trim().toUpperCase(), prefix: "" };
    const lastComma = value.lastIndexOf(",");
    const tail = lastComma >= 0 ? value.slice(lastComma + 1) : value;
    return {
      activeQuery: tail.trim().toUpperCase(),
      prefix: lastComma >= 0 ? value.slice(0, lastComma + 1) : "",
    };
  }, [value, multi]);

  const matches = useMemo(() => {
    if (!instruments) return [];
    const q = activeQuery;
    const filtered = q
      ? instruments.filter((i) => i.symbol.toUpperCase().includes(q))
      : instruments;
    // Watchlist'd symbols float to the top — your pinned ones surface
    // first regardless of the catalog's underlying sort.
    return [...filtered]
      .sort((a, b) => {
        const ap = isPinned(a.source, a.symbol) ? 1 : 0;
        const bp = isPinned(b.source, b.symbol) ? 1 : 0;
        return bp - ap;
      })
      .slice(0, 12);
  }, [instruments, activeQuery, isPinned]);

  function pick(sym: string) {
    if (multi) {
      // Append, then add a comma so the user can keep typing the next one.
      const sep = prefix.trim() ? (prefix.endsWith(", ") || prefix.endsWith(",") ? "" : ", ") : "";
      onChange(`${prefix}${sep}${sym}, `);
    } else {
      onChange(sym);
    }
    setOpen(false);
    setHighlight(0);
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter" && matches[highlight]) {
      e.preventDefault();
      pick(matches[highlight].symbol);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className={cn("relative", className)} ref={containerRef}>
      <Input
        id={id}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setHighlight(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
        placeholder={placeholder ?? (multi ? "BTC-PERP, ETH-PERP" : "BTC-PERP")}
        className="font-mono"
        required={required}
        autoComplete="off"
      />
      {open && matches.length > 0 && (
        <div className="bg-popover absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-md border shadow-lg">
          {matches.map((i, idx) => (
            <button
              key={i.symbol}
              type="button"
              onMouseDown={(e) => {
                // mousedown so it fires before blur closes the dropdown.
                e.preventDefault();
                pick(i.symbol);
              }}
              className={cn(
                "flex w-full items-center justify-between px-3 py-1.5 text-left text-xs",
                idx === highlight ? "bg-secondary" : "hover:bg-secondary/50",
              )}
            >
              <span className="font-mono">{i.symbol}</span>
              <span className="text-[10px] text-muted-foreground">{i.quote}</span>
            </button>
          ))}
        </div>
      )}
      {open && instruments && matches.length === 0 && activeQuery && (
        <div className="bg-popover absolute z-10 mt-1 w-full rounded-md border px-3 py-2 text-xs text-muted-foreground shadow-lg">
          No match for <code className="font-mono">{activeQuery}</code>. Free text is accepted but
          the symbol must exist on {source} for orders to fire.
        </div>
      )}
    </div>
  );
}
