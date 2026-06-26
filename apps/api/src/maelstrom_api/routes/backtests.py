"""Backtest run creation + read-side endpoints."""

import uuid
from typing import Annotated

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import audit
from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import (
    BacktestEquity,
    BacktestRun,
    BacktestStatus,
    BacktestTrade,
    Strategy,
    StrategyVersion,
    User,
)
from maelstrom_api.routes.markets import get_arq_pool
from maelstrom_api.schemas.backtest import (
    BacktestCreate,
    BacktestDiagnostics,
    BacktestRunOut,
    EquityPointOut,
    SweepRequest,
    SweepResponse,
    TradeOut,
)

router = APIRouter(
    prefix="/backtests",
    tags=["backtests"],
    dependencies=[Depends(current_active_user)],
)


def _can_access_strategy(strategy: Strategy, user: User) -> bool:
    return user.is_superuser or strategy.owner_id == user.id


async def _latest_version(session: AsyncSession, strategy_id: uuid.UUID) -> StrategyVersion | None:
    stmt = (
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(desc(StrategyVersion.version))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ---------------------------------------------------------------- create


@router.post(
    "/strategies/{strategy_id}",
    response_model=BacktestRunOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_backtest(
    strategy_id: uuid.UUID,
    body: BacktestCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> BacktestRun:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    if body.range_start >= body.range_end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "range_start must be before range_end")

    # Resolve strategy_version_id (default: latest)
    if body.strategy_version_id is not None:
        version = await session.get(StrategyVersion, body.strategy_version_id)
        if version is None or version.strategy_id != strategy_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid strategy_version_id")
    else:
        version = await _latest_version(session, strategy_id)
        if version is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "strategy has no versions")

    run = BacktestRun(
        strategy_id=strategy_id,
        strategy_version_id=version.id,
        source=body.source,
        symbols=body.symbols,
        timeframe=body.timeframe,
        range_start=body.range_start,
        range_end=body.range_end,
        initial_capital=body.initial_capital,
        params=body.params,
        status=BacktestStatus.PENDING.value,
        requester_id=user.id,
    )
    session.add(run)
    await audit.record(
        session,
        action="backtest.create",
        actor_id=user.id,
        target_kind="strategy",
        target_id=str(strategy_id),
        payload={
            "source": body.source,
            "symbols": body.symbols,
            "timeframe": body.timeframe,
            "range_start": body.range_start.isoformat(),
            "range_end": body.range_end.isoformat(),
            "version": version.version,
        },
    )
    await session.commit()
    await session.refresh(run)

    await arq.enqueue_job("run_backtest", str(run.id))
    return run


# ---------------------------------------------------------------- sweep


@router.post(
    "/strategies/{strategy_id}/sweep",
    response_model=SweepResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sweep_backtest(
    strategy_id: uuid.UUID,
    body: SweepRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> SweepResponse:
    """Queue N backtest runs of the same strategy varying one numeric param.

    Pairs with the /backtests/compare page — frontend navigates there with
    the returned ids when the sweep finishes.
    """
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    if body.base.range_start >= body.base.range_end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "range_start must be before range_end")
    if body.base.strategy_version_id is not None:
        version = await session.get(StrategyVersion, body.base.strategy_version_id)
        if version is None or version.strategy_id != strategy_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid strategy_version_id")
    else:
        version = await _latest_version(session, strategy_id)
        if version is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "strategy has no versions")

    # Inclusive linear spread.
    step = (body.stop - body.start) / (body.steps - 1)
    values = [body.start + i * step for i in range(body.steps)]

    runs: list[BacktestRun] = []
    for v in values:
        run_params = dict(body.base.params)
        run_params[body.param_name] = v
        runs.append(
            BacktestRun(
                strategy_id=strategy_id,
                strategy_version_id=version.id,
                source=body.base.source,
                symbols=body.base.symbols,
                timeframe=body.base.timeframe,
                range_start=body.base.range_start,
                range_end=body.base.range_end,
                initial_capital=body.base.initial_capital,
                params=run_params,
                status=BacktestStatus.PENDING.value,
                requester_id=user.id,
            ),
        )
    session.add_all(runs)
    await audit.record(
        session,
        action="backtest.sweep",
        actor_id=user.id,
        target_kind="strategy",
        target_id=str(strategy_id),
        payload={
            "param_name": body.param_name,
            "start": body.start,
            "stop": body.stop,
            "steps": body.steps,
            "values": values,
        },
    )
    await session.commit()
    for run in runs:
        await arq.enqueue_job("run_backtest", str(run.id))
    return SweepResponse(
        queued=len(runs),
        backtest_run_ids=[r.id for r in runs],
        values=values,
    )


# ---------------------------------------------------------------- read


async def _load_and_authorize(
    session: AsyncSession,
    run_id: uuid.UUID,
    user: User,
) -> BacktestRun:
    run = await session.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backtest not found")
    s = await session.get(Strategy, run.strategy_id)
    if s is None or not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your backtest")
    return run


@router.get("/{run_id}", response_model=BacktestRunOut)
async def get_backtest(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> BacktestRun:
    return await _load_and_authorize(session, run_id, user)


@router.get("/{run_id}/equity", response_model=list[EquityPointOut])
async def get_equity(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=10000)] = 3000,
) -> list[BacktestEquity]:
    await _load_and_authorize(session, run_id, user)
    stmt = (
        select(BacktestEquity)
        .where(BacktestEquity.run_id == run_id)
        .order_by(BacktestEquity.ts.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{run_id}/trades", response_model=list[TradeOut])
async def get_trades(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[BacktestTrade]:
    await _load_and_authorize(session, run_id, user)
    stmt = (
        select(BacktestTrade)
        .where(BacktestTrade.run_id == run_id)
        .order_by(BacktestTrade.ts.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{run_id}/diagnostics", response_model=BacktestDiagnostics)
async def get_diagnostics(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> BacktestDiagnostics:
    """Per-trade and equity-curve diagnostics computed on the fly."""
    await _load_and_authorize(session, run_id, user)

    trade_rows = (
        (
            await session.execute(
                select(BacktestTrade)
                .where(BacktestTrade.run_id == run_id)
                .order_by(BacktestTrade.ts),
            )
        )
        .scalars()
        .all()
    )
    equity_rows = (
        (
            await session.execute(
                select(BacktestEquity)
                .where(BacktestEquity.run_id == run_id)
                .order_by(BacktestEquity.ts),
            )
        )
        .scalars()
        .all()
    )

    # ---- per-fill stats. We treat each fill as a "trade" event; closing
    # fills carry realized PnL, opens carry zero PnL.
    fills_count = len(trade_rows)
    pnls = [float(t.pnl) for t in trade_rows]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]
    largest_win = max(winners) if winners else 0.0
    largest_loss = min(losers) if losers else 0.0
    avg_win = sum(winners) / len(winners) if winners else 0.0
    avg_loss = sum(losers) / len(losers) if losers else 0.0
    win_rate = (len(winners) / fills_count) if fills_count else 0.0
    gross_profit = sum(winners)
    gross_loss = sum(losers)
    profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else None
    expectancy = (sum(pnls) / fills_count) if fills_count else 0.0

    # Longest streaks
    longest_win = longest_lose = cur_win = cur_lose = 0
    for p in pnls:
        if p > 0:
            cur_win += 1
            cur_lose = 0
            longest_win = max(longest_win, cur_win)
        elif p < 0:
            cur_lose += 1
            cur_win = 0
            longest_lose = max(longest_lose, cur_lose)
        else:
            cur_win = cur_lose = 0

    # Exposure + PnL by symbol
    exposure_by_symbol: dict[str, float] = {}
    pnl_by_symbol: dict[str, float] = {}
    for t in trade_rows:
        exposure_by_symbol[t.symbol] = exposure_by_symbol.get(t.symbol, 0.0) + float(t.qty) * float(
            t.price,
        )
        pnl_by_symbol[t.symbol] = pnl_by_symbol.get(t.symbol, 0.0) + float(t.pnl)

    # ---- equity-curve stats
    # max_drawdown is already on the equity row's `drawdown` field (peak-to-now).
    # longest_drawdown_bars = max consecutive bars where drawdown > 0.
    max_dd = 0.0
    longest_dd = cur_dd = 0
    bars_with_position = 0
    for eq in equity_rows:
        dd = float(eq.drawdown)
        max_dd = max(max_dd, dd)
        if dd > 0:
            cur_dd += 1
            longest_dd = max(longest_dd, cur_dd)
        else:
            cur_dd = 0

    # Time-in-market: count equity points where any non-zero position was
    # held. We don't persist per-bar positions, so approximate as "bars
    # between first and last fill" / total bars.
    if trade_rows and equity_rows:
        first_fill_ts = trade_rows[0].ts
        last_fill_ts = trade_rows[-1].ts
        bars_with_position = sum(1 for eq in equity_rows if first_fill_ts <= eq.ts <= last_fill_ts)
    time_in_market_pct = (bars_with_position / len(equity_rows)) if equity_rows else 0.0

    return BacktestDiagnostics(
        fills_count=fills_count,
        winning_fills=len(winners),
        losing_fills=len(losers),
        longest_winning_streak=longest_win,
        longest_losing_streak=longest_lose,
        largest_win=largest_win,
        largest_loss=largest_loss,
        avg_win=avg_win,
        avg_loss=avg_loss,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy=expectancy,
        time_in_market_pct=time_in_market_pct,
        max_drawdown=max_dd,
        longest_drawdown_bars=longest_dd,
        exposure_by_symbol=exposure_by_symbol,
        pnl_by_symbol=pnl_by_symbol,
    )


@router.get("/strategies/{strategy_id}", response_model=list[BacktestRunOut])
async def list_runs_for_strategy(
    strategy_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[BacktestRun]:
    s = await session.get(Strategy, strategy_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy not found")
    if not _can_access_strategy(s, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your strategy")
    stmt = (
        select(BacktestRun)
        .where(BacktestRun.strategy_id == strategy_id)
        .order_by(BacktestRun.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
