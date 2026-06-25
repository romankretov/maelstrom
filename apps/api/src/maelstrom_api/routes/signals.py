"""LLM-generated trade signals — read-side endpoints + scanner control."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import (
    BacktestRun,
    BacktestStatus,
    Signal,
    Strategy,
    StrategyVersion,
    User,
)
from maelstrom_api.routes.markets import get_arq_pool
from maelstrom_api.schemas.signal import SignalOut

router = APIRouter(
    prefix="/signals",
    tags=["signals"],
    dependencies=[Depends(current_active_user)],
)


# ---------------------------------------------------------------- scanner config


class ScannerConfigOut(BaseModel):
    interval_minutes: int
    enabled: bool
    last_run_at: datetime | None
    last_status: str | None
    last_signal_count: int | None
    last_reason: str | None
    last_call_id: str | None
    system_prompt: str | None = None  # null ⇒ scanner falls back to default


class ScannerConfigPatch(BaseModel):
    interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    enabled: bool | None = None
    # Use an empty string to reset to default (will be stored as NULL).
    system_prompt: str | None = Field(default=None, max_length=20_000)


async def _read_scanner_config(session: AsyncSession) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                "SELECT interval_minutes, enabled, last_run_at, last_status, "
                "       last_signal_count, last_reason, last_call_id, system_prompt "
                "  FROM scanner_config WHERE id = 1",
            ),
        )
    ).first()
    if row is None:
        # Defensive: migration creates the row, but on a fresh DB we backfill.
        await session.execute(text("INSERT INTO scanner_config (id) VALUES (1)"))
        await session.commit()
        return {
            "interval_minutes": 30,
            "enabled": True,
            "last_run_at": None,
            "last_status": None,
            "last_signal_count": None,
            "last_reason": None,
            "last_call_id": None,
            "system_prompt": None,
        }
    return {
        "interval_minutes": int(row[0]),
        "enabled": bool(row[1]),
        "last_run_at": row[2],
        "last_status": row[3],
        "last_signal_count": row[4],
        "last_reason": row[5],
        "last_call_id": str(row[6]) if row[6] else None,
        "system_prompt": row[7],
    }


@router.get("/scanner-config", response_model=ScannerConfigOut)
async def get_scanner_config(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, Any]:
    return await _read_scanner_config(session)


@router.patch("/scanner-config", response_model=ScannerConfigOut)
async def patch_scanner_config(
    body: ScannerConfigPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, Any]:
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    sets: list[str] = []
    params: dict[str, Any] = {}
    if body.interval_minutes is not None:
        sets.append("interval_minutes = :im")
        params["im"] = body.interval_minutes
    if body.enabled is not None:
        sets.append("enabled = :en")
        params["en"] = body.enabled
    if body.system_prompt is not None:
        # Empty string ⇒ reset to default (NULL in DB; scanner falls back).
        sets.append("system_prompt = :sp")
        params["sp"] = body.system_prompt.strip() or None
    if not sets:
        return await _read_scanner_config(session)
    sets.append("updated_at = now()")
    await session.execute(
        text(f"UPDATE scanner_config SET {', '.join(sets)} WHERE id = 1"),  # noqa: S608
        params,
    )
    await session.commit()
    return await _read_scanner_config(session)


@router.post("/scanner-config/run-now")
async def scanner_run_now(
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
    user: Annotated[User, Depends(current_active_user)],
) -> dict[str, str]:
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    job = await arq.enqueue_job("scan_opportunities", force=True)
    return {"job_id": (job.job_id if job else "")}


# ---------------------------------------------------------------- one-click backtest


# Bars-to-hold by horizon. Calibrated against a 1h timeframe so the same
# template makes sense across intraday / swing / position signals.
_HOLD_BARS_BY_HORIZON: dict[str, int] = {
    "intraday": 24,  # 1 day on 1h
    "swing": 96,  # 4 days on 1h
    "position": 480,  # ~20 days on 1h
}
_DEFAULT_HOLD_BARS = 24


def _strategy_template(
    *,
    signal_id: str,
    source: str,
    symbol: str,
    direction: str,
    horizon: str | None,
    rationale: str,
) -> str:
    hold_bars = _HOLD_BARS_BY_HORIZON.get(horizon or "", _DEFAULT_HOLD_BARS)
    side = "buy" if direction == "long" else "sell"
    # Render via str.format so f-string braces don't fight the template body.
    return (
        '"""Auto-generated from signal {signal_id}.\n\n'
        "Signal rationale: {rationale}\n"
        "Source: {source}  Symbol: {symbol}  Direction: {direction}  "
        'Horizon: {horizon}\n"""\n\n'
        "from maelstrom_worker.engine.sdk import Strategy as _S\n"
        "from maelstrom_worker.engine.types import EngineBar\n\n\n"
        "class Strategy(_S):\n"
        '    symbols = ("{symbol}",)\n'
        '    timeframe = "1h"\n\n'
        "    def on_init(self) -> None:\n"
        "        self._entry_bar: int | None = None\n"
        "        self._bar_index: int = 0\n\n"
        "    def on_bar(self, bar: EngineBar) -> None:\n"
        "        self._bar_index += 1\n"
        "        pos = self.position(bar.symbol)\n"
        "        if pos.qty == 0 and self._entry_bar is None:\n"
        "            self.{side}(bar.symbol, notional=self.params.get('notional', 1000),\n"
        '                       reason="signal entry")\n'
        "            self._entry_bar = self._bar_index\n"
        "            return\n"
        "        if (\n"
        "            self._entry_bar is not None\n"
        "            and self._bar_index - self._entry_bar >= {hold_bars}\n"
        "        ):\n"
        '            self.close(bar.symbol, reason="signal horizon reached")\n'
        "            self._entry_bar = None\n"
    ).format(
        signal_id=signal_id,
        source=source,
        symbol=symbol,
        direction=direction,
        horizon=horizon or "—",
        rationale=rationale.replace('"""', "'''")[:500],
        side=side,
        hold_bars=hold_bars,
    )


class SignalBacktestRequest(BaseModel):
    days: int = Field(default=90, ge=7, le=365)
    notional: float = Field(default=1000, gt=0)
    initial_capital: float = Field(default=10_000, gt=0)


class SignalBacktestResponse(BaseModel):
    strategy_id: uuid.UUID
    backtest_run_id: uuid.UUID


@router.post("/{signal_id}/backtest", response_model=SignalBacktestResponse)
async def backtest_signal(
    signal_id: uuid.UUID,
    body: SignalBacktestRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> SignalBacktestResponse:
    """Scaffold a strategy from the signal + immediately queue a backtest.

    Closes the loop between the AI scanner and the strategies pipeline so
    the user can validate a signal's premise on historical data without
    hand-writing code.
    """
    sig = await session.get(Signal, signal_id)
    if sig is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "signal not found")

    code = _strategy_template(
        signal_id=str(sig.id),
        source=sig.source,
        symbol=sig.symbol,
        direction=sig.direction,
        horizon=sig.horizon,
        rationale=sig.rationale,
    )

    short_id = str(sig.id)[:8]
    # Timestamp suffix guarantees uniqueness across repeated clicks (Strategy.name
    # has a UNIQUE constraint, so a second scaffold of the same signal would 500).
    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    name = f"signal-{sig.symbol}-{sig.direction}-{short_id}-{stamp}"
    strategy = Strategy(
        name=name,
        description=f"Auto-generated from signal {short_id} ({sig.rationale[:160]}).",
        owner_id=user.id,
    )
    session.add(strategy)
    await session.flush()

    version = StrategyVersion(
        strategy_id=strategy.id,
        version=1,
        code=code,
        params={"notional": body.notional},
        author_id=user.id,
        message=f"auto-scaffolded from signal {short_id}",
    )
    session.add(version)
    await session.flush()

    run = BacktestRun(
        strategy_id=strategy.id,
        strategy_version_id=version.id,
        source=sig.source,
        symbols=[sig.symbol],
        timeframe="1h",
        range_start=now - timedelta(days=body.days),
        range_end=now,
        initial_capital=Decimal(str(body.initial_capital)),
        params={"notional": body.notional},
        status=BacktestStatus.PENDING.value,
        requester_id=user.id,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    await arq.enqueue_job("run_backtest", str(run.id))
    return SignalBacktestResponse(strategy_id=strategy.id, backtest_run_id=run.id)


# ---------------------------------------------------------------- signals list


@router.get("", response_model=list[SignalOut])
async def list_signals(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    since: Annotated[datetime | None, Query()] = None,
    symbol: Annotated[str | None, Query()] = None,
    direction: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Signal]:
    cutoff = since or datetime.now(UTC) - timedelta(days=3)
    # Only surface signals that haven't expired yet. Signals with NULL
    # expires_at are pre-TTL artifacts — treat them as stale, not eternal.
    stmt = (
        select(Signal)
        .where(Signal.ts >= cutoff)
        .where(Signal.expires_at.is_not(None))
        .where(Signal.expires_at >= datetime.now(UTC))
        .order_by(desc(Signal.ts))
        .limit(limit)
    )
    if symbol:
        stmt = stmt.where(Signal.symbol == symbol)
    if direction:
        stmt = stmt.where(Signal.direction == direction)
    return list((await session.execute(stmt)).scalars().all())
