import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    symbol: str
    raw_symbol: str
    base: str
    quote: str
    kind: str
    active: bool
    meta: dict[str, Any] = Field(default_factory=dict)
    # Optional ranking columns — populated when sort=volume or sort=change.
    volume_24h: float | None = None
    change_24h: float | None = None


class BarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades_count: int | None = None


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    trade_id: str
    price: float
    qty: float
    side: str


class BackfillRequest(BaseModel):
    source: str
    symbol: str
    timeframe: str
    range_start: datetime
    range_end: datetime


class BulkBackfillRequest(BaseModel):
    source: str
    symbols: list[str]  # one job per symbol x timeframe
    timeframes: list[str]
    range_start: datetime
    range_end: datetime


class BulkBackfillResponse(BaseModel):
    queued: int
    job_ids: list[uuid.UUID]


class BackfillJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    symbol: str
    timeframe: str
    range_start: datetime
    range_end: datetime
    status: str
    bars_written: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceOut(BaseModel):
    name: str
    label: str
    asset_kinds: list[str]
