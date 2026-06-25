import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LiveStrategyCreate(BaseModel):
    account_id: uuid.UUID
    source: str
    symbols: list[str] = Field(min_length=1)
    timeframe: str
    params: dict[str, Any] = Field(default_factory=dict)
    strategy_version_id: uuid.UUID | None = None
    max_notional_per_symbol: Decimal | None = None
    max_position_qty: Decimal | None = None
    shadow_mode: bool = False


class LiveStrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID
    account_id: uuid.UUID
    source: str
    symbols: list[str]
    timeframe: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: str
    error: str | None = None
    max_notional_per_symbol: Decimal | None = None
    max_position_qty: Decimal | None = None
    shadow_mode: bool = False
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    requester_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ShadowFillOut(BaseModel):
    id: uuid.UUID
    live_strategy_id: uuid.UUID
    ts: datetime
    symbol: str
    side: str
    qty: float
    price: float
    notional: float
    fee: float
    pnl: float
    reason: str | None = None
