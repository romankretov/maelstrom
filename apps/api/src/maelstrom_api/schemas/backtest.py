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
