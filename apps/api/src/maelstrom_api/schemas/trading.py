import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: str
    owner_id: uuid.UUID | None = None
    starting_capital: Decimal
    is_active: bool
    killed: bool = False
    daily_loss_limit_pct: Decimal | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="paper")
    starting_capital: Decimal = Field(default=Decimal("10000"))
    daily_loss_limit_pct: Decimal | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AccountUpdate(BaseModel):
    is_active: bool | None = None
    daily_loss_limit_pct: Decimal | None = None
    meta: dict[str, Any] | None = None


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    symbol: str
    qty: Decimal
    avg_price: Decimal
    realized_pnl: Decimal
    last_price: Decimal
    updated_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    live_strategy_id: uuid.UUID | None = None
    source: str
    symbol: str
    side: str
    qty: Decimal
    price: Decimal | None = None
    order_type: str
    status: str
    filled_qty: Decimal
    avg_fill_price: Decimal
    error: str | None = None
    reason: str | None = None
    exchange_order_id: str | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class FillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    account_id: uuid.UUID
    symbol: str
    side: str
    qty: Decimal
    price: Decimal
    fee: Decimal
    pnl: Decimal
    ts: datetime


class PortfolioSummary(BaseModel):
    account: AccountOut
    cash: Decimal
    equity: Decimal
    total_return: float
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    open_positions: int
    positions: list[PositionOut]
    recent_fills: list[FillOut]


class EquityPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    equity: Decimal
    cash: Decimal
