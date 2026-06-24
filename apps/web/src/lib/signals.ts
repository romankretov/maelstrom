export type Signal = {
  id: string;
  scanner: string;
  source: string;
  symbol: string;
  direction: "long" | "short" | "neutral";
  score: string;
  confidence: string | null;
  horizon: string | null;
  rationale: string;
  context: Record<string, unknown>;
  llm_call_id: string | null;
  ts: string;
  expires_at: string | null;
};

export function directionTone(d: Signal["direction"]): string {
  switch (d) {
    case "long":
      return "text-emerald-400 bg-emerald-500/15";
    case "short":
      return "text-destructive bg-destructive/15";
    case "neutral":
      return "text-muted-foreground bg-muted";
  }
}
