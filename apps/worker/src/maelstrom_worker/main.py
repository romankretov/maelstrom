from typing import Any, ClassVar

import structlog
from arq import cron
from arq.connections import RedisSettings

from . import tasks
from .alerts import evaluate_alerts
from .live import manager as live_manager
from .notify import dispatch_notification
from .scanner import scan_opportunities
from .settings import get_settings
from .streams import manager as stream_manager

log = structlog.get_logger()


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    log.info("worker.startup", env=settings.env)
    # Kick instrument sync on boot — small, idempotent, makes the catalog
    # available immediately after a fresh deploy. We deliberately do NOT
    # kick keep_market_data_fresh here: it fans out ~150 perps x 3 timeframes
    # which is a multi-minute burst against Hyperliquid's /info and trips
    # 429s for everything else on the same IP (live broker, recon). The
    # daily cron at 04:00 UTC handles bootstrap on its own.
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
        tasks.reconcile_positions,
        tasks.sync_funding_rates,
        tasks.keep_market_data_fresh,
        tasks.dry_run_strategy,
        scan_opportunities,
        evaluate_alerts,
        dispatch_notification,
    ]
    # `unique=True` is the load-bearing flag here. Without it, arq queues
    # one job per missed tick when the worker falls behind (laptop sleep,
    # GC pause, etc.) and then floods the system on resume — we've seen
    # 30+ duplicate reconcile_positions kicks in a single second, all of
    # which hit Hyperliquid's `/info` endpoint and get 429-rate-limited.
    # With unique=True, only one pending instance can exist at a time.
    cron_jobs: ClassVar = [
        cron(tasks.heartbeat, second=0, unique=True),  # every minute
        cron(tasks.sync_instruments, hour=3, minute=0, unique=True),  # daily 03:00 UTC
        cron(
            tasks.reconcile_positions,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
            unique=True,
        ),
        # AI opportunity scanner — task self-gates on scanner_config.interval_minutes.
        cron(scan_opportunities, minute=set(range(0, 60, 5)), unique=True),
        # Funding-rate history — hourly catch-up. Source caps to ~30 perps.
        cron(tasks.sync_funding_rates, minute=17, unique=True),
        # Rolling OHLCV depth keeper — runs at 04:00 UTC (quiet hour),
        # also bootstraps on first deploy via the startup enqueue below.
        cron(tasks.keep_market_data_fresh, hour=4, minute=0, unique=True),
        # Alerts — every minute. Each row gated by its own cooldown.
        cron(evaluate_alerts, second=30, unique=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 60 * 30  # 30 minutes; backtests can run long
    keep_result = 60 * 60 * 24  # 1 day
