"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Sparkles } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { type LLMProvider, MODEL_OPTIONS } from "@/lib/ai";
import type { StrategyVersion } from "@/lib/strategies";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type OptimizeResponse = {
  rationale: string;
  code: string;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  cost_usd: number;
  duration_ms: number;
};

export function OptimizeDialog({ runId, strategyId }: { runId: string; strategyId: string }) {
  const router = useRouter();
  const { data: providers } = useSWR<LLMProvider[]>("/ai/providers", fetcher);
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState<"anthropic" | "openai">("anthropic");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizeResponse | null>(null);

  const current = providers?.find((p) => p.name === provider);
  const canSubmit = !!current?.has_key && current.enabled;

  async function runOptimize() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const resp = await api<OptimizeResponse>("/ai/strategies/optimize", {
        method: "POST",
        body: JSON.stringify({
          backtest_run_id: runId,
          provider,
          ...(model ? { model } : {}),
        }),
      });
      setResult(resp);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  async function applyAsNewVersion() {
    if (!result) return;
    setApplying(true);
    setError(null);
    try {
      const v = await api<StrategyVersion>(`/strategies/${strategyId}/versions`, {
        method: "POST",
        body: JSON.stringify({
          code: result.code,
          message: `AI optimize (${result.provider} ${result.model})`,
        }),
      });
      setOpen(false);
      router.push(`/strategies/${strategyId}?v=${v.version}`);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setApplying(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Sparkles className="h-4 w-4" /> Optimize with AI
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>AI strategy optimizer</DialogTitle>
          <DialogDescription>
            The model sees your code + this run&apos;s metrics and suggests one focused change. You
            decide whether to save it as a new version.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-4">
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-1">
              <Label>Provider</Label>
              <div className="flex gap-1">
                {(["anthropic", "openai"] as const).map((p) => (
                  <Button
                    key={p}
                    type="button"
                    variant={p === provider ? "default" : "ghost"}
                    size="sm"
                    className="h-8"
                    onClick={() => {
                      setProvider(p);
                      setModel("");
                    }}
                  >
                    {p}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="opt-model">Model</Label>
              <Input
                id="opt-model"
                list={`opt-${provider}-models`}
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={current?.default_model ?? MODEL_OPTIONS[provider][0]}
              />
              <datalist id={`opt-${provider}-models`}>
                {MODEL_OPTIONS[provider].map((m) => (
                  <option value={m} key={m} />
                ))}
              </datalist>
            </div>
          </div>

          {current && !current.has_key && (
            <p className="text-xs text-destructive">
              No API key configured for {provider} — set it in Settings.
            </p>
          )}

          {result && (
            <div className="space-y-3">
              <div>
                <Label className="text-xs uppercase text-muted-foreground">Rationale</Label>
                <p className="mt-1 whitespace-pre-wrap rounded-md border bg-card p-3 text-sm">
                  {result.rationale}
                </p>
              </div>
              <div>
                <Label className="text-xs uppercase text-muted-foreground">Proposed code</Label>
                <pre className="mt-1 max-h-72 overflow-auto rounded-md border bg-card p-3 font-mono text-xs">
                  {result.code}
                </pre>
              </div>
              <p className="text-xs text-muted-foreground">
                {result.model} · in:{result.prompt_tokens}
                {result.cached_tokens > 0 && ` (${result.cached_tokens} cached)`} · out:
                {result.completion_tokens} · ${result.cost_usd.toFixed(4)} · {result.duration_ms}ms
              </p>
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter className="flex-wrap">
          <DialogClose asChild>
            <Button type="button" variant="ghost" disabled={busy || applying}>
              Close
            </Button>
          </DialogClose>
          {!result && (
            <Button type="button" onClick={runOptimize} disabled={busy || !canSubmit}>
              {busy ? "Asking model…" : "Get suggestion"}
            </Button>
          )}
          {result && (
            <>
              <Button type="button" variant="ghost" onClick={() => setResult(null)}>
                Discard
              </Button>
              <Button type="button" onClick={applyAsNewVersion} disabled={applying}>
                {applying ? "Saving…" : "Apply as new version"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
