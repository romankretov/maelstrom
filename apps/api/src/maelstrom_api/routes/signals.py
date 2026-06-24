"""LLM-generated trade signals — read-side endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import Signal, User
from maelstrom_api.schemas.signal import SignalOut

router = APIRouter(
    prefix="/signals",
    tags=["signals"],
    dependencies=[Depends(current_active_user)],
)


@router.get("", response_model=list[SignalOut])
async def list_signals(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    since: Annotated[datetime | None, Query()] = None,
    symbol: Annotated[str | None, Query()] = None,
    direction: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Signal]:
    cutoff = since or datetime.now(UTC) - timedelta(days=3)
    stmt = (
        select(Signal)
        .where(Signal.ts >= cutoff)
        .where(or_(Signal.expires_at.is_(None), Signal.expires_at >= datetime.now(UTC)))
        .order_by(desc(Signal.ts))
        .limit(limit)
    )
    if symbol:
        stmt = stmt.where(Signal.symbol == symbol)
    if direction:
        stmt = stmt.where(Signal.direction == direction)
    return list((await session.execute(stmt)).scalars().all())
