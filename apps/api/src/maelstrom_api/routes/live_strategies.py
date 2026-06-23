"""Start/stop/list live strategies."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import audit
from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import (
    Account,
    LiveStatus,
    LiveStrategy,
    Strategy,
    StrategyVersion,
    User,
)
from maelstrom_api.schemas.live_strategy import LiveStrategyCreate, LiveStrategyOut

router = APIRouter(
    prefix="/live-strategies",
    tags=["live-strategies"],
    dependencies=[Depends(current_active_user)],
)


def _can_access_strategy(s: Strategy, user: User) -> bool:
    return user.is_superuser or s.owner_id == user.id


def _can_access_account(a: Account, user: User) -> bool:
    return user.is_superuser or a.owner_id == user.id


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
    response_model=LiveStrategyOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_and_start(
    strategy_id: uuid.UUID,
    body: LiveStrategyCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> LiveStrategy:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")

    account = await session.get(Account, body.account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access_account(account, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    if account.kind != "paper" and not user.is_superuser:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "live trading on non-paper accounts requires admin (P3.2)",
        )

    if body.strategy_version_id is not None:
        version = await session.get(StrategyVersion, body.strategy_version_id)
        if version is None or version.strategy_id != strategy_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid strategy_version_id")
    else:
        version = await _latest_version(session, strategy_id)
        if version is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "strategy has no versions")

    live = LiveStrategy(
        strategy_id=strategy_id,
        strategy_version_id=version.id,
        account_id=body.account_id,
        source=body.source,
        symbols=body.symbols,
        timeframe=body.timeframe,
        params=body.params,
        status=LiveStatus.PENDING_START.value,
        requester_id=user.id,
    )
    session.add(live)
    await audit.record(
        session,
        action="live_strategy.start",
        actor_id=user.id,
        target_kind="strategy",
        target_id=str(strategy_id),
        payload={
            "account_id": str(body.account_id),
            "source": body.source,
            "symbols": body.symbols,
            "timeframe": body.timeframe,
            "version": version.version,
        },
    )
    await session.commit()
    await session.refresh(live)
    return live


# ---------------------------------------------------------------- stop


@router.post("/{live_id}/stop", response_model=LiveStrategyOut)
async def stop(
    live_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> LiveStrategy:
    live = await session.get(LiveStrategy, live_id)
    if live is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "live strategy not found")
    s = await session.get(Strategy, live.strategy_id)
    if s is None or not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")

    if live.status in (LiveStatus.STOPPED.value, LiveStatus.FAILED.value):
        return live
    live.status = LiveStatus.PENDING_STOP.value
    await audit.record(
        session,
        action="live_strategy.stop",
        actor_id=user.id,
        target_kind="live_strategy",
        target_id=str(live_id),
    )
    await session.commit()
    await session.refresh(live)
    return live


# ---------------------------------------------------------------- list / read


@router.get("/strategies/{strategy_id}", response_model=list[LiveStrategyOut])
async def list_for_strategy(
    strategy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> list[LiveStrategy]:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    stmt = (
        select(LiveStrategy)
        .where(LiveStrategy.strategy_id == strategy_id)
        .order_by(LiveStrategy.created_at.desc())
        .limit(50)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{live_id}", response_model=LiveStrategyOut)
async def get(
    live_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> LiveStrategy:
    live = await session.get(LiveStrategy, live_id)
    if live is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "live strategy not found")
    s = await session.get(Strategy, live.strategy_id)
    if s is None or not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    return live
