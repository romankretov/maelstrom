"""Live strategy manager.

Polls live_strategies every few seconds; spawns/cancels LiveRunner tasks
for rows transitioning into pending_start / pending_stop. Also ensures
the StreamManager is publishing the (source, symbol, timeframe) the
strategy needs — starting an on-demand stream if not already running.

State machine (in DB):
    paused        -> POST start  -> pending_start -> running
    running       -> POST stop   -> pending_stop  -> stopped
    failed / stopped: terminal
"""

import asyncio
import contextlib
from typing import Any

import redis.asyncio as aioredis
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from maelstrom_worker.broker import Broker, HyperliquidBroker, PaperBroker
from maelstrom_worker.settings import get_settings
from maelstrom_worker.streams import manager as stream_manager

from .runner import LiveRunner

log = structlog.get_logger()


POLL_INTERVAL_SECS = 3


class LiveManager:
    def __init__(self) -> None:
        self._engine: Any = None
        self._sm: async_sessionmaker | None = None
        self._redis: aioredis.Redis | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._runners: dict[str, LiveRunner] = {}
        self._stopped = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None

    async def _ensure_db(self) -> async_sessionmaker:
        if self._sm is None:
            self._engine = create_async_engine(
                str(get_settings().database_url),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
            self._sm = async_sessionmaker(self._engine, expire_on_commit=False)
        return self._sm

    async def _ensure_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(str(get_settings().redis_url))
        return self._redis

    async def start(self) -> None:
        await self._ensure_db()
        await self._ensure_redis()
        self._loop_task = asyncio.create_task(self._loop(), name="live.manager.loop")
        log.info("live.manager.start")

    async def stop(self) -> None:
        self._stopped.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        if self._redis is not None:
            await self._redis.aclose()
        if self._engine is not None:
            await self._engine.dispose()

    async def _loop(self) -> None:
        # On boot, resume anything that was running before the worker died.
        await self._resume_orphans()

        while not self._stopped.is_set():
            try:
                await self._tick()
            except Exception as e:
                log.exception("live.manager.tick_error", error=str(e))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stopped.wait(), timeout=POLL_INTERVAL_SECS)

    async def _resume_orphans(self) -> None:
        """Any row stuck in 'running' from a previous worker process needs to
        be re-spawned. Same for 'pending_start'."""
        sm = await self._ensure_db()
        async with sm() as session:
            await session.execute(
                text(
                    "UPDATE live_strategies SET status='pending_start', updated_at=now() "
                    "WHERE status='running'",
                ),
            )
            await session.commit()

    async def _tick(self) -> None:
        sm = await self._ensure_db()
        async with sm() as session:
            pending_starts = (
                (
                    await session.execute(
                        text(
                            "SELECT id FROM live_strategies WHERE status = 'pending_start'",
                        ),
                    )
                )
                .scalars()
                .all()
            )
            pending_stops = (
                (
                    await session.execute(
                        text(
                            "SELECT id FROM live_strategies WHERE status = 'pending_stop'",
                        ),
                    )
                )
                .scalars()
                .all()
            )

        for lid in pending_starts:
            await self._spawn(str(lid))

        for lid in pending_stops:
            await self._cancel(str(lid))

    async def _spawn(self, live_id: str) -> None:
        if live_id in self._tasks and not self._tasks[live_id].done():
            return
        sm = await self._ensure_db()
        redis = await self._ensure_redis()

        # Look up the (source, symbol, tf, account.kind) so we can route to
        # the right broker and guarantee an upstream stream exists.
        async with sm() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT ls.source, ls.symbols, ls.timeframe, "
                        "       ls.account_id, a.kind "
                        "  FROM live_strategies ls "
                        "  JOIN accounts a ON a.id = ls.account_id "
                        " WHERE ls.id = :id"
                    ),
                    {"id": live_id},
                )
            ).first()
        if row is None:
            log.warning("live.spawn.missing_row", id=live_id)
            return
        source, symbols, timeframe, account_id, account_kind = (
            row[0],
            list(row[1]),
            row[2],
            str(row[3]),
            row[4],
        )
        for sym in symbols:
            stream_manager.start(source, sym, timeframe)

        broker: Broker
        if account_kind.startswith("live_hl_"):
            broker = HyperliquidBroker(sm, account_id=account_id)
            log.info("live.broker.hyperliquid", account=account_id, kind=account_kind)
        else:
            broker = PaperBroker(sm)
            log.info("live.broker.paper", account=account_id)
        runner = LiveRunner(live_id, broker, sm, redis)
        self._runners[live_id] = runner
        self._tasks[live_id] = asyncio.create_task(
            runner.run(),
            name=f"live.runner.{live_id}",
        )
        log.info("live.manager.spawned", id=live_id)

    async def _cancel(self, live_id: str) -> None:
        runner = self._runners.get(live_id)
        if runner is not None:
            await runner.stop()
        task = self._tasks.get(live_id)
        if task is not None and not task.done():
            await asyncio.sleep(0)  # let the runner notice _stopped flag
            task.cancel()
        self._runners.pop(live_id, None)
        self._tasks.pop(live_id, None)
        # If the row was orphaned (worker restarted while pending_stop), the
        # runner was never spawned this process, so its own stop path never
        # ran — we still need to flip the row to 'stopped' here, otherwise
        # _tick() keeps re-selecting it forever and we spam this log.
        sm = await self._ensure_db()
        async with sm() as session:
            await session.execute(
                text(
                    "UPDATE live_strategies "
                    "   SET status = 'stopped', "
                    "       stopped_at = COALESCE(stopped_at, now()), "
                    "       updated_at = now() "
                    " WHERE id = :id AND status IN ('pending_stop', 'pending_start')",
                ),
                {"id": live_id},
            )
            await session.commit()
        log.info("live.manager.cancelled", id=live_id)


manager = LiveManager()
