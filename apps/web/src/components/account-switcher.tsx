"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { ChevronsUpDown, Wallet } from "lucide-react";
import { fetcher } from "@/lib/api";
import type { Account } from "@/lib/trading";
import { useCurrentAccount } from "@/lib/current-account";
import { cn } from "@/lib/utils";

function kindLabel(kind: string): string {
  if (kind === "paper") return "paper";
  if (kind === "live_hl_main") return "hl main";
  if (kind === "live_hl_testnet") return "hl test";
  return kind;
}

/**
 * Sidebar widget that surfaces the user's "current" trading account. Click
 * to expand and switch between accounts — selection is persisted via
 * useCurrentAccount so other pages (portfolio, run-live) can default to
 * the same one.
 */
export function AccountSwitcher() {
  const { data: accounts } = useSWR<Account[]>("/accounts", fetcher);
  const { accountId, setAccountId } = useCurrentAccount();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // First-load default — pick the first account if nothing's selected.
  useEffect(() => {
    if (accountId === null && accounts && accounts.length > 0) {
      setAccountId(accounts[0].id);
    }
  }, [accounts, accountId, setAccountId]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  if (!accounts || accounts.length === 0) {
    return (
      <Link
        href="/portfolio"
        className="mx-2 flex items-center gap-2 rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground hover:bg-secondary/60"
      >
        <Wallet className="h-3.5 w-3.5" />
        No accounts — set up
      </Link>
    );
  }

  const current = accounts.find((a) => a.id === accountId) ?? accounts[0];

  return (
    <div className="relative mx-2" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-md border bg-background px-3 py-2 text-left text-xs hover:bg-secondary/60"
      >
        <span className="flex min-w-0 flex-col">
          <span className="truncate font-medium">{current.name}</span>
          <span className="text-[10px] text-muted-foreground">
            <Wallet className="mr-1 inline h-3 w-3" />
            {kindLabel(current.kind)}
            {current.killed && <span className="ml-1 text-destructive">· killed</span>}
            {!current.is_active && <span className="ml-1 text-yellow-500">· inactive</span>}
          </span>
        </span>
        <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      </button>
      {open && (
        <div className="bg-popover absolute bottom-full left-0 z-20 mb-1 w-full overflow-hidden rounded-md border shadow-lg">
          {accounts.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => {
                setAccountId(a.id);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center justify-between px-3 py-1.5 text-left text-xs",
                a.id === current.id ? "bg-secondary" : "hover:bg-secondary/60",
              )}
            >
              <span className="flex min-w-0 flex-col">
                <span className="truncate font-medium">{a.name}</span>
                <span className="text-[10px] text-muted-foreground">{kindLabel(a.kind)}</span>
              </span>
            </button>
          ))}
          <Link
            href="/portfolio"
            onClick={() => setOpen(false)}
            className="block border-t px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-secondary/60"
          >
            Manage accounts →
          </Link>
        </div>
      )}
    </div>
  );
}
