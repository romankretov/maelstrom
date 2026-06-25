"""LLM-generated trade signals — read-side endpoints + scanner control."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import Signal, User
from maelstrom_api.routes.markets import get_arq_pool
from maelstrom_api.schemas.signal import SignalOut

router = APIRouter(
    prefix="/signals",
    tags=["signals"],
    dependencies=[Depends(current_active_user)],
)


# ---------------------------------------------------------------- scanner config


class ScannerConfigOut(BaseModel):
    interval_minutes: int
    enabled: bool
    last_run_at: datetime | None
    last_status: str | None
    last_signal_count: int | None
    last_reason: str | None
    last_call_id: str | None


class ScannerConfigPatch(BaseModel):
    interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    enabled: bool | None = None


async def _read_scanner_config(session: AsyncSession) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                "SELECT interval_minutes, enabled, last_run_at, last_status, "
                "       last_signal_count, last_reason, last_call_id "
                "  FROM scanner_config WHERE id = 1",
            ),
        )
    ).first()
    if row is None:
        # Defensive: migration creates the row, but on a fresh DB we backfill.
        await session.execute(text("INSERT INTO scanner_config (id) VALUES (1)"))
        await session.commit()
        return {
            "interval_minutes": 30,
            "enabled": True,
            "last_run_at": None,
            "last_status": None,
            "last_signal_count": None,
            "last_reason": None,
            "last_call_id": None,
        }
    return {
        "interval_minutes": int(row[0]),
        "enabled": bool(row[1]),
        "last_run_at": row[2],
        "last_status": row[3],
        "last_signal_count": row[4],
        "last_reason": row[5],
        "last_call_id": str(row[6]) if row[6] else None,
    }


@router.get("/scanner-config", response_model=ScannerConfigOut)
async def get_scanner_config(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, Any]:
    return await _read_scanner_config(session)


@router.patch("/scanner-config", response_model=ScannerConfigOut)
async def patch_scanner_config(
    body: ScannerConfigPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, Any]:
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    sets: list[str] = []
    params: dict[str, Any] = {}
    if body.interval_minutes is not None:
        sets.append("interval_minutes = :im")
        params["im"] = body.interval_minutes
    if body.enabled is not None:
        sets.append("enabled = :en")
        params["en"] = body.enabled
    if not sets:
        return await _read_scanner_config(session)
    sets.append("updated_at = now()")
    await session.execute(
        text(f"UPDATE scanner_config SET {', '.join(sets)} WHERE id = 1"),  # noqa: S608
        params,
    )
    await session.commit()
    return await _read_scanner_config(session)


@router.post("/scanner-config/run-now")
async def scanner_run_now(
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, str]:
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    job = await arq.enqueue_job("scan_opportunities", force=True)
    return {"job_id": (job.job_id if job else "")}


# ---------------------------------------------------------------- signals list


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
