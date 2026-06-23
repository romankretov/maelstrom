"""Common types + Protocol shared by every market data source.

Connectors normalize raw exchange data into these shapes. The worker
writes them straight to TimescaleDB hypertables.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class Instrument:
    source: str  # "binance" | "hyperliquid" | "yfinance"
    symbol: str  # normalized — e.g. "BTC-PERP", "ETH-PERP", "AAPL"
    raw_symbol: str  # exchange-native — e.g. "BTC/USDT:USDT"
    base: str
    quote: str
    kind: str  # "perp" | "spot" | "equity"
    active: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Bar:
    """One OHLCV candle for a (source, symbol, timeframe, ts) cell."""

    source: str
    symbol: str
    timeframe: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades_count: int | None = None


@dataclass(slots=True)
class Trade:
    source: str
    symbol: str
    ts: datetime
    trade_id: str
    price: float
    qty: float
    side: str  # "buy" | "sell"


class MarketDataSource(Protocol):
    """Every connector implements this. Worker tasks consume only this surface."""

    source: str

    async def close(self) -> None: ...

    async def list_instruments(self) -> list[Instrument]: ...

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: datetime,
        limit: int = 1000,
    ) -> list[Bar]:
        """Return bars in the [since, until) range, paginated upstream as needed."""
        ...

    def stream_ohlcv(
        self,
        symbol: str,
        timeframe: str,
    ) -> AsyncIterator[Bar]:
        """Yield bars as they tick + close. Async generator — not `async def` in
        the Protocol since the *factory* returns AsyncIterator directly (no
        await needed)."""
        ...

    def stream_trades(self, symbol: str) -> AsyncIterator[Trade]:
        """Yield trades as they print. See stream_ohlcv re: signature."""
        ...
