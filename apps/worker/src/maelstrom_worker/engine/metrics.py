"""Performance metrics for a backtest run."""

import math
from collections import defaultdict
from datetime import datetime

from .types import EquityPoint, Fill, Metrics

# Trading periods per year. We use 365 because crypto trades 24/7.
PERIODS_PER_YEAR = 365


def _daily_returns(equity: list[EquityPoint]) -> list[float]:
    """Downsample equity curve to one point per day (last value) and return
    daily simple returns."""
    if not equity:
        return []
    by_day: dict[datetime, float] = {}
    for p in equity:
        day = p.ts.replace(hour=0, minute=0, second=0, microsecond=0)
        by_day[day] = p.equity
    days = sorted(by_day.keys())
    if len(days) < 2:
        return []
    out: list[float] = []
    for i in range(1, len(days)):
        prev = by_day[days[i - 1]]
        cur = by_day[days[i]]
        if prev <= 0:
            continue
        out.append((cur - prev) / prev)
    return out


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def compute_metrics(
    equity_curve: list[EquityPoint],
    fills: list[Fill],
    initial_capital: float,
) -> Metrics:
    m = Metrics(initial_capital=initial_capital)
    if not equity_curve:
        return m

    final_equity = equity_curve[-1].equity
    m.final_equity = final_equity
    m.total_return = (final_equity / initial_capital) - 1.0 if initial_capital > 0 else 0.0
    m.max_drawdown = max((p.drawdown for p in equity_curve), default=0.0)

    rets = _daily_returns(equity_curve)
    if rets:
        mean = sum(rets) / len(rets)
        sd = _stdev(rets)
        if sd > 0:
            m.sharpe = (mean / sd) * math.sqrt(PERIODS_PER_YEAR)
        neg = [r for r in rets if r < 0]
        sd_neg = _stdev(neg) if len(neg) > 1 else 0.0
        if sd_neg > 0:
            m.sortino = (mean / sd_neg) * math.sqrt(PERIODS_PER_YEAR)

    # Calmar: annualised return / max drawdown
    # Annualise using time span.
    if m.max_drawdown > 0 and len(equity_curve) >= 2:
        days = (equity_curve[-1].ts - equity_curve[0].ts).total_seconds() / 86400
        if days > 0:
            ann_ret = (1 + m.total_return) ** (PERIODS_PER_YEAR / days) - 1
            m.calmar = ann_ret / m.max_drawdown

    # Trade metrics — count realised PnL events only (i.e. closing trades).
    closing = [f for f in fills if f.pnl != 0.0]
    wins = [f for f in closing if f.pnl > 0]
    losses = [f for f in closing if f.pnl < 0]
    m.trade_count = len(closing)
    if closing:
        m.win_rate = len(wins) / len(closing)
        gross_win = sum(f.pnl for f in wins)
        gross_loss = -sum(f.pnl for f in losses)
        m.profit_factor = gross_win / gross_loss if gross_loss > 0 else math.inf

    # Suppress per-symbol noise (currently unused but useful for debugging).
    _ = defaultdict
    return m
