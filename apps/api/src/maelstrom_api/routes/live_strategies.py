"""Start/stop/list live strategies."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select, text
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
from maelstrom_api.schemas.live_strategy import (
    LiveStrategyCreate,
    LiveStrategyOut,
    ShadowFillOut,
)

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

    if account.killed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "account is killed; cannot start new live strategies",
        )

    live = LiveStrategy(
        strategy_id=strategy_id,
        strategy_version_id=version.id,
        account_id=body.account_id,
        source=body.source,
        symbols=body.symbols,
        timeframe=body.timeframe,
        params=body.params,
        max_notional_per_symbol=body.max_notional_per_symbol,
        max_position_qty=body.max_position_qty,
        shadow_mode=body.shadow_mode,
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


class LiveStrategyRow(LiveStrategyOut):
    """Same as LiveStrategyOut + display-friendly joins."""

    strategy_name: str | None = None
    account_name: str | None = None
    account_kind: str | None = None
    realized_pnl: float = 0.0  # sum from fills attributed to this live run


@router.get("", response_model=list[LiveStrategyRow])
async def list_all(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[LiveStrategyRow]:
    """All live strategies the caller can see.

    Admins see everything. Regular users see only runs whose underlying
    strategy belongs to them. Defaults to running + pending_* unless
    `?status=<value>` is passed.
    """
    where_clauses: list[str] = []
    params: dict[str, Any] = {}
    if status_filter is None:
        where_clauses.append("ls.status IN ('running', 'pending_start', 'pending_stop')")
    else:
        where_clauses.append("ls.status = :status")
        params["status"] = status_filter
    if not user.is_superuser:
        where_clauses.append("s.owner_id = :uid")
        params["uid"] = user.id
    where_sql = " AND ".join(where_clauses)
    base_sql = (
        "SELECT "
        "  ls.id, ls.strategy_id, ls.strategy_version_id, ls.account_id, ls.source, "
        "  ls.symbols, ls.timeframe, ls.params, ls.status, ls.error, "
        "  ls.max_notional_per_symbol, ls.max_position_qty, ls.shadow_mode, "
        "  ls.started_at, ls.stopped_at, ls.requester_id, "
        "  ls.created_at, ls.updated_at, "
        "  s.name AS strategy_name, a.name AS account_name, a.kind AS account_kind, "
        "  COALESCE(("
        "    SELECT SUM(f.pnl) FROM fills f JOIN orders o ON o.id = f.order_id "
        "     WHERE o.live_strategy_id = ls.id"
        "  ), 0) AS realized_pnl "
        "  FROM live_strategies ls "
        "  JOIN strategies s ON s.id = ls.strategy_id "
        "  JOIN accounts a ON a.id = ls.account_id"
    )
    # where_sql is composed from string constants above (no user input) —
    # the dynamic part of the query is only the static branch selection.
    sql = base_sql + f" WHERE {where_sql} ORDER BY ls.created_at DESC LIMIT 200"
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [
        LiveStrategyRow(
            id=r["id"],
            strategy_id=r["strategy_id"],
            strategy_version_id=r["strategy_version_id"],
            account_id=r["account_id"],
            source=r["source"],
            symbols=list(r["symbols"]),
            timeframe=r["timeframe"],
            params=r["params"] or {},
            status=r["status"],
            error=r["error"],
            max_notional_per_symbol=r["max_notional_per_symbol"],
            max_position_qty=r["max_position_qty"],
            shadow_mode=bool(r["shadow_mode"]),
            started_at=r["started_at"],
            stopped_at=r["stopped_at"],
            requester_id=r["requester_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            strategy_name=r["strategy_name"],
            account_name=r["account_name"],
            account_kind=r["account_kind"],
            realized_pnl=float(r["realized_pnl"] or 0),
        )
        for r in rows
    ]


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


@router.get("/{live_id}/shadow-fills", response_model=list[ShadowFillOut])
async def shadow_fills(
    live_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ShadowFillOut]:
    live = await session.get(LiveStrategy, live_id)
    if live is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "live strategy not found")
    s = await session.get(Strategy, live.strategy_id)
    if s is None or not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    rows = (
        await session.execute(
            text(
                "SELECT id, live_strategy_id, ts, symbol, side, qty, price, "
                "       notional, fee, pnl, reason "
                "  FROM shadow_fills "
                " WHERE live_strategy_id = :id "
                " ORDER BY ts DESC LIMIT :n",
            ),
            {"id": live_id, "n": limit},
        )
    ).all()
    return [
        ShadowFillOut(
            id=r[0],
            live_strategy_id=r[1],
            ts=r[2],
            symbol=r[3],
            side=r[4],
            qty=float(r[5]),
            price=float(r[6]),
            notional=float(r[7]),
            fee=float(r[8]),
            pnl=float(r[9]),
            reason=r[10],
        )
        for r in rows
    ]
