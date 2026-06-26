"""Per-user watchlist of (source, symbol) pairs.

Pinned symbols float to the top of the instruments dropdown and can
be used as quick filters elsewhere. Bare-bones CRUD: list / add /
remove. No ordering; the UI sorts pinned-first.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import User

router = APIRouter(
    prefix="/watchlist",
    tags=["watchlist"],
    dependencies=[Depends(current_active_user)],
)


class WatchlistEntry(BaseModel):
    source: str
    symbol: str


@router.get("", response_model=list[WatchlistEntry])
async def list_watchlist(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> list[WatchlistEntry]:
    rows = (
        await session.execute(
            text(
                "SELECT source, symbol FROM watchlist "
                " WHERE user_id = :uid "
                " ORDER BY created_at DESC",
            ),
            {"uid": user.id},
        )
    ).all()
    return [WatchlistEntry(source=r[0], symbol=r[1]) for r in rows]


@router.post("", response_model=WatchlistEntry, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    body: WatchlistEntry,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> WatchlistEntry:
    await session.execute(
        text(
            "INSERT INTO watchlist (user_id, source, symbol) "
            "VALUES (:uid, :s, :sym) "
            "ON CONFLICT (user_id, source, symbol) DO NOTHING",
        ),
        {"uid": user.id, "s": body.source, "sym": body.symbol},
    )
    await session.commit()
    return body


@router.delete("/{source}/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    source: str,
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> None:
    await session.execute(
        text(
            "DELETE FROM watchlist  WHERE user_id = :uid AND source = :s AND symbol = :sym",
        ),
        {"uid": user.id, "s": source, "sym": symbol},
    )
    await session.commit()
