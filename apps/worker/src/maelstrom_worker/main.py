from typing import Any, ClassVar

import structlog
from arq import cron
from arq.connections import RedisSettings

from . import tasks
from .settings import get_settings

log = structlog.get_logger()


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    log.info("worker.startup", env=settings.env)


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("worker.shutdown")


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings.from_dsn(str(settings.redis_url))


class WorkerSettings:
    """arq entrypoint. Run with: `arq maelstrom_worker.main.WorkerSettings`."""

    functions: ClassVar = [
        tasks.heartbeat,
        tasks.sync_instruments,
        tasks.backfill_ohlcv,
    ]
    cron_jobs: ClassVar = [
        cron(tasks.heartbeat, second=0),  # every minute
        cron(tasks.sync_instruments, hour=3, minute=0),  # daily 03:00 UTC
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 60 * 30  # 30 minutes; backtests can run long
    keep_result = 60 * 60 * 24  # 1 day
