export type Source = {
  name: string;
  label: string;
  asset_kinds: string[];
};

export type Instrument = {
  source: string;
  symbol: string;
  raw_symbol: string;
  base: string;
  quote: string;
  kind: string;
  active: boolean;
  meta: Record<string, unknown>;
  volume_24h?: number | null;
  change_24h?: number | null;
};

export type InstrumentSort = "alpha" | "volume" | "change_24h";

export type Bar = {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  trades_count: number | null;
};

export const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
export type Timeframe = (typeof TIMEFRAMES)[number];
