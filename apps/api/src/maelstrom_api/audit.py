from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog


async def record(
    session: AsyncSession,
    *,
    action: str,
    actor_kind: str = "user",
    actor_id: UUID | None = None,
    target_kind: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append a row to audit_log. Caller is responsible for committing."""
    entry = AuditLog(
        actor_kind=actor_kind,
        actor_id=actor_id,
        action=action,
        target_kind=target_kind,
        target_id=target_id,
        payload=payload or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(entry)
