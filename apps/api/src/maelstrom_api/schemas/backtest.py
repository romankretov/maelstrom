import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BacktestCreate(BaseModel):
    source: str
    symbols: list[str] = Field(min_length=1)
    timeframe: str
    range_start: datetime
    range_end: datetime
    initial_capital: Decimal = Field(default=Decimal("10000"))
    params: dict[str, Any] = Field(default_factory=dict)
    # Optional: pin to a specific version. Defaults to the latest.
    strategy_version_id: uuid.UUID | None = None


class SweepRequest(BaseModel):
    """One numeric param swept across a linear range.

    Inherits the base body's source/symbols/timeframe/range; only `params`
    differs per generated run (with `param_name` overridden by each value).
    """

    base: BacktestCreate
    param_name: str = Field(min_length=1, max_length=64)
    start: float
    stop: float  # inclusive
    steps: int = Field(ge=2, le=50)


class SweepResponse(BaseModel):
    queued: int
    backtest_run_ids: list[uuid.UUID]
    values: list[float]


class BacktestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID
    source: str
    symbols: list[str]
    timeframe: str
    range_start: datetime
    range_end: datetime
    initial_capital: Decimal
    params: dict[str, Any] = Field(default_factory=dict)
    status: str
    error: str | None = None
    metrics: dict[str, Any] | None = None
    requester_id: uuid.UUID | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class EquityPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    equity: float
    drawdown: float


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    side: str
    qty: float
    price: float
    fee: float
    pnl: float
    ts: datetime
    reason: str | None = None


class BacktestDiagnostics(BaseModel):
    """Extra analytics computed from fills + equity. Helps answer
    'why did this strategy win/lose money' beyond the headline metrics."""

    fills_count: int
    winning_fills: int
    losing_fills: int
    longest_winning_streak: int
    longest_losing_streak: int
    largest_win: float
    largest_loss: float
    avg_win: float
    avg_loss: float
    win_rate: float  # fraction (0..1)
    profit_factor: float | None  # gross_profit / |gross_loss|
    expectancy: float  # avg PnL per fill
    time_in_market_pct: float  # fraction of bars where any position held
    max_drawdown: float  # fraction (0..1) — same as headline metric
    longest_drawdown_bars: int  # bars from peak to recovery
    exposure_by_symbol: dict[str, float]  # symbol → total notional traded
    pnl_by_symbol: dict[str, float]
