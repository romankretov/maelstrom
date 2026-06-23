"""Broker abstraction. Backtest uses BacktestEngine (in-memory). Live uses
PaperBroker (DB-backed, simulated fills) or HyperliquidBroker (DB-backed,
real orders — P3.3)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(slots=True)
class OrderIntent:
    account_id: str
    live_strategy_id: str | None
    source: str
    symbol: str
    side: str  # "buy" | "sell"
    qty: float | None = None
    notional: float | None = None
    order_type: str = "market"
    price: float | None = None  # limit price for non-market
    reason: str | None = None
    idempotency_key: str | None = None


@dataclass(slots=True)
class OrderResult:
    order_id: str
    status: str  # "filled" | "rejected" | "partial" | ...
    filled_qty: float
    avg_fill_price: float
    fee: float
    pnl: float
    ts: datetime
    error: str | None = None


class Broker(Protocol):
    """Implementations: PaperBroker, HyperliquidBroker."""

    async def submit(self, intent: OrderIntent, last_price: float) -> OrderResult: ...

    async def update_mark(self, account_id: str, symbol: str, last_price: float) -> None: ...
