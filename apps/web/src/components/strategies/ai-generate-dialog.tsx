"use client";

import { useState } from "react";
import useSWR from "swr";
import { Sparkles } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { type LLMProvider, MODEL_OPTIONS, type StrategyGenResponse } from "@/lib/ai";
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
import { Textarea } from "@/components/ui/textarea";

export function AiGenerateDialog({
  onCode,
  size = "sm",
}: {
  onCode: (code: string) => void;
  size?: "sm" | "default" | "lg";
}) {
  const { data: providers } = useSWR<LLMProvider[]>("/ai/providers", fetcher);
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState<"anthropic" | "openai">("anthropic");
  const [model, setModel] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<StrategyGenResponse | null>(null);

  const current = providers?.find((p) => p.name === provider);
  const canSubmit = !!current?.has_key && current.enabled && prompt.trim().length > 4;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const resp = await api<StrategyGenResponse>("/ai/strategies/generate", {
        method: "POST",
        body: JSON.stringify({
          prompt,
          provider,
          ...(model ? { model } : {}),
        }),
      });
      setLast(resp);
      onCode(resp.code);
      setOpen(false);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size={size}>
          <Sparkles className="h-4 w-4" /> Generate with AI
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Generate strategy with AI</DialogTitle>
            <DialogDescription>
              Describe what you want. The model writes Maelstrom Strategy code; you stay in control
              of saving and backtesting it.
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
                <Label htmlFor="model">Model</Label>
                <Input
                  id="model"
                  list={`${provider}-models`}
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder={current?.default_model ?? MODEL_OPTIONS[provider][0]}
                />
                <datalist id={`${provider}-models`}>
                  {MODEL_OPTIONS[provider].map((m) => (
                    <option value={m} key={m} />
                  ))}
                </datalist>
              </div>
            </div>

            {current && !current.has_key && (
              <p className="text-xs text-destructive">
                No API key configured for {provider} — set it in Settings first.
              </p>
            )}

            <div className="space-y-1">
              <Label htmlFor="prompt">Prompt</Label>
              <Textarea
                id="prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={6}
                placeholder="Write a momentum strategy on BTC-PERP at 4h timeframe that goes long after price closes above a 30-bar high and exits on a 10-bar low. Position size: $5000."
              />
            </div>

            {last && (
              <p className="text-xs text-muted-foreground">
                Last run: {last.model} · in:{last.prompt_tokens}{" "}
                {last.cached_tokens > 0 && `(${last.cached_tokens} cached)`} · out:
                {last.completion_tokens} · ${last.cost_usd.toFixed(4)} · {last.duration_ms}ms
              </p>
            )}
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={busy}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy || !canSubmit}>
              {busy ? "Generating…" : "Generate"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
