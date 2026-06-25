export type LiveStatus =
  | "paused"
  | "pending_start"
  | "running"
  | "pending_stop"
  | "stopped"
  | "failed";

export type LiveStrategy = {
  id: string;
  strategy_id: string;
  strategy_version_id: string;
  account_id: string;
  source: string;
  symbols: string[];
  timeframe: string;
  params: Record<string, unknown>;
  status: LiveStatus;
  error: string | null;
  shadow_mode: boolean;
  started_at: string | null;
  stopped_at: string | null;
  requester_id: string | null;
  created_at: string;
  updated_at: string;
};

export function liveStatusColor(status: LiveStatus): string {
  switch (status) {
    case "running":
      return "bg-emerald-500/15 text-emerald-400";
    case "pending_start":
    case "pending_stop":
      return "bg-yellow-500/15 text-yellow-400 animate-pulse";
    case "stopped":
    case "paused":
      return "bg-muted text-muted-foreground";
    case "failed":
      return "bg-destructive/15 text-destructive";
  }
}
