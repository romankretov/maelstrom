"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/strategies";
import {
  DEFAULT_TEMPLATE_ID,
  STRATEGY_TEMPLATES,
  type StrategyTemplate,
} from "@/lib/strategy-templates";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CodeEditor } from "@/components/code-editor";
import { AiGenerateDialog } from "@/components/strategies/ai-generate-dialog";
import { cn } from "@/lib/utils";

const DEFAULT =
  STRATEGY_TEMPLATES.find((t) => t.id === DEFAULT_TEMPLATE_ID) ?? STRATEGY_TEMPLATES[0];

export default function NewStrategy() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [templateId, setTemplateId] = useState(DEFAULT.id);
  const [code, setCode] = useState(DEFAULT.code);
  // Track whether the user has manually edited the code — if so, switching
  // templates would clobber their work. Confirm before doing so.
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pickTemplate(t: StrategyTemplate) {
    if (dirty && !confirm("Replace your current code with this template?")) return;
    setTemplateId(t.id);
    setCode(t.code);
    setDirty(false);
  }

  function onCodeChange(next: string) {
    setCode(next);
    setDirty(true);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const s = await api<Strategy>("/strategies", {
        method: "POST",
        body: JSON.stringify({ name, description: description || null, code }),
      });
      router.push(`/strategies/${s.id}`);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : String((e as { message?: string }).message ?? "Create failed"),
      );
      setBusy(false);
    }
  }

  return (
    <Card className="mx-auto max-w-5xl">
      <CardHeader>
        <CardTitle>New strategy</CardTitle>
        <p className="text-sm text-muted-foreground">
          Pick a template to scaffold from. Each one ships with the full SDK reference at the top of
          the file so you don&apos;t have to remember the API.
        </p>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={submit}>
          <div className="space-y-2">
            <Label>Template</Label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {STRATEGY_TEMPLATES.map((t) => {
                const active = t.id === templateId;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => pickTemplate(t)}
                    className={cn(
                      "rounded-md border p-3 text-left transition-colors",
                      active
                        ? "border-foreground bg-secondary"
                        : "hover:border-secondary hover:bg-secondary/40",
                    )}
                  >
                    <div className="font-medium">{t.name}</div>
                    <div className="text-xs text-muted-foreground">{t.description}</div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={120}
                placeholder="sma-cross-btc"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="(optional) one-line summary"
              />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Code</Label>
              <div className="flex items-center gap-2">
                {dirty && (
                  <span className="text-xs text-muted-foreground">edited from template</span>
                )}
                <AiGenerateDialog
                  onCode={(c) => {
                    setCode(c);
                    setDirty(true);
                  }}
                />
              </div>
            </div>
            <CodeEditor value={code} onChange={onCodeChange} height={520} />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => router.back()}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
