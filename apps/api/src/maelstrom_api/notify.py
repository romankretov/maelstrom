"""API-side notification fan-out. Worker has its own copy in
apps/worker/.../notify.py — keep them aligned.
"""

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


async def notify_all(
    session: AsyncSession,
    arq: Any,
    event_type: str,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> int:
    """Enqueue one dispatch_notification job per channel whose `events`
    array contains event_type. Returns count enqueued.
    Best-effort: if Redis is unhappy, we log and continue.
    """
    sql = "SELECT id FROM notification_channels  WHERE enabled = TRUE AND :event = ANY(events)"
    params: dict[str, Any] = {"event": event_type}
    if user_id is not None:
        sql += " AND user_id = :uid"
        params["uid"] = user_id
    rows = (await session.execute(text(sql), params)).scalars().all()
    sent = 0
    for cid in rows:
        try:
            await arq.enqueue_job(
                "dispatch_notification",
                str(cid),
                event_type,
                payload,
            )
            sent += 1
        except Exception as e:
            log.warning("notify_all.enqueue_failed", channel_id=str(cid), error=str(e))
    if sent:
        log.info("notify_all.enqueued", event=event_type, count=sent)
    return sent
