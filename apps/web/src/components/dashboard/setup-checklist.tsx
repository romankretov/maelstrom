"use client";

import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type Checklist = {
  admin_exists: boolean;
  llm_key_configured: boolean;
  notification_channel_configured: boolean;
  has_account: boolean;
  hl_credentials_configured: boolean;
  has_strategy: boolean;
  has_backtest: boolean;
};

type Step = {
  key: keyof Checklist;
  label: string;
  description: string;
  href: string;
  required: boolean;
};

const STEPS: Step[] = [
  {
    key: "admin_exists",
    label: "Admin account created",
    description: "Register the first user. They become the platform admin.",
    href: "/login",
    required: true,
  },
  {
    key: "llm_key_configured",
    label: "LLM provider key",
    description:
      "Add an Anthropic key (and optionally OpenAI) so the scanner and AI helpers can run.",
    href: "/settings",
    required: true,
  },
  {
    key: "has_account",
    label: "Trading account created",
    description: "Add a Paper or Hyperliquid account in Portfolio.",
    href: "/portfolio",
    required: true,
  },
  {
    key: "hl_credentials_configured",
    label: "Hyperliquid credentials (optional)",
    description: "Required for live trading. Skip if you only intend to paper trade.",
    href: "/portfolio",
    required: false,
  },
  {
    key: "notification_channel_configured",
    label: "Notification channel",
    description: "Hook Telegram or Discord for alerts and important events.",
    href: "/settings",
    required: false,
  },
  {
    key: "has_strategy",
    label: "First strategy",
    description:
      "Pick a template on /strategies/new — every starter ships with the SDK reference inline.",
    href: "/strategies/new",
    required: true,
  },
  {
    key: "has_backtest",
    label: "First backtest",
    description: "Click Save & backtest on a strategy to validate it against historical bars.",
    href: "/strategies",
    required: false,
  },
];

export function SetupChecklist() {
  const { data } = useSWR<Checklist>("/admin/setup-checklist", fetcher, {
    refreshInterval: 30_000,
  });

  if (!data) {
    return null;
  }

  const completed = STEPS.filter((s) => data[s.key]).length;
  const required = STEPS.filter((s) => s.required);
  const allRequiredDone = required.every((s) => data[s.key]);

  // Hide once everything is done — the user has graduated.
  if (allRequiredDone && completed === STEPS.length) return null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base">Setup checklist</CardTitle>
        <span className="text-xs text-muted-foreground">
          {completed} / {STEPS.length} complete
        </span>
      </CardHeader>
      <CardContent className="space-y-2">
        {STEPS.map((s) => {
          const done = data[s.key];
          return (
            <div
              key={s.key}
              className={cn(
                "flex items-start gap-3 rounded-md border p-3",
                done ? "border-emerald-500/30 bg-emerald-500/5" : "border-border",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
                  done ? "bg-emerald-500/20 text-emerald-400" : "bg-muted text-muted-foreground",
                )}
              >
                {done ? "✓" : ""}
              </span>
              <div className="flex-1">
                <div className="flex items-center gap-2 text-sm">
                  <span className={cn(done ? "text-muted-foreground line-through" : "font-medium")}>
                    {s.label}
                  </span>
                  {!s.required && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
                      optional
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">{s.description}</div>
              </div>
              {!done && (
                <Link
                  href={s.href}
                  className="text-xs text-foreground underline hover:no-underline"
                >
                  Go →
                </Link>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
