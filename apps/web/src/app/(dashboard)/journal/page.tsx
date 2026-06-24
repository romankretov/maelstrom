"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, fetcher } from "@/lib/api";
import type { Account } from "@/lib/trading";
import type { Strategy } from "@/lib/strategies";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type JournalResponse = {
  answer: string;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  cost_usd: number;
  duration_ms: number;
};

const PRESET_PROMPTS = [
  "Why is my account underperforming?",
  "What's my biggest losing position and why?",
  "Did the strategy take any obvious bad trades?",
  "Which symbols am I overtrading?",
];

export default function JournalPage() {
  const { data: accounts } = useSWR<Account[]>("/accounts", fetcher);
  const { data: strategies } = useSWR<Strategy[]>("/strategies", fetcher);
  const [accountId, setAccountId] = useState<string>("");
  const [strategyId, setStrategyId] = useState<string>("");
  const [days, setDays] = useState(14);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<JournalResponse | null>(null);

  async function ask(e?: React.FormEvent) {
    e?.preventDefault();
    if (!accountId && !strategyId) {
      setError("Pick at least an account or a strategy to scope the question.");
      return;
    }
    setBusy(true);
    setError(null);
    setResp(null);
    try {
      const r = await api<JournalResponse>("/ai/journal/ask", {
        method: "POST",
        body: JSON.stringify({
          question,
          account_id: accountId || undefined,
          strategy_id: strategyId || undefined,
          days,
          provider: "anthropic",
        }),
      });
      setResp(r);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Trade journal</h1>
        <p className="text-sm text-muted-foreground">
          Ask the AI about your fills, positions, and strategy performance. It only sees data you
          scope below.
        </p>
      </header>

      <form className="space-y-3" onSubmit={ask}>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="acc">Account</Label>
            <select
              id="acc"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">(none)</option>
              {accounts?.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.kind})
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="strat">Strategy</Label>
            <select
              id="strat"
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">(none)</option>
              {strategies?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="days">Lookback (days)</Label>
            <input
              id="days"
              type="number"
              min={1}
              max={180}
              value={days}
              onChange={(e) => setDays(Math.max(1, Math.min(180, Number(e.target.value) || 14)))}
              className="h-10 w-full rounded-md border border-input bg-background px-3 font-mono text-sm tabular-nums"
            />
          </div>
        </div>

        <div className="space-y-1">
          <Label htmlFor="q">Question</Label>
          <Textarea
            id="q"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={4}
            placeholder="e.g. Why has my equity been bleeding the last 5 days?"
          />
          <div className="flex flex-wrap gap-1 pt-1">
            {PRESET_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setQuestion(p)}
                className="rounded-md border bg-card px-2 py-1 text-xs text-muted-foreground hover:bg-secondary/40"
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex justify-end">
          <Button type="submit" disabled={busy || question.trim().length < 4}>
            {busy ? "Thinking…" : "Ask"}
          </Button>
        </div>
      </form>

      {resp && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between text-sm">
              <span>Answer</span>
              <span className="text-[10px] font-normal text-muted-foreground">
                {resp.model} · {resp.prompt_tokens} in · {resp.completion_tokens} out · $
                {resp.cost_usd.toFixed(4)} · {resp.duration_ms}ms
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <article
              className={cn(
                "prose prose-sm prose-invert max-w-none",
                "[&_h2]:mt-3 [&_h3]:mt-2 [&_li]:my-0 [&_p]:my-2 [&_ul]:my-2",
              )}
            >
              {resp.answer.split("\n").map((line, i) => (
                <p key={i} className={line.trim() ? undefined : "h-2"}>
                  {line || " "}
                </p>
              ))}
            </article>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
