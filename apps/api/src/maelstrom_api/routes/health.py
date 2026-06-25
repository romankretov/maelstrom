from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.db import get_session
from maelstrom_api.models import User

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe — process is up. Never depends on downstreams."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    """Readiness probe — DB reachable. Used by Caddy/compose for traffic routing."""
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/auth/bootstrap-needed")
async def bootstrap_needed(
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """True when the DB has zero users — the login page uses this to switch
    into "create admin account" mode on first boot. Unauthenticated by
    design; flips to false the instant the first user registers."""
    count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    return {"needs_admin": count == 0}
