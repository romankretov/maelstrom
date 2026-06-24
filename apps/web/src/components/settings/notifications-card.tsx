"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api, fetcher } from "@/lib/api";
import { ALL_EVENTS, type NotificationChannel, type NotificationKind } from "@/lib/notifications";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { cn } from "@/lib/utils";

function NewChannelDialog() {
  const { mutate } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<NotificationKind>("telegram");
  const [label, setLabel] = useState("");
  const [chatId, setChatId] = useState("");
  const [botToken, setBotToken] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        kind,
        label,
        events: [...ALL_EVENTS],
      };
      if (kind === "telegram") {
        body.config = { chat_id: chatId };
        body.secret = botToken;
      } else {
        body.config = { webhook_url: webhookUrl };
      }
      await api("/notifications/channels", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setOpen(false);
      setLabel("");
      setChatId("");
      setBotToken("");
      setWebhookUrl("");
      await mutate("/notifications/channels");
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
        <Button size="sm">Add channel</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>New notification channel</DialogTitle>
            <DialogDescription>
              Telegram bot token is encrypted at rest with the VPS master key, like all other
              secrets. Webhook URLs for Discord aren&apos;t treated as secret.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3 py-4">
            <div className="space-y-1">
              <Label>Kind</Label>
              <div className="flex gap-1">
                {(["telegram", "discord"] as const).map((k) => (
                  <Button
                    key={k}
                    type="button"
                    variant={kind === k ? "default" : "ghost"}
                    size="sm"
                    className="h-8"
                    onClick={() => setKind(k)}
                  >
                    {k}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="label">Label</Label>
              <Input
                id="label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                required
                placeholder="e.g. Phone / Discord #trading"
              />
            </div>

            {kind === "telegram" ? (
              <>
                <div className="space-y-1">
                  <Label htmlFor="chat">Chat ID</Label>
                  <Input
                    id="chat"
                    value={chatId}
                    onChange={(e) => setChatId(e.target.value)}
                    required
                    placeholder="123456789 — message @userinfobot to get yours"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="bot">Bot token</Label>
                  <Input
                    id="bot"
                    type="password"
                    value={botToken}
                    onChange={(e) => setBotToken(e.target.value)}
                    required
                    placeholder="from @BotFather"
                  />
                </div>
              </>
            ) : (
              <div className="space-y-1">
                <Label htmlFor="hook">Webhook URL</Label>
                <Input
                  id="hook"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  required
                  placeholder="https://discord.com/api/webhooks/..."
                />
              </div>
            )}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={busy}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ChannelRow({ c }: { c: NotificationChannel }) {
  const { mutate } = useSWRConfig();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function call(verb: "test" | "delete" | "toggle") {
    setBusy(verb);
    setError(null);
    try {
      if (verb === "test") {
        await api(`/notifications/channels/${c.id}/test`, { method: "POST" });
      } else if (verb === "delete") {
        if (!confirm(`Delete channel "${c.label}"?`)) {
          return;
        }
        await api(`/notifications/channels/${c.id}`, { method: "DELETE" });
      } else if (verb === "toggle") {
        await api(`/notifications/channels/${c.id}`, {
          method: "PATCH",
          body: JSON.stringify({ enabled: !c.enabled }),
        });
      }
      await mutate("/notifications/channels");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : String((e as { message?: string }).message ?? "Failed"),
      );
    } finally {
      setBusy(null);
    }
  }

  async function toggleEvent(event: string) {
    const next = c.events.includes(event)
      ? c.events.filter((e) => e !== event)
      : [...c.events, event];
    await api(`/notifications/channels/${c.id}`, {
      method: "PATCH",
      body: JSON.stringify({ events: next }),
    });
    await mutate("/notifications/channels");
  }

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm">
          <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase">{c.kind}</span>
          <span className="font-medium">{c.label}</span>
          {!c.enabled && (
            <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-[10px] uppercase text-destructive">
              disabled
            </span>
          )}
        </div>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => call("test")}
            disabled={busy !== null}
          >
            {busy === "test" ? "…" : "Test"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => call("toggle")}
            disabled={busy !== null}
          >
            {c.enabled ? "Disable" : "Enable"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-destructive"
            onClick={() => call("delete")}
            disabled={busy !== null}
          >
            Delete
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        {ALL_EVENTS.map((e) => {
          const on = c.events.includes(e);
          return (
            <button
              key={e}
              type="button"
              onClick={() => toggleEvent(e)}
              className={cn(
                "rounded px-1.5 py-0.5 text-[10px] uppercase",
                on
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "border border-input text-muted-foreground hover:bg-secondary/40",
              )}
            >
              {e.replace("_", " ")}
            </button>
          );
        })}
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

export function NotificationsCard() {
  const { data, isLoading } = useSWR<NotificationChannel[]>("/notifications/channels", fetcher);

  return (
    <Card className="lg:col-span-2">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base">Notifications</CardTitle>
        <NewChannelDialog />
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {data && data.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No channels yet. Add Telegram (bot + chat) or a Discord webhook.
          </p>
        )}
        {data?.map((c) => (
          <ChannelRow key={c.id} c={c} />
        ))}
      </CardContent>
    </Card>
  );
}
