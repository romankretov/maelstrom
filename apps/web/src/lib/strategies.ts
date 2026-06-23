export type StrategyVersion = {
  id: string;
  version: number;
  code: string;
  params: Record<string, unknown>;
  author_id: string | null;
  message: string | null;
  created_at: string;
};

export type Strategy = {
  id: string;
  name: string;
  description: string | null;
  owner_id: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  latest_version: StrategyVersion | null;
};

export const STARTER_CODE = `# Maelstrom strategy — Phase 2.0 scaffold
# The full SDK lands in P2.1; this is just for storage.
class MyStrategy:
    symbols = ["BTC-PERP"]
    timeframe = "1h"
    sma_period = 20

    def on_bar(self, bar):
        # Buy when close crosses above the running SMA.
        # (Engine + helpers wired in Phase 2.1.)
        ...
`;
