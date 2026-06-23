from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .connectors import Bar, Instrument, get_source, list_sources
from .settings import get_settings

log = structlog.get_logger()


# ----------------------------------------------------------------- engine
# One engine per worker process. arq invokes tasks repeatedly — recreating
# the engine on every call kills throughput.

_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _sm() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _session_maker is None:
        _engine = create_async_engine(
            str(get_settings().database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_maker


# ----------------------------------------------------------------- heartbeat


async def heartbeat(ctx: dict[str, Any]) -> str:
    """Per-minute pulse, audit_log row + structured log."""
    async with _sm()() as session:
        await session.execute(
            text(
                "INSERT INTO audit_log (actor_kind, action, payload) "
                "VALUES ('worker', 'worker.heartbeat', :p::json)",
            ),
            {"p": '{"ts": "' + datetime.now(UTC).isoformat() + '"}'},
        )
        await session.commit()
    log.info("worker.heartbeat")
    return "ok"


# ----------------------------------------------------------------- instruments


_UPSERT_INSTRUMENT_SQL = text(
    """
    INSERT INTO instruments (
        source, symbol, raw_symbol, base, quote, kind, active, meta, updated_at
    )
    VALUES (
        :source, :symbol, :raw_symbol, :base, :quote, :kind, :active, CAST(:meta AS jsonb), now()
    )
    ON CONFLICT (source, symbol) DO UPDATE SET
        raw_symbol = EXCLUDED.raw_symbol,
        base       = EXCLUDED.base,
        quote      = EXCLUDED.quote,
        kind       = EXCLUDED.kind,
        active     = EXCLUDED.active,
        meta       = EXCLUDED.meta,
        updated_at = now()
    """,
)


async def _upsert_instruments(session: AsyncSession, instruments: list[Instrument]) -> int:
    if not instruments:
        return 0
    import orjson

    payload = [
        {
            "source": i.source,
            "symbol": i.symbol,
            "raw_symbol": i.raw_symbol,
            "base": i.base,
            "quote": i.quote,
            "kind": i.kind,
            "active": i.active,
            "meta": orjson.dumps(i.meta).decode("utf-8"),
        }
        for i in instruments
    ]
    await session.execute(_UPSERT_INSTRUMENT_SQL, payload)
    await session.commit()
    return len(payload)


async def sync_instruments(ctx: dict[str, Any], source: str | None = None) -> dict[str, int]:
    """Refresh instruments catalog. Per-source if `source` is given, else all sources."""
    targets = [source] if source else list_sources()
    counts: dict[str, int] = {}
    for name in targets:
        try:
            src = get_source(name)
        except ValueError as e:
            log.warning("sync_instruments.unknown_source", source=name, error=str(e))
            continue
        try:
            instruments = await src.list_instruments()
            async with _sm()() as session:
                written = await _upsert_instruments(session, instruments)
            counts[name] = written
            log.info("sync_instruments.done", source=name, count=written)
        except Exception as e:
            log.exception("sync_instruments.failed", source=name, error=str(e))
            counts[name] = -1
        finally:
            await src.close()
    return counts


# ----------------------------------------------------------------- OHLCV backfill


_UPSERT_OHLCV_SQL = text(
    """
    INSERT INTO ohlcv (source, symbol, timeframe, ts, open, high, low, close, volume, trades_count)
    VALUES (:source, :symbol, :timeframe, :ts, :open, :high, :low, :close, :volume, :trades_count)
    ON CONFLICT (source, symbol, timeframe, ts) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low  = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        trades_count = EXCLUDED.trades_count
    """,
)


async def _upsert_bars(session: AsyncSession, bars: list[Bar]) -> int:
    if not bars:
        return 0
    payload = [
        {
            "source": b.source,
            "symbol": b.symbol,
            "timeframe": b.timeframe,
            "ts": b.ts,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "trades_count": b.trades_count,
        }
        for b in bars
    ]
    await session.execute(_UPSERT_OHLCV_SQL, payload)
    await session.commit()
    return len(payload)


async def backfill_ohlcv(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Run a backfill_jobs row to completion."""
    log.info("backfill.start", job_id=job_id)
    async with _sm()() as session:
        row = (
            await session.execute(
                text(
                    "SELECT source, symbol, timeframe, range_start, range_end "
                    "FROM backfill_jobs WHERE id = :id",
                ),
                {"id": job_id},
            )
        ).first()
        if row is None:
            log.error("backfill.not_found", job_id=job_id)
            return {"status": "not_found"}
        await session.execute(
            text("UPDATE backfill_jobs SET status='running', updated_at=now() WHERE id=:id"),
            {"id": job_id},
        )
        await session.commit()

    source_name, symbol, timeframe, since, until = row
    total = 0
    src = get_source(source_name)
    try:
        bars = await src.fetch_ohlcv(symbol, timeframe, since, until)
        async with _sm()() as session:
            total = await _upsert_bars(session, bars)
            await session.execute(
                text(
                    "UPDATE backfill_jobs SET status='done', bars_written=:n, updated_at=now() "
                    "WHERE id=:id",
                ),
                {"id": job_id, "n": total},
            )
            await session.commit()
        log.info("backfill.done", job_id=job_id, bars=total)
        return {"status": "done", "bars": total}
    except Exception as e:
        log.exception("backfill.failed", job_id=job_id, error=str(e))
        async with _sm()() as session:
            await session.execute(
                text(
                    "UPDATE backfill_jobs SET status='failed', error=:err, updated_at=now() "
                    "WHERE id=:id",
                ),
                {"id": job_id, "err": str(e)[:2000]},
            )
            await session.commit()
        return {"status": "failed", "error": str(e)}
    finally:
        await src.close()
