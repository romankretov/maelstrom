"""Live OHLCV streaming.

A `StreamManager` owns one asyncio.Task per (source, symbol, timeframe). Each
task subscribes to the exchange via ccxt.pro.watch_ohlcv, upserts every bar
update into Postgres, and publishes the bar JSON to a Redis channel
"bars:{source}:{symbol}:{timeframe}" for the API to fan out to browsers.

On boot we start a small hard-coded set of streams (top liquid perps, 1m).
On-demand subscription lands in a later phase once the UI requests it.
"""

import asyncio
import os
from dataclasses import asdict
from typing import Any

import orjson
import redis.asyncio as aioredis
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .connectors import Bar, get_source
from .settings import get_settings

log = structlog.get_logger()


DEFAULT_STREAMS: list[tuple[str, str, str]] = [
    ("binance", "BTC-PERP", "1m"),
    ("binance", "ETH-PERP", "1m"),
    ("binance", "SOL-PERP", "1m"),
    ("hyperliquid", "BTC-PERP", "1m"),
    ("hyperliquid", "ETH-PERP", "1m"),
    ("hyperliquid", "SOL-PERP", "1m"),
]


def _load_streams_config() -> list[tuple[str, str, str]]:
    """Allow override via MAELSTROM_STREAMS env var.

    Format: comma-separated `source:SYMBOL:tf` entries.
    Example: "binance:BTC-PERP:1m,hyperliquid:ETH-PERP:1m"
    """
    raw = os.environ.get("MAELSTROM_STREAMS", "").strip()
    if not raw:
        return DEFAULT_STREAMS
    out: list[tuple[str, str, str]] = []
    for entry in raw.split(","):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            out.append((parts[0], parts[1], parts[2]))
    return out or DEFAULT_STREAMS


_UPSERT_OHLCV_SQL = text(
    """
    INSERT INTO ohlcv (source, symbol, timeframe, ts, open, high, low, close, volume)
    VALUES (:source, :symbol, :timeframe, :ts, :open, :high, :low, :close, :volume)
    ON CONFLICT (source, symbol, timeframe, ts) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low  = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume
    """,
)


def _channel(source: str, symbol: str, timeframe: str) -> str:
    return f"bars:{source}:{symbol}:{timeframe}"


def _bar_payload(bar: Bar) -> bytes:
    d = asdict(bar)
    d["ts"] = bar.ts.isoformat()
    return orjson.dumps(d)


class StreamManager:
    def __init__(self) -> None:
        self._tasks: dict[tuple[str, str, str], asyncio.Task[None]] = {}
        self._engine: Any = None
        self._sm: async_sessionmaker[AsyncSession] | None = None
        self._redis: aioredis.Redis | None = None

    async def _ensure_db(self) -> async_sessionmaker[AsyncSession]:
        if self._sm is None:
            self._engine = create_async_engine(
                str(get_settings().database_url),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
            self._sm = async_sessionmaker(self._engine, expire_on_commit=False)
        return self._sm

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(str(get_settings().redis_url))
        return self._redis

    async def start_default(self) -> None:
        for source, symbol, timeframe in _load_streams_config():
            self.start(source, symbol, timeframe)

    def start(self, source: str, symbol: str, timeframe: str) -> None:
        key = (source, symbol, timeframe)
        if key in self._tasks and not self._tasks[key].done():
            return
        self._tasks[key] = asyncio.create_task(
            self._run_stream(source, symbol, timeframe),
            name=f"stream:{source}:{symbol}:{timeframe}",
        )
        log.info("stream.start", source=source, symbol=symbol, timeframe=timeframe)

    async def stop_all(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        if self._redis is not None:
            await self._redis.aclose()
        if self._engine is not None:
            await self._engine.dispose()

    async def _run_stream(self, source: str, symbol: str, timeframe: str) -> None:
        backoff = 1.0
        while True:
            try:
                await self._stream_once(source, symbol, timeframe)
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception(
                    "stream.error",
                    source=source,
                    symbol=symbol,
                    timeframe=timeframe,
                    error=str(e),
                    backoff=backoff,
                )
                await asyncio.sleep(min(backoff, 30.0))
                backoff = min(backoff * 2, 30.0)

    async def _stream_once(self, source_name: str, symbol: str, timeframe: str) -> None:
        src = get_source(source_name)
        sm = await self._ensure_db()
        r = await self._ensure_redis()
        channel = _channel(source_name, symbol, timeframe)
        try:
            async for bar in src.stream_ohlcv(symbol, timeframe):
                async with sm() as session:
                    await session.execute(
                        _UPSERT_OHLCV_SQL,
                        {
                            "source": bar.source,
                            "symbol": bar.symbol,
                            "timeframe": bar.timeframe,
                            "ts": bar.ts,
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "volume": bar.volume,
                        },
                    )
                    await session.commit()
                await r.publish(channel, _bar_payload(bar))
        finally:
            await src.close()


# Singleton accessible from the worker startup hook.
manager = StreamManager()
