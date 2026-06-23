"""Strategy CRUD + versioned code storage.

Strategies are owned by users (single owner for now) and visible to:
- the owner
- any admin/superuser
A new strategy is created with v1 of the code. Every save creates a new
strategy_versions row; old versions are immutable (audit + reproducibility).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import audit
from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import Strategy, StrategyVersion, User
from maelstrom_api.schemas.strategy import (
    StrategyCreate,
    StrategyOut,
    StrategyUpdate,
    StrategyVersionCreate,
    StrategyVersionOut,
)

router = APIRouter(
    prefix="/strategies",
    tags=["strategies"],
    dependencies=[Depends(current_active_user)],
)


def _can_access(strategy: Strategy, user: User) -> bool:
    if user.is_superuser:
        return True
    return strategy.owner_id == user.id


def _can_edit(strategy: Strategy, user: User) -> bool:
    return _can_access(strategy, user)


async def _latest_version(session: AsyncSession, strategy_id: uuid.UUID) -> StrategyVersion | None:
    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(desc(StrategyVersion.version))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _to_out(strategy: Strategy, latest: StrategyVersion | None) -> StrategyOut:
    return StrategyOut(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        owner_id=strategy.owner_id,
        is_archived=strategy.is_archived,
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
        latest_version=(StrategyVersionOut.model_validate(latest) if latest else None),
    )


# ---------------------------------------------------------------- list / read


@router.get("", response_model=list[StrategyOut])
async def list_strategies(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    archived: Annotated[bool, Query()] = False,
    q: Annotated[str | None, Query(description="search name/description")] = None,
) -> list[StrategyOut]:
    stmt = select(Strategy).where(Strategy.is_archived == archived)
    if not user.is_superuser:
        stmt = stmt.where(Strategy.owner_id == user.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Strategy.name).like(like))
    stmt = stmt.order_by(Strategy.updated_at.desc()).limit(200)
    strategies = list((await session.execute(stmt)).scalars().all())

    out: list[StrategyOut] = []
    for s in strategies:
        latest = await _latest_version(session, s.id)
        out.append(_to_out(s, latest))
    return out


@router.get("/{strategy_id}", response_model=StrategyOut)
async def get_strategy(
    strategy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> StrategyOut:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    latest = await _latest_version(session, s.id)
    return _to_out(s, latest)


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionOut])
async def list_versions(
    strategy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[StrategyVersion]:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(desc(StrategyVersion.version))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------- create / update


@router.post("", response_model=StrategyOut, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    body: StrategyCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> StrategyOut:
    # Reject duplicate names.
    existing = (
        await session.execute(select(Strategy).where(Strategy.name == body.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"strategy '{body.name}' already exists")

    s = Strategy(
        name=body.name,
        description=body.description,
        owner_id=user.id,
    )
    session.add(s)
    await session.flush()  # populate s.id

    v = StrategyVersion(
        strategy_id=s.id,
        version=1,
        code=body.code,
        params=body.params,
        author_id=user.id,
        message=body.message or "initial",
    )
    session.add(v)

    await audit.record(
        session,
        action="strategy.create",
        actor_id=user.id,
        target_kind="strategy",
        target_id=str(s.id),
        payload={"name": body.name},
    )
    await session.commit()
    await session.refresh(s)
    return _to_out(s, v)


@router.patch("/{strategy_id}", response_model=StrategyOut)
async def update_strategy(
    strategy_id: uuid.UUID,
    body: StrategyUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> StrategyOut:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_edit(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")

    if body.description is not None:
        s.description = body.description
    if body.is_archived is not None:
        s.is_archived = body.is_archived
    await audit.record(
        session,
        action="strategy.update",
        actor_id=user.id,
        target_kind="strategy",
        target_id=str(s.id),
        payload=body.model_dump(exclude_none=True),
    )
    await session.commit()
    await session.refresh(s)
    latest = await _latest_version(session, s.id)
    return _to_out(s, latest)


@router.post(
    "/{strategy_id}/versions",
    response_model=StrategyVersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    strategy_id: uuid.UUID,
    body: StrategyVersionCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> StrategyVersion:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_edit(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")

    next_version = (
        await session.execute(
            select(func.coalesce(func.max(StrategyVersion.version), 0)).where(
                StrategyVersion.strategy_id == strategy_id
            ),
        )
    ).scalar_one() + 1

    v = StrategyVersion(
        strategy_id=s.id,
        version=next_version,
        code=body.code,
        params=body.params,
        author_id=user.id,
        message=body.message,
    )
    session.add(v)
    # Bump strategy.updated_at so it sorts to the top of the list.
    s.updated_at = func.now()  # type: ignore[assignment]
    await audit.record(
        session,
        action="strategy.version.create",
        actor_id=user.id,
        target_kind="strategy",
        target_id=str(s.id),
        payload={"version": next_version, "message": body.message},
    )
    await session.commit()
    await session.refresh(v)
    return v


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_strategy(
    strategy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> None:
    """Soft-delete: sets is_archived. Versions are kept for audit."""
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_edit(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    s.is_archived = True
    await audit.record(
        session,
        action="strategy.archive",
        actor_id=user.id,
        target_kind="strategy",
        target_id=str(s.id),
    )
    await session.commit()


# Silence the import-unused warning on `and_`; we'll use it in a follow-up commit.
_ = and_
