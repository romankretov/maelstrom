from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .settings import get_settings

log = structlog.get_logger()


async def heartbeat(ctx: dict[str, Any]) -> str:
    """Cron task — writes an audit log row every 60s so we can verify the worker→DB path.

    Replaced/extended in later phases with real ingest, backtest, and strategy run tasks.
    """
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        await session.execute(
            text(
                "INSERT INTO audit_log (actor_kind, action, payload) "
                "VALUES ('worker', 'worker.heartbeat', :payload::json)",
            ),
            {"payload": '{"ts": "' + datetime.now(UTC).isoformat() + '"}'},
        )
        await session.commit()
    await engine.dispose()
    log.info("worker.heartbeat", env=settings.env)
    return "ok"
