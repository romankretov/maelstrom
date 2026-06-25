"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import type { Strategy, StrategyVersion } from "@/lib/strategies";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CodeEditor } from "@/components/code-editor";
import { AiGenerateDialog } from "@/components/strategies/ai-generate-dialog";
import { BacktestForm } from "@/components/strategies/backtest-form";
import { SweepForm } from "@/components/strategies/sweep-form";
import { BacktestList } from "@/components/strategies/backtest-list";
import { LiveList } from "@/components/strategies/live-list";
import { RunLiveForm } from "@/components/strategies/run-live-form";

export default function StrategyEditor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const { data: strategy, error, isLoading } = useSWR<Strategy>(`/strategies/${id}`, fetcher);
  const { data: versions } = useSWR<StrategyVersion[]>(`/strategies/${id}/versions`, fetcher);

  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [description, setDescription] = useState("");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!strategy) return;
    setCode(strategy.latest_version?.code ?? "");
    setDescription(strategy.description ?? "");
    setDirty(false);
  }, [strategy?.id, strategy?.latest_version?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function save() {
    setBusy(true);
    setSaveError(null);
    try {
      if (strategy && description !== (strategy.description ?? "")) {
        await api(`/strategies/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ description: description || null }),
        });
      }
      await api<StrategyVersion>(`/strategies/${id}/versions`, {
        method: "POST",
        body: JSON.stringify({ code, message: message || null }),
      });
      setMessage("");
      setDirty(false);
      await Promise.all([
        mutate(`/strategies/${id}`),
        mutate(`/strategies/${id}/versions`),
        mutate("/strategies"),
      ]);
    } catch (e) {
      setSaveError(
        e instanceof Error
          ? e.message
          : String((e as { message?: string }).message ?? "Save failed"),
      );
    } finally {
      setBusy(false);
    }
  }

  async function archive() {
    if (!strategy) return;
    if (!confirm(`Archive "${strategy.name}"?`)) return;
    await api(`/strategies/${id}`, { method: "DELETE" });
    router.push("/strategies");
  }

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error)
    return (
      <p className="text-sm text-destructive">
        {(error as { message?: string }).message ?? "Failed to load strategy."}
      </p>
    );
  if (!strategy) return null;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{strategy.name}</h1>
          <p className="text-xs text-muted-foreground">
            Latest: v{strategy.latest_version?.version ?? "—"} ·{" "}
            {strategy.latest_version
              ? new Date(strategy.latest_version.created_at).toLocaleString()
              : "no versions"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={archive}>
            Archive
          </Button>
          <BacktestForm strategyId={id} dirty={dirty} onSaveFirst={save} />
          <SweepForm strategyId={id} />
          <RunLiveForm strategyId={id} />
          <Button size="sm" onClick={save} disabled={busy || !dirty}>
            {busy ? "Saving…" : "Save version"}
          </Button>
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Code</CardTitle>
            <AiGenerateDialog
              onCode={(c) => {
                setCode(c);
                setDirty(true);
              }}
            />
          </CardHeader>
          <CardContent className="space-y-3">
            <CodeEditor
              value={code}
              onChange={(v) => {
                setCode(v);
                setDirty(true);
              }}
              height={520}
            />
            <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-end">
              <div className="space-y-1">
                <Label htmlFor="message" className="text-xs">
                  Commit message (optional)
                </Label>
                <Input
                  id="message"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="raise SMA period to 50"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="desc" className="text-xs">
                Description
              </Label>
              <Input
                id="desc"
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value);
                  setDirty(true);
                }}
              />
            </div>
            {saveError && <p className="text-sm text-destructive">{saveError}</p>}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <LiveList strategyId={id} />
          <BacktestList strategyId={id} />

          <Card className="h-fit">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Versions</CardTitle>
            </CardHeader>
            <CardContent className="max-h-[40vh] space-y-2 overflow-y-auto">
              {!versions && <p className="text-xs text-muted-foreground">Loading…</p>}
              {versions?.length === 0 && (
                <p className="text-xs text-muted-foreground">No versions yet.</p>
              )}
              {versions?.map((v) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => {
                    if (dirty && !confirm("Discard unsaved changes?")) return;
                    setCode(v.code);
                    setDirty(true);
                  }}
                  className="flex w-full flex-col items-start rounded-md border bg-card px-3 py-2 text-left hover:bg-card/70"
                >
                  <span className="text-sm">
                    v{v.version}
                    {strategy.latest_version?.id === v.id && (
                      <span className="ml-2 rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase">
                        head
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-muted-foreground">{v.message ?? "—"}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(v.created_at).toLocaleString()}
                  </span>
                </button>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
