export type LLMProvider = {
  name: "openai" | "anthropic";
  default_model: string | null;
  enabled: boolean;
  has_key: boolean;
  updated_at: string;
};

export type StrategyGenResponse = {
  code: string;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  cost_usd: number;
  duration_ms: number;
};

export const MODEL_OPTIONS: Record<string, string[]> = {
  anthropic: ["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
  openai: ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini"],
};
