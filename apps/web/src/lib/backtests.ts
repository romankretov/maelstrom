export type BacktestStatus = "pending" | "running" | "done" | "failed";

export type BacktestMetrics = {
  total_return: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  calmar: number;
  win_rate: number;
  trade_count: number;
  final_equity: number;
  initial_capital: number;
  profit_factor: number | null;
};

export type BacktestRun = {
  id: string;
  strategy_id: string;
  strategy_version_id: string;
  source: string;
  symbols: string[];
  timeframe: string;
  range_start: string;
  range_end: string;
  initial_capital: string;
  params: Record<string, unknown>;
  status: BacktestStatus;
  error: string | null;
  metrics: BacktestMetrics | null;
  requester_id: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type BacktestEquityPoint = {
  ts: string;
  equity: number;
  drawdown: number;
};

export type BacktestTrade = {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  fee: number;
  pnl: number;
  ts: string;
  reason: string | null;
};

export function statusColor(status: BacktestStatus): string {
  switch (status) {
    case "pending":
      return "bg-yellow-500/15 text-yellow-400";
    case "running":
      return "bg-blue-500/15 text-blue-400";
    case "done":
      return "bg-emerald-500/15 text-emerald-400";
    case "failed":
      return "bg-destructive/15 text-destructive";
  }
}

export function fmtPct(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const sign = x > 0 ? "+" : "";
  return `${sign}${(x * 100).toFixed(2)}%`;
}

export function fmtNum(x: number | null | undefined, digits = 2): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return x.toFixed(digits);
}

export function fmtMoney(x: number | null | undefined): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `$${x.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}
