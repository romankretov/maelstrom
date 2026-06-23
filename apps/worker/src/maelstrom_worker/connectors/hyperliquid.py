"""Hyperliquid perpetuals via ccxt.pro (REST + WS in one client)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import ccxt.pro as ccxtpro
import structlog

from .base import Bar, Instrument, Trade

log = structlog.get_logger()


def _normalize_symbol(raw: str) -> str:
    """Hyperliquid perp symbols look like "BTC/USDC:USDC". Normalize to "BTC-PERP"."""
    base = raw.split("/", 1)[0]
    return f"{base}-PERP"


def _to_ms(ts: datetime) -> int:
    return int(ts.timestamp() * 1000)


class HyperliquidSource:
    source = "hyperliquid"

    def __init__(self) -> None:
        self._ex = ccxtpro.hyperliquid({"enableRateLimit": True})

    async def close(self) -> None:
        await self._ex.close()

    async def list_instruments(self) -> list[Instrument]:
        markets: dict[str, Any] = await self._ex.load_markets()
        out: list[Instrument] = []
        for raw, m in markets.items():
            if not m.get("active"):
                continue
            if not m.get("swap"):
                continue
            base = m.get("base") or raw.split("/", 1)[0]
            quote = m.get("quote") or "USDC"
            out.append(
                Instrument(
                    source=self.source,
                    symbol=_normalize_symbol(raw),
                    raw_symbol=raw,
                    base=base,
                    quote=quote,
                    kind="perp",
                    active=True,
                    meta={
                        "tick_size": (m.get("precision") or {}).get("price"),
                        "step_size": (m.get("precision") or {}).get("amount"),
                        "max_leverage": (m.get("info") or {}).get("maxLeverage"),
                    },
                ),
            )
        return out

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: datetime,
        limit: int = 1000,
    ) -> list[Bar]:
        raw_symbol = await self._resolve_raw(symbol)
        all_bars: list[Bar] = []
        cursor_ms = _to_ms(since)
        until_ms = _to_ms(until)
        while cursor_ms < until_ms:
            chunk = await self._ex.fetch_ohlcv(
                raw_symbol,
                timeframe=timeframe,
                since=cursor_ms,
                limit=limit,
            )
            if not chunk:
                break
            for candle in chunk:
                ts_ms, o, h, lo, cl, vol = (
                    candle[0],
                    candle[1],
                    candle[2],
                    candle[3],
                    candle[4],
                    candle[5],
                )
                if ts_ms >= until_ms:
                    break
                all_bars.append(
                    Bar(
                        source=self.source,
                        symbol=symbol,
                        timeframe=timeframe,
                        ts=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                        open=float(o),
                        high=float(h),
                        low=float(lo),
                        close=float(cl),
                        volume=float(vol),
                    ),
                )
            last_ts = chunk[-1][0]
            if last_ts <= cursor_ms:
                break
            cursor_ms = last_ts + 1
            if len(chunk) < limit:
                break
        return all_bars

    async def stream_ohlcv(
        self,
        symbol: str,
        timeframe: str,
    ) -> AsyncIterator[Bar]:
        raw_symbol = await self._resolve_raw(symbol)
        while True:
            bars = await self._ex.watch_ohlcv(raw_symbol, timeframe=timeframe)
            for candle in bars:
                ts_ms, o, h, lo, cl, vol = (
                    candle[0],
                    candle[1],
                    candle[2],
                    candle[3],
                    candle[4],
                    candle[5],
                )
                yield Bar(
                    source=self.source,
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                    open=float(o),
                    high=float(h),
                    low=float(lo),
                    close=float(cl),
                    volume=float(vol),
                )

    async def stream_trades(self, symbol: str) -> AsyncIterator[Trade]:
        raw_symbol = await self._resolve_raw(symbol)
        while True:
            trades = await self._ex.watch_trades(raw_symbol)
            for t in trades:
                yield Trade(
                    source=self.source,
                    symbol=symbol,
                    ts=datetime.fromtimestamp(t["timestamp"] / 1000, tz=UTC),
                    trade_id=str(t.get("id") or f"{t['timestamp']}-{t['price']}"),
                    price=float(t["price"]),
                    qty=float(t["amount"]),
                    side=t["side"],
                )

    async def _resolve_raw(self, normalized: str) -> str:
        if not self._ex.markets:
            await self._ex.load_markets()
        base = normalized.removesuffix("-PERP")
        raw = f"{base}/USDC:USDC"
        if raw not in self._ex.markets:
            raise ValueError(f"Unknown Hyperliquid perp symbol: {normalized}")
        return raw
