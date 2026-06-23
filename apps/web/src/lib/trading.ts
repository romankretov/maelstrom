export type Account = {
  id: string;
  name: string;
  kind: "paper" | "live_hl_testnet" | "live_hl_main";
  owner_id: string | null;
  starting_capital: string;
  is_active: boolean;
  meta: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type PortfolioPosition = {
  account_id: string;
  symbol: string;
  qty: string;
  avg_price: string;
  realized_pnl: string;
  last_price: string;
  updated_at: string;
};

export type PortfolioFill = {
  id: string;
  order_id: string;
  account_id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: string;
  price: string;
  fee: string;
  pnl: string;
  ts: string;
};

export type PortfolioSummary = {
  account: Account;
  cash: string;
  equity: string;
  total_return: number;
  realized_pnl: string;
  unrealized_pnl: string;
  open_positions: number;
  positions: PortfolioPosition[];
  recent_fills: PortfolioFill[];
};

export function num(s: string | number | null | undefined): number {
  if (s === null || s === undefined) return 0;
  return typeof s === "number" ? s : Number(s);
}
