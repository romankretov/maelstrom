from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class EngineBar:
    source: str
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Position:
    symbol: str
    qty: float = 0.0  # signed: +long, -short, 0 flat
    avg_price: float = 0.0


@dataclass(slots=True)
class Fill:
    symbol: str
    side: str  # "buy" | "sell"
    qty: float  # always positive
    price: float
    fee: float
    ts: datetime
    reason: str | None = None
    pnl: float = 0.0  # realized PnL on this fill (closing portion)


@dataclass(slots=True)
class EquityPoint:
    ts: datetime
    equity: float
    drawdown: float


@dataclass(slots=True)
class Metrics:
    total_return: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0
    calmar: float = 0.0
    win_rate: float = 0.0
    trade_count: int = 0
    final_equity: float = 0.0
    initial_capital: float = 0.0
    profit_factor: float = 0.0


@dataclass(slots=True)
class BacktestResult:
    fills: list[Fill] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
