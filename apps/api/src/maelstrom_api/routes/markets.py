import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.auth import current_active_user
from maelstrom_api.config import get_settings
from maelstrom_api.db import get_session
from maelstrom_api.models import (
    OHLCV,
    BackfillJob,
    BackfillStatus,
    Instrument,
    Timeframe,
    Trade,
    User,
)
from maelstrom_api.schemas.market import (
    BackfillJobOut,
    BackfillRequest,
    BarOut,
    InstrumentOut,
    SourceOut,
    TradeOut,
)

router = APIRouter(
    prefix="/markets",
    tags=["markets"],
    dependencies=[Depends(current_active_user)],
)

# --- redis pool for enqueuing worker jobs ------------------------------------

_arq_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis:
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(
            RedisSettings.from_dsn(str(get_settings().redis_url)),
        )
    return _arq_pool


# --- sources -----------------------------------------------------------------


@router.get("/sources", response_model=list[SourceOut])
async def list_sources() -> list[SourceOut]:
    return [
        SourceOut(name="binance", label="Binance (perps)", asset_kinds=["perp"]),
        SourceOut(name="hyperliquid", label="Hyperliquid (perps)", asset_kinds=["perp"]),
        SourceOut(name="yfinance", label="Yahoo Finance (equities)", asset_kinds=["equity"]),
    ]


# --- instruments -------------------------------------------------------------


@router.get("/instruments", response_model=list[InstrumentOut])
async def list_instruments(
    session: Annotated[AsyncSession, Depends(get_session)],
    source: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    q: Annotated[str | None, Query(description="search base, quote, or symbol")] = None,
    active: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Instrument]:
    stmt = select(Instrument).where(Instrument.active == active)
    if source:
        stmt = stmt.where(Instrument.source == source)
    if kind:
        stmt = stmt.where(Instrument.kind == kind)
    if q:
        like = f"%{q.upper()}%"
        stmt = stmt.where(
            or_(
                func.upper(Instrument.symbol).like(like),
                func.upper(Instrument.base).like(like),
                func.upper(Instrument.quote).like(like),
            ),
        )
    stmt = stmt.order_by(Instrument.base, Instrument.quote).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# --- OHLCV -------------------------------------------------------------------


def _validate_timeframe(tf: str) -> str:
    valid = {t.value for t in Timeframe}
    if tf not in valid:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid timeframe '{tf}'. Allowed: {sorted(valid)}",
        )
    return tf


@router.get("/ohlcv", response_model=list[BarOut])
async def get_ohlcv(
    session: Annotated[AsyncSession, Depends(get_session)],
    source: Annotated[str, Query()],
    symbol: Annotated[str, Query()],
    timeframe: Annotated[str, Query()],
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[OHLCV]:
    _validate_timeframe(timeframe)
    until = until or datetime.now(UTC)
    since = since or until - timedelta(days=7)
    stmt = (
        select(OHLCV)
        .where(
            and_(
                OHLCV.source == source,
                OHLCV.symbol == symbol,
                OHLCV.timeframe == timeframe,
                OHLCV.ts >= since,
                OHLCV.ts <= until,
            ),
        )
        .order_by(OHLCV.ts.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# --- trades ------------------------------------------------------------------


@router.get("/trades", response_model=list[TradeOut])
async def get_trades(
    session: Annotated[AsyncSession, Depends(get_session)],
    source: Annotated[str, Query()],
    symbol: Annotated[str, Query()],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Trade]:
    stmt = (
        select(Trade)
        .where(and_(Trade.source == source, Trade.symbol == symbol))
        .order_by(desc(Trade.ts))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# --- backfill ----------------------------------------------------------------


@router.post(
    "/backfill",
    response_model=BackfillJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_backfill(
    body: BackfillRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
    user: Annotated[User, Depends(current_active_user)],
) -> BackfillJob:
    _validate_timeframe(body.timeframe)
    if body.range_start >= body.range_end:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "range_start must be before range_end",
        )

    job = BackfillJob(
        source=body.source,
        symbol=body.symbol,
        timeframe=body.timeframe,
        range_start=body.range_start,
        range_end=body.range_end,
        status=BackfillStatus.PENDING.value,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    await arq.enqueue_job("backfill_ohlcv", str(job.id))
    return job


@router.get("/backfill/{job_id}", response_model=BackfillJobOut)
async def get_backfill(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BackfillJob:
    job = await session.get(BackfillJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backfill job not found")
    return job
