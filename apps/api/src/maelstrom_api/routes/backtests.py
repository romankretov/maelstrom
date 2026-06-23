"""Backtest run creation + read-side endpoints."""

import uuid
from typing import Annotated

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import audit
from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import (
    BacktestEquity,
    BacktestRun,
    BacktestStatus,
    BacktestTrade,
    Strategy,
    StrategyVersion,
    User,
)
from maelstrom_api.routes.markets import get_arq_pool
from maelstrom_api.schemas.backtest import (
    BacktestCreate,
    BacktestRunOut,
    EquityPointOut,
    TradeOut,
)

router = APIRouter(
    prefix="/backtests",
    tags=["backtests"],
    dependencies=[Depends(current_active_user)],
)


def _can_access_strategy(strategy: Strategy, user: User) -> bool:
    return user.is_superuser or strategy.owner_id == user.id


async def _latest_version(session: AsyncSession, strategy_id: uuid.UUID) -> StrategyVersion | None:
    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(desc(StrategyVersion.version))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------- create


@router.post(
    "/strategies/{strategy_id}",
    response_model=BacktestRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_backtest(
    strategy_id: uuid.UUID,
    body: BacktestCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> BacktestRun:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    if body.range_start >= body.range_end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "range_start must be before range_end")

    # Resolve strategy_version_id (default: latest)
    if body.strategy_version_id is not None:
        version = await session.get(StrategyVersion, body.strategy_version_id)
        if version is None or version.strategy_id != strategy_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid strategy_version_id")
    else:
        version = await _latest_version(session, strategy_id)
        if version is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "strategy has no versions")

    run = BacktestRun(
        strategy_id=strategy_id,
        strategy_version_id=version.id,
        source=body.source,
        symbols=body.symbols,
        timeframe=body.timeframe,
        range_start=body.range_start,
        range_end=body.range_end,
        initial_capital=body.initial_capital,
        params=body.params,
        status=BacktestStatus.PENDING.value,
        requester_id=user.id,
    )
    session.add(run)
    await audit.record(
        session,
        action="backtest.create",
        actor_id=user.id,
        target_kind="strategy",
        target_id=str(strategy_id),
        payload={
            "source": body.source,
            "symbols": body.symbols,
            "timeframe": body.timeframe,
            "range_start": body.range_start.isoformat(),
            "range_end": body.range_end.isoformat(),
            "version": version.version,
        },
    )
    await session.commit()
    await session.refresh(run)

    await arq.enqueue_job("run_backtest", str(run.id))
    return run


# ---------------------------------------------------------------- read


async def _load_and_authorize(
    session: AsyncSession,
    run_id: uuid.UUID,
    user: User,
) -> BacktestRun:
    run = await session.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backtest not found")
    s = await session.get(Strategy, run.strategy_id)
    if s is None or not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your backtest")
    return run


@router.get("/{run_id}", response_model=BacktestRunOut)
async def get_backtest(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> BacktestRun:
    return await _load_and_authorize(session, run_id, user)


@router.get("/{run_id}/equity", response_model=list[EquityPointOut])
async def get_equity(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=10000)] = 3000,
) -> list[BacktestEquity]:
    await _load_and_authorize(session, run_id, user)
    stmt = (
        select(BacktestEquity)
        .where(BacktestEquity.run_id == run_id)
        .order_by(BacktestEquity.ts.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{run_id}/trades", response_model=list[TradeOut])
async def get_trades(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[BacktestTrade]:
    await _load_and_authorize(session, run_id, user)
    stmt = (
        select(BacktestTrade)
        .where(BacktestTrade.run_id == run_id)
        .order_by(BacktestTrade.ts.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/strategies/{strategy_id}", response_model=list[BacktestRunOut])
async def list_runs_for_strategy(
    strategy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[BacktestRun]:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    stmt = (
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy_id)
        .order_by(BacktestRun.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
