"""Notification channel CRUD + send-test endpoint."""

import uuid
from typing import Annotated, Any

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import audit, crypto
from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import NotificationChannel, User
from maelstrom_api.routes.markets import get_arq_pool
from maelstrom_api.schemas.notification import (
    NotificationChannelCreate,
    NotificationChannelOut,
    NotificationChannelUpdate,
)

router = APIRouter(
    prefix="/notifications/channels",
    tags=["notifications"],
    dependencies=[Depends(current_active_user)],
)


# Separate router so the path doesn't have to live under /channels.
preview_router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(current_active_user)],
)


# Mirrors the worker's notify._format_message — keep these aligned. The
# worker is the source of truth; this is a UI preview only.
def _format_preview(event_type: str, payload: dict[str, Any]) -> str:
    if "text" in payload:
        return str(payload["text"])
    title = event_type.replace("_", " ").title()
    lines = [f"*Maelstrom — {title}*"]
    for k, v in payload.items():
        lines.append(f"_{k}_: `{v}`")
    return "\n".join(lines)


# One example per event type. The shape matches what the actual
# producers send — kept narrow on purpose so the preview reflects the
# real on-the-wire payload.
_SAMPLE_PAYLOADS: dict[str, dict[str, Any]] = {
    "kill_account": {
        "account": "Paper test",
        "reason": "daily loss limit hit (-5.20%)",
        "equity": "$9,481.20",
    },
    "backtest_done": {
        "strategy": "SMA crossover",
        "sharpe": "1.42",
        "total_return": "+12.30%",
        "max_drawdown": "-4.10%",
        "trades": 38,
    },
    "signal_top": {
        "symbol": "BTC-PERP",
        "direction": "long",
        "score": "82.5",
        "horizon": "swing",
        "rationale": "Reclaim of 200-day MA on rising open interest.",
    },
    "live_failed": {
        "strategy": "Mean reversion v3",
        "account": "HL testnet",
        "error": "Strategy module raised: ZeroDivisionError",
    },
    "fill": {
        "account": "HL testnet",
        "symbol": "BTC-PERP",
        "side": "buy",
        "qty": "0.0140",
        "price": "$72,150.00",
        "fee": "$0.50",
    },
    "order_rejected": {
        "account": "HL testnet",
        "symbol": "BTC-PERP",
        "side": "buy",
        "reason": "post-only would cross book",
    },
    "daily_summary": {
        "account": "HL main",
        "pnl_24h": "+$184.20",
        "open_positions": 2,
        "fills_24h": 7,
    },
}


class NotificationPreview(BaseModel):
    event: str
    payload: dict[str, Any]
    rendered: str


@preview_router.get("/preview", response_model=NotificationPreview)
async def preview_notification(
    user: Annotated[User, Depends(current_active_user)],
    event: Annotated[str, Query(min_length=1, max_length=64)],
) -> NotificationPreview:
    """Return the rendered preview text for a given event type. Mirrors the
    worker formatter — useful as 'what will I actually see in Telegram'.
    """
    del user  # auth gate only
    payload = _SAMPLE_PAYLOADS.get(
        event,
        {"text": f"(no sample payload for '{event}' — falling back to plain text)"},
    )
    return NotificationPreview(
        event=event,
        payload=payload,
        rendered=_format_preview(event, payload),
    )


def _to_out(c: NotificationChannel) -> NotificationChannelOut:
    return NotificationChannelOut(
        id=c.id,
        user_id=c.user_id,
        kind=c.kind,
        label=c.label,
        config=c.config,
        has_secret=c.secret_enc is not None,
        enabled=c.enabled,
        events=c.events,
        quiet_start=c.quiet_start,
        quiet_end=c.quiet_end,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def _validate_kind(kind: str) -> None:
    if kind not in ("telegram", "discord"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"unknown channel kind '{kind}' (telegram|discord)",
        )


@router.get("", response_model=list[NotificationChannelOut])
async def list_channels(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> list[NotificationChannelOut]:
    stmt = select(NotificationChannel).where(NotificationChannel.user_id == user.id)
    if user.is_superuser:
        stmt = select(NotificationChannel)
    stmt = stmt.order_by(NotificationChannel.created_at.asc())
    rows = list((await session.execute(stmt)).scalars().all())
    return [_to_out(c) for c in rows]


@router.post(
    "",
    response_model=NotificationChannelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    body: NotificationChannelCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> NotificationChannelOut:
    _validate_kind(body.kind)
    if body.kind == "telegram":
        if not body.secret:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "telegram channel requires `secret` (bot token)",
            )
        if not body.config.get("chat_id"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "telegram channel requires config.chat_id",
            )
    elif body.kind == "discord" and not body.config.get("webhook_url"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "discord channel requires config.webhook_url",
        )

    c = NotificationChannel(
        user_id=user.id,
        kind=body.kind,
        label=body.label,
        config=body.config,
        secret_enc=crypto.encrypt_str(body.secret) if body.secret else None,
        events=body.events,
        quiet_start=body.quiet_start,
        quiet_end=body.quiet_end,
    )
    session.add(c)
    await audit.record(
        session,
        action="notification_channel.create",
        actor_id=user.id,
        target_kind="notification_channel",
        target_id=None,
        payload={"kind": body.kind, "label": body.label},
    )
    await session.commit()
    await session.refresh(c)
    return _to_out(c)


@router.patch("/{channel_id}", response_model=NotificationChannelOut)
async def update_channel(
    channel_id: uuid.UUID,
    body: NotificationChannelUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> NotificationChannelOut:
    c = await session.get(NotificationChannel, channel_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    if c.user_id != user.id and not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your channel")

    if body.label is not None:
        c.label = body.label
    if body.config is not None:
        c.config = body.config
    if body.secret is not None:
        c.secret_enc = crypto.encrypt_str(body.secret) if body.secret else None
    if body.enabled is not None:
        c.enabled = body.enabled
    if body.events is not None:
        c.events = body.events
    if body.quiet_start is not None:
        c.quiet_start = body.quiet_start
    if body.quiet_end is not None:
        c.quiet_end = body.quiet_end
    await audit.record(
        session,
        action="notification_channel.update",
        actor_id=user.id,
        target_kind="notification_channel",
        target_id=str(channel_id),
        payload=body.model_dump(exclude_none=True, exclude={"secret"}),
    )
    await session.commit()
    await session.refresh(c)
    return _to_out(c)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> None:
    c = await session.get(NotificationChannel, channel_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    if c.user_id != user.id and not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your channel")
    await session.delete(c)
    await audit.record(
        session,
        action="notification_channel.delete",
        actor_id=user.id,
        target_kind="notification_channel",
        target_id=str(channel_id),
    )
    await session.commit()


@router.post("/{channel_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def send_test(
    channel_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> dict[str, str]:
    c = await session.get(NotificationChannel, channel_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    if c.user_id != user.id and not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your channel")
    await arq.enqueue_job(
        "dispatch_notification",
        str(channel_id),
        "test",
        {"text": "Maelstrom test notification — channel works ✅"},
    )
    return {"status": "queued"}
