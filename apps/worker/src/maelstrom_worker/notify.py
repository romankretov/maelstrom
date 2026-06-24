"""Notification dispatcher.

Two responsibilities:
  1. `notify_all(event_type, payload)` — fan-out helper called by other code
     (broker fills, scanner, account kill, ...) that enqueues one
     dispatch_notification job per matching channel.
  2. `dispatch_notification(ctx, channel_id, event_type, payload)` — arq
     task that loads the channel, applies quiet hours, formats the
     message, and POSTs to Telegram or Discord. Records to audit_log on
     send/fail.

Channels are scoped per-user via notification_channels.user_id. Each
channel has an `events` array — we only fan out to channels whose array
contains the event_type (`test` is always allowed).
"""

from datetime import UTC, datetime, time
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from .crypto import decrypt_str

log = structlog.get_logger()


async def _send_telegram(bot_token: str, chat_id: str, text_msg: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            url,
            json={"chat_id": chat_id, "text": text_msg, "parse_mode": "Markdown"},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"telegram error {r.status_code}: {r.text[:200]}")


async def _send_discord(webhook_url: str, text_msg: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(webhook_url, json={"content": text_msg})
        if r.status_code >= 400:
            raise RuntimeError(f"discord error {r.status_code}: {r.text[:200]}")


def _in_quiet_hours(now_utc: time, qs: time | None, qe: time | None) -> bool:
    if qs is None or qe is None:
        return False
    if qs <= qe:
        return qs <= now_utc <= qe
    # Wraps midnight
    return now_utc >= qs or now_utc <= qe


def _format_message(event_type: str, payload: dict[str, Any]) -> str:
    if "text" in payload:
        return str(payload["text"])
    title = event_type.replace("_", " ").title()
    lines = [f"*Maelstrom — {title}*"]
    for k, v in payload.items():
        lines.append(f"_{k}_: `{v}`")
    return "\n".join(lines)


async def dispatch_notification(
    ctx: dict[str, Any],
    channel_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    """arq task entry."""
    from .tasks import _sm  # cached session maker

    sm = _sm()
    async with sm() as session:
        row = (
            await session.execute(
                text(
                    "SELECT kind, label, config, secret_enc, enabled, events, "
                    "       quiet_start, quiet_end, user_id "
                    "  FROM notification_channels WHERE id = :id",
                ),
                {"id": channel_id},
            )
        ).first()
    if row is None:
        log.warning("notify.channel_missing", channel_id=channel_id)
        return {"status": "missing"}
    kind, label, config, secret_enc, enabled, events, qs, qe, user_id = row
    if not enabled:
        log.info("notify.channel_disabled", channel_id=channel_id, label=label)
        return {"status": "disabled"}
    if event_type != "test" and event_type not in (events or []):
        return {"status": "not_subscribed"}
    if _in_quiet_hours(datetime.now(UTC).time(), qs, qe):
        return {"status": "quiet_hours"}

    text_msg = _format_message(event_type, payload)
    try:
        if kind == "telegram":
            if not secret_enc:
                raise RuntimeError("telegram channel missing bot token")
            bot_token = decrypt_str(bytes(secret_enc))
            chat_id = str((config or {}).get("chat_id") or "")
            if not chat_id:
                raise RuntimeError("telegram channel missing chat_id")
            await _send_telegram(bot_token, chat_id, text_msg)
        elif kind == "discord":
            webhook_url = str((config or {}).get("webhook_url") or "")
            if not webhook_url:
                raise RuntimeError("discord channel missing webhook_url")
            await _send_discord(webhook_url, text_msg)
        else:
            raise RuntimeError(f"unknown channel kind: {kind}")
    except Exception as e:
        log.exception(
            "notify.send_failed",
            channel_id=channel_id,
            kind=kind,
            event=event_type,
            error=str(e),
        )
        async with sm() as session:
            await session.execute(
                text(
                    "INSERT INTO audit_log "
                    " (actor_kind, action, target_kind, target_id, payload) "
                    "VALUES ('worker', 'notification.failed', "
                    "        'notification_channel', :id, "
                    "        CAST(:p AS jsonb))",
                ),
                {"id": channel_id, "p": _to_json({"event": event_type, "error": str(e)[:1000]})},
            )
            await session.commit()
        return {"status": "failed", "error": str(e)[:400]}

    log.info("notify.sent", channel_id=channel_id, kind=kind, event=event_type)
    async with sm() as session:
        await session.execute(
            text(
                "INSERT INTO audit_log "
                " (actor_kind, action, target_kind, target_id, payload) "
                "VALUES ('worker', 'notification.sent', "
                "        'notification_channel', :id, "
                "        CAST(:p AS jsonb))",
            ),
            {"id": channel_id, "p": _to_json({"event": event_type, "user_id": str(user_id)})},
        )
        await session.commit()
    return {"status": "sent"}


def _to_json(d: dict[str, Any]) -> str:
    import orjson

    return orjson.dumps(d).decode()


# ---- fan-out helper -----------------------------------------------------


async def notify_all(
    sm: async_sessionmaker,
    arq: Any,
    event_type: str,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> int:
    """Enqueue one dispatch_notification job per channel whose `events`
    contains event_type. Returns count enqueued."""
    async with sm() as session:
        params = {"event": event_type}
        sql = "SELECT id FROM notification_channels  WHERE enabled = TRUE AND :event = ANY(events)"
        if user_id is not None:
            sql += " AND user_id = :uid"
            params["uid"] = user_id
        rows = (await session.execute(text(sql), params)).scalars().all()
    for cid in rows:
        await arq.enqueue_job("dispatch_notification", str(cid), event_type, payload)
    return len(rows)
