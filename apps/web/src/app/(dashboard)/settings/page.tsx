"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import { type LLMProvider, MODEL_OPTIONS } from "@/lib/ai";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const PROVIDERS: { id: "anthropic" | "openai"; label: string }[] = [
  { id: "anthropic", label: "Anthropic (Claude)" },
  { id: "openai", label: "OpenAI" },
];

function ProviderCard({ id, label }: { id: "anthropic" | "openai"; label: string }) {
  const { mutate } = useSWRConfig();
  const { data } = useSWR<LLMProvider[]>("/ai/providers", fetcher);
  const current = data?.find((p) => p.name === id);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      if (apiKey.trim()) body.api_key = apiKey.trim();
      if (model.trim()) body.default_model = model.trim();
      if (Object.keys(body).length === 0) {
        setError("Nothing to save — set the key or a default model.");
        return;
      }
      await api(`/ai/providers/${id}`, { method: "PUT", body: JSON.stringify(body) });
      setApiKey("");
      await mutate("/ai/providers");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  async function toggle() {
    if (!current) return;
    try {
      await api(`/ai/providers/${id}`, {
        method: "PUT",
        body: JSON.stringify({ enabled: !current.enabled }),
      });
      await mutate("/ai/providers");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between text-base">
          {label}
          {current && (
            <span className="flex items-center gap-2 text-xs">
              {current.has_key ? (
                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-400">
                  key set
                </span>
              ) : (
                <span className="rounded bg-yellow-500/15 px-1.5 py-0.5 text-yellow-400">
                  no key
                </span>
              )}
              {current.enabled ? (
                <span className="rounded bg-secondary px-1.5 py-0.5 text-muted-foreground">
                  enabled
                </span>
              ) : (
                <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-destructive">
                  disabled
                </span>
              )}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor={`${id}-key`}>API key</Label>
          <Input
            id={`${id}-key`}
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={current?.has_key ? "(replace existing — leave empty to keep)" : "sk-…"}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`${id}-model`}>Default model</Label>
          <Input
            id={`${id}-model`}
            list={`${id}-models`}
            value={model || current?.default_model || ""}
            onChange={(e) => setModel(e.target.value)}
            placeholder={MODEL_OPTIONS[id][0]}
          />
          <datalist id={`${id}-models`}>
            {MODEL_OPTIONS[id].map((m) => (
              <option value={m} key={m} />
            ))}
          </datalist>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          {current && (
            <Button variant="ghost" size="sm" onClick={toggle}>
              {current.enabled ? "Disable" : "Enable"}
            </Button>
          )}
          <Button size="sm" onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          API keys are encrypted at rest with the VPS master key.
        </p>
      </header>
      <div className="grid gap-4 lg:grid-cols-2">
        {PROVIDERS.map((p) => (
          <ProviderCard key={p.id} id={p.id} label={p.label} />
        ))}
      </div>
    </div>
  );
}
