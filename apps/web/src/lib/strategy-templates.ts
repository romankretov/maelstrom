// Strategy starter templates. Each one is a fully-working strategy whose
// header docstring is the canonical SDK reference — so a developer who
// picks any template gets the docs side-by-side with working code in
// their editor. Keep these in sync with apps/worker/.../engine/sdk.py.

export type StrategyTemplate = {
  id: string;
  name: string;
  description: string;
  code: string;
};

const SDK_HEADER = `"""
Maelstrom Strategy SDK reference
================================

This file IS your strategy. Edit the class body — the runtime calls
methods on the class for every bar of market data.

Lifecycle:
    on_init()           runs once before the first bar
    on_bar(bar)         runs for every bar in time order

Class attributes you should set:
    symbols   = ("BTC-PERP",)  tuple of symbols to subscribe to
    timeframe = "1h"           one of "1m" | "5m" | "15m" | "1h" | "4h" | "1d"

Order placement (market orders, fill at last close +/- slippage):
    self.buy(symbol, notional=USD, reason="...")     open or add to a long
    self.sell(symbol, notional=USD, reason="...")    open or add to a short
    self.close(symbol, reason="...")                 close any open position

Account state (read-only):
    self.position(symbol) -> Position
        .qty            signed quantity (positive long, negative short)
        .avg_price      average entry price
        .unrealized_pnl
    self.history(symbol, n=N) -> list[Bar]
        Most-recent N bars in CHRONOLOGICAL order (oldest first, newest
        last). Capped at N — first N-1 bars after start you'll get fewer.
        NOT an ever-growing counter; if you need one, track it yourself.
    self.cash       -> float (USDC)
    self.equity     -> float (cash + position MTM)
    self.params     -> dict (whatever the backtest / live form sent)

Bar fields:
    bar.ts, .open, .high, .low, .close, .volume, .symbol

Gotchas:
    1. on_bar fires AFTER the bar closes -- bar.close is final.
    2. history(n=N) returns AT MOST N bars; for the first N-1 bars
       you'll get fewer. Guard with: if len(history) < N: return.
    3. No built-in bar counter. Track one in on_init() if you need it.
    4. Identical code runs in backtest and live. Keep on_bar idempotent.
"""
`;

const EMPTY = `${SDK_HEADER}
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar


class MyStrategy(Strategy):
    symbols = ("BTC-PERP",)
    timeframe = "1h"

    def on_init(self) -> None:
        pass

    def on_bar(self, bar: EngineBar) -> None:
        # Your logic here.
        pass
`;

const BUY_AND_HOLD = `${SDK_HEADER}
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar


class BuyAndHold(Strategy):
    """Open a long once on the first bar and hold forever."""

    symbols = ("BTC-PERP",)
    timeframe = "1h"

    def on_init(self) -> None:
        self.bought = False

    def on_bar(self, bar: EngineBar) -> None:
        if not self.bought:
            self.buy(bar.symbol, notional=self.params.get("notional", 1000), reason="entry")
            self.bought = True
`;

const SMA_CROSS = `${SDK_HEADER}
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar


def _sma(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


class SmaCross(Strategy):
    """Go long when the fast SMA crosses above the slow SMA, flat otherwise.

    Tune via params: {"sma_short": 5, "sma_long": 20, "notional": 1000}.
    """

    symbols = ("BTC-PERP",)
    timeframe = "1h"

    def on_init(self) -> None:
        self.prev_diff: float | None = None

    def on_bar(self, bar: EngineBar) -> None:
        short_n = int(self.params.get("sma_short", 5))
        long_n = int(self.params.get("sma_long", 20))
        notional = float(self.params.get("notional", 1000))

        history = self.history(bar.symbol, n=long_n)
        if len(history) < long_n:
            return

        # history is chronological (oldest first), so the newest closes
        # are at the end of the list.
        closes = [b.close for b in history]
        short_sma = _sma(closes[-short_n:])
        long_sma = _sma(closes[-long_n:])
        diff = short_sma - long_sma

        pos = self.position(bar.symbol)
        if self.prev_diff is not None:
            crossed_up = self.prev_diff <= 0 < diff
            crossed_down = self.prev_diff >= 0 > diff
            if crossed_up and pos.qty <= 0:
                if pos.qty < 0:
                    self.close(bar.symbol, reason="cross-up: cover short")
                self.buy(bar.symbol, notional=notional, reason="sma cross up")
            elif crossed_down and pos.qty > 0:
                self.close(bar.symbol, reason="sma cross down")

        self.prev_diff = diff
`;

const BREAKOUT = `${SDK_HEADER}
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar


class DonchianBreakout(Strategy):
    """Buy on a new N-bar high; close when the close drops below the
    N-bar low. Long-only, single position at a time.

    Params: {"lookback": 20, "notional": 1000}.
    """

    symbols = ("BTC-PERP",)
    timeframe = "1h"

    def on_bar(self, bar: EngineBar) -> None:
        n = int(self.params.get("lookback", 20))
        notional = float(self.params.get("notional", 1000))

        # n+1 so we have n PRIOR bars plus the current one.
        history = self.history(bar.symbol, n=n + 1)
        if len(history) < n + 1:
            return

        # history is oldest-first; history[-1] is the current bar. The
        # n-bar lookback window is everything BEFORE the current bar.
        window = history[:-1]
        upper = max(b.high for b in window)
        lower = min(b.low for b in window)

        pos = self.position(bar.symbol)
        if pos.qty == 0 and bar.close > upper:
            self.buy(bar.symbol, notional=notional, reason=f"break above {upper:.2f}")
        elif pos.qty > 0 and bar.close < lower:
            self.close(bar.symbol, reason=f"break below {lower:.2f}")
`;

const RSI = `${SDK_HEADER}
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar


def _rsi(closes: list[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))


class RsiMeanReversion(Strategy):
    """Buy when RSI < oversold threshold, close when RSI > exit threshold.

    Params: {"period": 14, "oversold": 30, "exit": 55, "notional": 1000}.
    """

    symbols = ("BTC-PERP",)
    timeframe = "1h"

    def on_bar(self, bar: EngineBar) -> None:
        period = int(self.params.get("period", 14))
        oversold = float(self.params.get("oversold", 30))
        exit_at = float(self.params.get("exit", 55))
        notional = float(self.params.get("notional", 1000))

        history = self.history(bar.symbol, n=period + 1)
        if len(history) < period + 1:
            return

        # history is already chronological (oldest first).
        closes = [b.close for b in history]
        rsi = _rsi(closes, period)

        pos = self.position(bar.symbol)
        if pos.qty == 0 and rsi < oversold:
            self.buy(bar.symbol, notional=notional, reason=f"rsi={rsi:.1f} oversold")
        elif pos.qty > 0 and rsi > exit_at:
            self.close(bar.symbol, reason=f"rsi={rsi:.1f} exit")
`;

const MOMENTUM = `${SDK_HEADER}
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar


class TrailingMomentum(Strategy):
    """Long when the N-bar return is positive; flat otherwise. Adds a
    simple trailing stop on the position high.

    Params: {"lookback": 12, "stop_pct": 0.03, "notional": 1000}.
    """

    symbols = ("BTC-PERP",)
    timeframe = "1h"

    def on_init(self) -> None:
        self.position_high: float = 0.0

    def on_bar(self, bar: EngineBar) -> None:
        lookback = int(self.params.get("lookback", 12))
        stop_pct = float(self.params.get("stop_pct", 0.03))
        notional = float(self.params.get("notional", 1000))

        history = self.history(bar.symbol, n=lookback + 1)
        if len(history) < lookback + 1:
            return

        # chronological: history[0] is oldest, history[-1] is current bar.
        ret = (history[-1].close - history[0].close) / history[0].close
        pos = self.position(bar.symbol)

        if pos.qty == 0 and ret > 0:
            self.buy(bar.symbol, notional=notional, reason=f"{lookback}-bar momentum +{ret:.2%}")
            self.position_high = bar.close
        elif pos.qty > 0:
            self.position_high = max(self.position_high, bar.high)
            drawdown = (bar.close - self.position_high) / self.position_high
            if drawdown <= -stop_pct:
                self.close(bar.symbol, reason=f"trail stop {drawdown:.2%}")
                self.position_high = 0.0
`;

export const STRATEGY_TEMPLATES: StrategyTemplate[] = [
  {
    id: "empty",
    name: "Empty",
    description: "Bare skeleton + SDK reference. Pick this when you want to write from scratch.",
    code: EMPTY,
  },
  {
    id: "buy-and-hold",
    name: "Buy & hold",
    description: "Opens one long on the first bar and never sells. Useful as a benchmark.",
    code: BUY_AND_HOLD,
  },
  {
    id: "sma-cross",
    name: "SMA cross",
    description: "Long when the short SMA crosses above the long SMA, flat below.",
    code: SMA_CROSS,
  },
  {
    id: "donchian-breakout",
    name: "Donchian breakout",
    description: "Buy on new N-bar highs, exit on new N-bar lows. Trend-follower.",
    code: BREAKOUT,
  },
  {
    id: "rsi-mean-reversion",
    name: "RSI mean reversion",
    description: "Buy oversold, exit on RSI recovery. Counter-trend.",
    code: RSI,
  },
  {
    id: "momentum-trailing",
    name: "Momentum + trailing stop",
    description: "Long when N-bar return is positive, exit on configurable trailing drawdown.",
    code: MOMENTUM,
  },
];

export const DEFAULT_TEMPLATE_ID = "sma-cross";
