export type NotificationKind = "telegram" | "discord";

export const ALL_EVENTS = [
  "kill_account",
  "backtest_done",
  "signal_top",
  "live_failed",
  "fill",
  "order_rejected",
  "daily_summary",
] as const;
export type NotificationEvent = (typeof ALL_EVENTS)[number];

export type NotificationChannel = {
  id: string;
  user_id: string;
  kind: NotificationKind;
  label: string;
  config: Record<string, unknown>;
  has_secret: boolean;
  enabled: boolean;
  events: string[];
  quiet_start: string | null;
  quiet_end: string | null;
  created_at: string;
  updated_at: string;
};
