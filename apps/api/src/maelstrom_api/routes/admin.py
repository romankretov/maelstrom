"""Admin / observability endpoints.

Pulls together the data points scattered across scanner_config, ohlcv,
audit_log, llm_calls, and live_strategies so a single dashboard can show
"is everything healthy" at a glance.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import User

router = APIRouter(prefix="/admin", tags=["admin"])


# ----------------------------------------------------------------- schemas


class ScannerSummary(BaseModel):
    enabled: bool
    interval_minutes: int
    last_run_at: datetime | None
    last_status: str | None
    last_signal_count: int | None
    last_reason: str | None


class StreamSummary(BaseModel):
    source: str
    symbol: str
    timeframe: str
    last_bar_ts: datetime | None
    lag_seconds: int | None  # now - last_bar_ts, in seconds


class WorkerSummary(BaseModel):
    last_heartbeat_at: datetime | None
    lag_seconds: int | None


class LLMCostByPurpose(BaseModel):
    purpose: str
    spend_usd: float
    calls: int


class LLMSpendSummary(BaseModel):
    spend_24h: float
    spend_7d: float
    spend_30d: float
    calls_24h: int
    calls_7d: int
    by_purpose_30d: list[LLMCostByPurpose]


class HealthSummary(BaseModel):
    scanner: ScannerSummary | None
    streams: list[StreamSummary]
    worker: WorkerSummary
    llm: LLMSpendSummary
    live_runs: int
    paper_accounts: int
    live_accounts: int


# ----------------------------------------------------------------- endpoint


@router.get("/health", response_model=HealthSummary)
async def health_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> HealthSummary:
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")

    now = datetime.now(UTC)

    # ---- scanner
    scanner_row = (
        await session.execute(
            text(
                "SELECT enabled, interval_minutes, last_run_at, last_status, "
                "       last_signal_count, last_reason "
                "  FROM scanner_config WHERE id = 1",
            ),
        )
    ).first()
    scanner: ScannerSummary | None = (
        ScannerSummary(
            enabled=bool(scanner_row[0]),
            interval_minutes=int(scanner_row[1]),
            last_run_at=scanner_row[2],
            last_status=scanner_row[3],
            last_signal_count=scanner_row[4],
            last_reason=scanner_row[5],
        )
        if scanner_row
        else None
    )

    # ---- streams: last bar per source for the active 1m streams.
    # Limit to symbols that have any recent bar (skip thousands of empty
    # cells from the instruments catalog). 24h cutoff is plenty.
    stream_rows = (
        await session.execute(
            text(
                "SELECT source, symbol, timeframe, MAX(ts) AS last_ts "
                "  FROM ohlcv "
                " WHERE timeframe = '1m' AND ts >= now() - INTERVAL '24 hours' "
                " GROUP BY source, symbol, timeframe "
                " ORDER BY source, symbol",
            ),
        )
    ).all()
    streams = [
        StreamSummary(
            source=r[0],
            symbol=r[1],
            timeframe=r[2],
            last_bar_ts=r[3],
            lag_seconds=int((now - r[3]).total_seconds()) if r[3] else None,
        )
        for r in stream_rows
    ]

    # ---- worker heartbeat
    hb_row = (
        await session.execute(
            text(
                "SELECT MAX(created_at) FROM audit_log WHERE action = 'worker.heartbeat'",
            ),
        )
    ).first()
    last_hb = hb_row[0] if hb_row else None
    worker = WorkerSummary(
        last_heartbeat_at=last_hb,
        lag_seconds=int((now - last_hb).total_seconds()) if last_hb else None,
    )

    # ---- LLM spend
    cost_rows = (
        await session.execute(
            text(
                "SELECT "
                "  COALESCE(SUM(CASE WHEN created_at >= :h24 THEN cost_usd END), 0) AS s24, "
                "  COALESCE(SUM(CASE WHEN created_at >= :d7  THEN cost_usd END), 0) AS s7, "
                "  COALESCE(SUM(cost_usd), 0) AS s30, "
                "  COUNT(*) FILTER (WHERE created_at >= :h24) AS c24, "
                "  COUNT(*) FILTER (WHERE created_at >= :d7) AS c7 "
                "  FROM llm_calls "
                " WHERE created_at >= :d30",
            ),
            {
                "h24": now - timedelta(hours=24),
                "d7": now - timedelta(days=7),
                "d30": now - timedelta(days=30),
            },
        )
    ).first()
    by_purpose_rows = (
        await session.execute(
            text(
                "SELECT purpose, SUM(cost_usd) AS spend, COUNT(*) AS n "
                "  FROM llm_calls "
                " WHERE created_at >= :d30 "
                " GROUP BY purpose ORDER BY spend DESC LIMIT 10",
            ),
            {"d30": now - timedelta(days=30)},
        )
    ).all()
    llm = LLMSpendSummary(
        spend_24h=float((cost_rows or [0, 0, 0, 0, 0])[0] or 0),
        spend_7d=float((cost_rows or [0, 0, 0, 0, 0])[1] or 0),
        spend_30d=float((cost_rows or [0, 0, 0, 0, 0])[2] or 0),
        calls_24h=int((cost_rows or [0, 0, 0, 0, 0])[3] or 0),
        calls_7d=int((cost_rows or [0, 0, 0, 0, 0])[4] or 0),
        by_purpose_30d=[
            LLMCostByPurpose(purpose=r[0], spend_usd=float(r[1] or 0), calls=int(r[2]))
            for r in by_purpose_rows
        ],
    )

    # ---- live runs + accounts
    live_runs = int(
        (
            await session.execute(
                text("SELECT COUNT(*) FROM live_strategies WHERE status = 'running'"),
            )
        ).scalar_one(),
    )
    paper_accounts = int(
        (
            await session.execute(
                text("SELECT COUNT(*) FROM accounts WHERE kind = 'paper' AND is_active = TRUE"),
            )
        ).scalar_one(),
    )
    live_accounts = int(
        (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM accounts  WHERE kind LIKE 'live_%' AND is_active = TRUE",
                ),
            )
        ).scalar_one(),
    )

    return HealthSummary(
        scanner=scanner,
        streams=streams,
        worker=worker,
        llm=llm,
        live_runs=live_runs,
        paper_accounts=paper_accounts,
        live_accounts=live_accounts,
    )
