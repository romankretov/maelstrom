import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, or_, select, text
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
    BulkBackfillRequest,
    BulkBackfillResponse,
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
    sort: Annotated[
        str,
        Query(description="alpha | volume | change_24h"),
    ] = "alpha",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[InstrumentOut]:
    """List instruments with optional ranking by 24h volume / change.

    Alphabetic sort is fine for stock-like markets but for crypto perps
    "biggest movers" or "most-traded" is what you actually want to see.
    The volume/change columns come from a single 1h-bar aggregate; if no
    data is stored, those rows just have NULL ranking columns and fall
    to the bottom.
    """
    if sort not in ("alpha", "volume", "change_24h"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown sort: {sort}")

    if sort == "alpha":
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
        rows = (await session.execute(stmt)).scalars().all()
        return [InstrumentOut.model_validate(r) for r in rows]

    # volume / change_24h paths share a CTE that aggregates last 25h of
    # 1h bars. Symbols with no recent bars come back with NULL and sort
    # to the bottom via NULLS LAST.
    params: dict[str, Any] = {"active": active}
    where: list[str] = ["i.active = :active"]
    if source:
        where.append("i.source = :source")
        params["source"] = source
    if kind:
        where.append("i.kind = :kind")
        params["kind"] = kind
    if q:
        where.append(
            "(UPPER(i.symbol) LIKE :like "
            " OR UPPER(i.base) LIKE :like "
            " OR UPPER(i.quote) LIKE :like)",
        )
        params["like"] = f"%{q.upper()}%"
    where_sql = " AND ".join(where)

    order_col = "vol_24h" if sort == "volume" else "change_24h"
    base_sql = (
        "WITH agg AS ("
        "  SELECT source, symbol, "
        "         SUM(volume) AS vol_24h, "
        "         (array_agg(close ORDER BY ts DESC))[1] AS close_now, "
        "         (array_agg(close ORDER BY ts ASC))[1]  AS close_old "
        "    FROM ohlcv "
        "   WHERE timeframe = '1h' AND ts >= now() - INTERVAL '25 hours' "
        "   GROUP BY source, symbol"
        ") "
        "SELECT i.source, i.symbol, i.raw_symbol, i.base, i.quote, i.kind, "
        "       i.active, i.meta, "
        "       a.vol_24h, "
        "       CASE WHEN a.close_old > 0 "
        "            THEN (a.close_now - a.close_old) / a.close_old "
        "            ELSE NULL END AS change_24h "
        "  FROM instruments i "
        "  LEFT JOIN agg a ON a.source = i.source AND a.symbol = i.symbol"
    )
    # where_sql + order_col are both built from string constants above (no
    # user input), so the composed query is safe despite f-string concat.
    sql = f"{base_sql} WHERE {where_sql} ORDER BY {order_col} DESC NULLS LAST LIMIT :limit"
    params["limit"] = limit
    mapping_rows = (await session.execute(text(sql), params)).mappings().all()
    return [
        InstrumentOut(
            source=r["source"],
            symbol=r["symbol"],
            raw_symbol=r["raw_symbol"],
            base=r["base"],
            quote=r["quote"],
            kind=r["kind"],
            active=r["active"],
            meta=r["meta"] or {},
            volume_24h=float(r["vol_24h"]) if r["vol_24h"] is not None else None,
            change_24h=float(r["change_24h"]) if r["change_24h"] is not None else None,
        )
        for r in mapping_rows
    ]


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


@router.post(
    "/backfill/bulk",
    response_model=BulkBackfillResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_bulk_backfill(
    body: BulkBackfillRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
    user: Annotated[User, Depends(current_active_user)],
) -> BulkBackfillResponse:
    """Create one BackfillJob per (symbol x timeframe) and enqueue them all.

    Cap is 100 jobs per call so a fat-fingered "all 600 binance perps x 6
    timeframes" can't flood the worker.
    """
    if body.range_start >= body.range_end:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "range_start must be before range_end",
        )
    if not body.symbols or not body.timeframes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "need at least one symbol + timeframe")
    for tf in body.timeframes:
        _validate_timeframe(tf)
    pairs = [(sym, tf) for sym in body.symbols for tf in body.timeframes]
    if len(pairs) > 100:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"too many jobs ({len(pairs)}); cap is 100 per call",
        )

    jobs: list[BackfillJob] = []
    for sym, tf in pairs:
        jobs.append(
            BackfillJob(
                source=body.source,
                symbol=sym,
                timeframe=tf,
                range_start=body.range_start,
                range_end=body.range_end,
                status=BackfillStatus.PENDING.value,
            ),
        )
    session.add_all(jobs)
    await session.commit()
    for job in jobs:
        await arq.enqueue_job("backfill_ohlcv", str(job.id))
    return BulkBackfillResponse(queued=len(jobs), job_ids=[j.id for j in jobs])
