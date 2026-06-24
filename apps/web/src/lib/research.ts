export type MarketStats = {
  source: string;
  symbol: string;
  timeframe: string;
  last_price: number | null;
  change_1h: number | null;
  change_24h: number | null;
  change_7d: number | null;
  change_30d: number | null;
  high_24h: number | null;
  low_24h: number | null;
  volume_24h: number | null;
  realized_vol_24h: number | null;
  realized_vol_7d: number | null;
  bar_count: number;
  earliest_ts: string | null;
  latest_ts: string | null;
};

export type CorrelationOut = {
  source: string;
  timeframe: string;
  days: number;
  symbols: string[];
  matrix: (number | null)[][];
  samples: number[][];
  computed_at: string;
};

export function formatPct(x: number | null | undefined, digits = 2): string {
  if (x == null || !Number.isFinite(x)) return "—";
  const sign = x > 0 ? "+" : "";
  return `${sign}${(x * 100).toFixed(digits)}%`;
}

export function formatPrice(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return "—";
  if (x >= 1000) return x.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (x >= 1) return x.toFixed(4);
  return x.toPrecision(4);
}

export type FundingPoint = {
  ts: string;
  rate: number;
};

export type FundingHistoryOut = {
  source: string;
  symbol: string;
  days: number;
  points: FundingPoint[];
  mean: number | null;
  annualized: number | null;
};

export function formatCompactNumber(x: number | null | undefined): string {
  if (x == null || !Number.isFinite(x)) return "—";
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(x);
}
