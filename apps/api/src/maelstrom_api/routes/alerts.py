"""User-defined price / funding / change alerts.

CRUD only — the worker evaluator (apps/worker/.../alerts.py) reads the
table on a cron tick and fires notifications via notify_all.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import User

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(current_active_user)],
)


AlertCondition = Literal[
    "price_above",
    "price_below",
    "change_24h_above",
    "change_24h_below",
    "funding_above",
    "funding_below",
]


class AlertCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)
    condition: AlertCondition
    threshold: Decimal
    cooldown_minutes: int = Field(default=60, ge=1, le=10_080)


class AlertUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    threshold: Decimal | None = None
    cooldown_minutes: int | None = Field(default=None, ge=1, le=10_080)
    enabled: bool | None = None


class AlertOut(BaseModel):
    id: uuid.UUID
    label: str
    source: str
    symbol: str
    condition: AlertCondition
    threshold: float
    cooldown_minutes: int
    enabled: bool
    last_triggered_at: datetime | None
    last_value: float | None
    trigger_count: int
    created_at: datetime


def _row_to_alert(row: Any) -> AlertOut:
    return AlertOut(
        id=row[0],
        label=row[1],
        source=row[2],
        symbol=row[3],
        condition=row[4],
        threshold=float(row[5]),
        cooldown_minutes=int(row[6]),
        enabled=bool(row[7]),
        last_triggered_at=row[8],
        last_value=float(row[9]) if row[9] is not None else None,
        trigger_count=int(row[10]),
        created_at=row[11],
    )


_SELECT_COLUMNS = (
    "id, label, source, symbol, condition, threshold, cooldown_minutes, enabled, "
    "last_triggered_at, last_value, trigger_count, created_at"
)


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> list[AlertOut]:
    rows = (
        await session.execute(
            text(
                f"SELECT {_SELECT_COLUMNS} FROM alerts "  # noqa: S608
                "WHERE user_id = :uid ORDER BY created_at DESC",
            ),
            {"uid": user.id},
        )
    ).all()
    return [_row_to_alert(r) for r in rows]


@router.post("", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> AlertOut:
    row = (
        await session.execute(
            text(
                "INSERT INTO alerts "  # noqa: S608
                "  (user_id, label, source, symbol, condition, threshold, cooldown_minutes) "
                "VALUES (:uid, :label, :source, :symbol, :cond, :thr, :cd) "
                f"RETURNING {_SELECT_COLUMNS}",
            ),
            {
                "uid": user.id,
                "label": body.label,
                "source": body.source,
                "symbol": body.symbol,
                "cond": body.condition,
                "thr": body.threshold,
                "cd": body.cooldown_minutes,
            },
        )
    ).first()
    await session.commit()
    assert row is not None
    return _row_to_alert(row)


@router.patch("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: uuid.UUID,
    body: AlertUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> AlertOut:
    sets: list[str] = []
    params: dict[str, Any] = {"id": alert_id, "uid": user.id}
    if body.label is not None:
        sets.append("label = :label")
        params["label"] = body.label
    if body.threshold is not None:
        sets.append("threshold = :thr")
        params["thr"] = body.threshold
    if body.cooldown_minutes is not None:
        sets.append("cooldown_minutes = :cd")
        params["cd"] = body.cooldown_minutes
    if body.enabled is not None:
        sets.append("enabled = :en")
        params["en"] = body.enabled
    if not sets:
        # No-op — just return current state.
        row = (
            await session.execute(
                text(
                    f"SELECT {_SELECT_COLUMNS} FROM alerts "  # noqa: S608
                    "WHERE id = :id AND user_id = :uid",
                ),
                params,
            )
        ).first()
    else:
        row = (
            await session.execute(
                text(
                    f"UPDATE alerts SET {', '.join(sets)} "  # noqa: S608
                    "WHERE id = :id AND user_id = :uid "
                    f"RETURNING {_SELECT_COLUMNS}",
                ),
                params,
            )
        ).first()
        await session.commit()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    return _row_to_alert(row)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> None:
    result = await session.execute(
        text("DELETE FROM alerts WHERE id = :id AND user_id = :uid RETURNING id"),
        {"id": alert_id, "uid": user.id},
    )
    deleted = result.first()
    await session.commit()
    if deleted is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
