"""Admin / observability endpoints.

Pulls together the data points scattered across scanner_config, ohlcv,
audit_log, llm_calls, and live_strategies so a single dashboard can show
"is everything healthy" at a glance.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

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


class DashboardLiveRun(BaseModel):
    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_name: str | None = None
    account_name: str | None = None
    symbols: list[str]
    timeframe: str
    status: str


class DashboardFill(BaseModel):
    ts: datetime
    account_name: str | None = None
    strategy_name: str | None = None
    symbol: str
    side: str
    qty: float
    price: float
    pnl: float


class DashboardSignal(BaseModel):
    id: uuid.UUID
    ts: datetime
    symbol: str
    direction: str
    score: float
    confidence: float | None = None
    horizon: str | None = None


class DashboardOverview(BaseModel):
    total_equity: float
    total_cash: float
    today_pnl: float
    running_strategies: int
    open_positions: int
    runs: list[DashboardLiveRun]
    fills: list[DashboardFill]
    signals: list[DashboardSignal]


class SetupChecklist(BaseModel):
    """Lightweight 'how far through setup is this user' status — drives
    the dashboard onboarding card. Each item is true once the user has
    crossed a meaningful threshold (registered, configured a provider, etc.)
    so the card auto-clears as the user makes progress."""

    admin_exists: bool
    llm_key_configured: bool
    notification_channel_configured: bool
    has_account: bool
    hl_credentials_configured: bool
    has_strategy: bool
    has_backtest: bool


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


@router.get("/dashboard", response_model=DashboardOverview)
async def dashboard_overview(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> DashboardOverview:
    """One-call overview powering /dashboard: total equity across the
    caller's accounts, today's P&L, currently-running live strategies,
    most recent fills, latest active signals.

    Scope: admin sees everything, regular user sees only own accounts
    + own strategies. Signal feed is global (scanner is shared).
    """
    is_admin = bool(user.is_superuser)
    params: dict[str, Any] = {"uid": user.id, "admin": is_admin}

    # ---- account equity rollup
    # Sum the latest account_equity per account the caller can see, and
    # compare against the latest snapshot from before UTC midnight to get
    # "today's P&L".
    equity_rows = (
        await session.execute(
            text(
                "WITH latest AS ("
                "  SELECT DISTINCT ON (account_id) account_id, ts, equity, cash "
                "    FROM account_equity ORDER BY account_id, ts DESC"
                "), today_open AS ("
                "  SELECT DISTINCT ON (account_id) account_id, equity AS open_equity "
                "    FROM account_equity "
                "   WHERE ts < date_trunc('day', now()) "
                "   ORDER BY account_id, ts DESC"
                ") "
                "SELECT a.id, l.equity, l.cash, t.open_equity "
                "  FROM accounts a "
                "  LEFT JOIN latest l ON l.account_id = a.id "
                "  LEFT JOIN today_open t ON t.account_id = a.id "
                " WHERE a.is_active = TRUE AND (:admin OR a.owner_id = :uid)",
            ),
            params,
        )
    ).all()
    total_equity = sum(float(r[1]) for r in equity_rows if r[1] is not None)
    total_cash = sum(float(r[2]) for r in equity_rows if r[2] is not None)
    today_pnl = sum(
        float(r[1]) - float(r[3]) for r in equity_rows if r[1] is not None and r[3] is not None
    )

    # ---- live runs
    run_rows = (
        await session.execute(
            text(
                "SELECT ls.id, ls.strategy_id, s.name, a.name, ls.symbols, ls.timeframe, ls.status "
                "  FROM live_strategies ls "
                "  JOIN strategies s ON s.id = ls.strategy_id "
                "  JOIN accounts a ON a.id = ls.account_id "
                " WHERE ls.status IN ('running', 'pending_start') "
                "   AND (:admin OR s.owner_id = :uid) "
                " ORDER BY ls.created_at DESC LIMIT 20",
            ),
            params,
        )
    ).all()
    runs = [
        DashboardLiveRun(
            id=r[0],
            strategy_id=r[1],
            strategy_name=r[2],
            account_name=r[3],
            symbols=list(r[4]),
            timeframe=r[5],
            status=r[6],
        )
        for r in run_rows
    ]

    # ---- recent fills
    fill_rows = (
        await session.execute(
            text(
                "SELECT f.ts, a.name, s.name, f.symbol, f.side, f.qty, f.price, f.pnl "
                "  FROM fills f "
                "  JOIN accounts a ON a.id = f.account_id "
                "  LEFT JOIN orders o ON o.id = f.order_id "
                "  LEFT JOIN live_strategies ls ON ls.id = o.live_strategy_id "
                "  LEFT JOIN strategies s ON s.id = ls.strategy_id "
                " WHERE :admin OR a.owner_id = :uid "
                " ORDER BY f.ts DESC LIMIT 10",
            ),
            params,
        )
    ).all()
    fills = [
        DashboardFill(
            ts=r[0],
            account_name=r[1],
            strategy_name=r[2],
            symbol=r[3],
            side=r[4],
            qty=float(r[5]),
            price=float(r[6]),
            pnl=float(r[7]),
        )
        for r in fill_rows
    ]

    # ---- open positions count (caller scope)
    open_positions = int(
        (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM positions p "
                    "  JOIN accounts a ON a.id = p.account_id "
                    " WHERE p.qty != 0 AND (:admin OR a.owner_id = :uid)",
                ),
                params,
            )
        ).scalar_one(),
    )

    # ---- latest non-expired signals (global)
    sig_rows = (
        await session.execute(
            text(
                "SELECT id, ts, symbol, direction, score, confidence, horizon "
                "  FROM signals "
                " WHERE expires_at IS NOT NULL AND expires_at >= now() "
                " ORDER BY ts DESC LIMIT 5",
            ),
        )
    ).all()
    signals = [
        DashboardSignal(
            id=r[0],
            ts=r[1],
            symbol=r[2],
            direction=r[3],
            score=float(r[4]),
            confidence=float(r[5]) if r[5] is not None else None,
            horizon=r[6],
        )
        for r in sig_rows
    ]

    return DashboardOverview(
        total_equity=total_equity,
        total_cash=total_cash,
        today_pnl=today_pnl,
        running_strategies=len(runs),
        open_positions=open_positions,
        runs=runs,
        fills=fills,
        signals=signals,
    )


@router.get("/setup-checklist", response_model=SetupChecklist)
async def setup_checklist(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> SetupChecklist:
    """Per-user setup progress. Counts only the caller's owned rows
    (admins see global counts since the system is otherwise theirs)."""

    # Pass admin-ness as a bound bool so the WHERE clauses stay a single
    # fixed string — avoids ruff S608 on concatenated SQL and lets PG plan
    # the query once.
    is_admin = bool(user.is_superuser)
    params = {"uid": user.id, "admin": is_admin}

    async def _exists(sql: str, p: dict[str, Any] | None = None) -> bool:
        result = await session.execute(text(sql), p or {})
        return bool(result.scalar())

    admin_exists = await _exists("SELECT COUNT(*) > 0 FROM users WHERE is_superuser = TRUE")
    llm_key_configured = await _exists(
        "SELECT COUNT(*) > 0 FROM llm_providers   WHERE api_key_enc IS NOT NULL AND enabled = TRUE",
    )
    notification_channel_configured = await _exists(
        "SELECT COUNT(*) > 0 FROM notification_channels WHERE enabled = TRUE",
    )
    has_account = await _exists(
        "SELECT COUNT(*) > 0 FROM accounts "
        "  WHERE is_active = TRUE AND (:admin OR owner_id = :uid)",
        params,
    )
    hl_credentials_configured = await _exists(
        "SELECT COUNT(*) > 0 FROM accounts "
        "  WHERE kind LIKE 'live_hl_%' AND api_key_enc IS NOT NULL "
        "    AND (:admin OR owner_id = :uid)",
        params,
    )
    has_strategy = await _exists(
        "SELECT COUNT(*) > 0 FROM strategies "
        "  WHERE is_archived = FALSE AND (:admin OR owner_id = :uid)",
        params,
    )
    has_backtest = await _exists(
        "SELECT COUNT(*) > 0 FROM backtest_runs br "
        "  JOIN strategies s ON s.id = br.strategy_id "
        "  WHERE :admin OR s.owner_id = :uid",
        params,
    )

    return SetupChecklist(
        admin_exists=admin_exists,
        llm_key_configured=llm_key_configured,
        notification_channel_configured=notification_channel_configured,
        has_account=has_account,
        hl_credentials_configured=hl_credentials_configured,
        has_strategy=has_strategy,
        has_backtest=has_backtest,
    )
