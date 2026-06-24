from datetime import datetime

from pydantic import BaseModel, Field


class MarketStats(BaseModel):
    source: str
    symbol: str
    timeframe: str
    last_price: float | None = None
    change_1h: float | None = None
    change_24h: float | None = None
    change_7d: float | None = None
    change_30d: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    volume_24h: float | None = None
    realized_vol_24h: float | None = None  # annualized, as a fraction (0.65 = 65%)
    realized_vol_7d: float | None = None
    bar_count: int = 0
    earliest_ts: datetime | None = None
    latest_ts: datetime | None = None


class CorrelationRequest(BaseModel):
    source: str
    symbols: list[str] = Field(min_length=2, max_length=20)
    timeframe: str = "1h"
    days: int = Field(default=30, ge=1, le=365)


class CorrelationOut(BaseModel):
    source: str
    timeframe: str
    days: int
    symbols: list[str]
    matrix: list[list[float | None]]
    # Number of overlapping return samples per pair (square, symmetric).
    samples: list[list[int]]
    computed_at: datetime
