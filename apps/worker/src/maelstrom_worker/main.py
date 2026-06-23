from typing import Any, ClassVar

import structlog
from arq import cron
from arq.connections import RedisSettings

from . import tasks
from .live import manager as live_manager
from .settings import get_settings
from .streams import manager as stream_manager

log = structlog.get_logger()


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    log.info("worker.startup", env=settings.env)
    # Kick a sync on every worker boot so a fresh deploy populates instruments
    # without an out-of-band step. Idempotent. Daily cron still runs at 03:00 UTC.
    pool = ctx.get("redis")
    if pool is not None:
        try:
            await pool.enqueue_job("sync_instruments")
            log.info("worker.startup.enqueued_initial_sync")
        except Exception as e:  # opportunistic; don't fail boot if Redis isn't ready
            log.warning("worker.startup.enqueue_failed", error=str(e))

    # Spin up live OHLCV streams. These run for the lifetime of the worker
    # process alongside arq's job loop.
    await stream_manager.start_default()
    await live_manager.start()


async def shutdown(ctx: dict[str, Any]) -> None:
    await live_manager.stop()
    await stream_manager.stop_all()
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
        tasks.run_backtest,
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
