"""Research workbench: market stats + correlation matrix.

Pure derivation from ohlcv — no new tables. Funding-rate history lives
in a follow-up push because that needs a fetcher + storage.
"""

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import User
from maelstrom_api.schemas.research import (
    CorrelationOut,
    CorrelationRequest,
    MarketStats,
)

router = APIRouter(
    prefix="/research",
    tags=["research"],
    dependencies=[Depends(current_active_user)],
)


# Bars per year per timeframe — used to annualize realized vol.
_PERIODS_PER_YEAR: dict[str, float] = {
    "1m": 60 * 24 * 365,
    "5m": 12 * 24 * 365,
    "15m": 4 * 24 * 365,
    "1h": 24 * 365,
    "4h": 6 * 365,
    "1d": 365,
}


def _stddev(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var)


def _pearson(xs: list[float], ys: list[float]) -> tuple[float | None, int]:
    n = min(len(xs), len(ys))
    if n < 2:
        return None, n
    xs, ys = xs[:n], ys[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None, n
    return num / (den_x * den_y), n


# ----------------------------------------------------------------- stats


@router.get("/stats", response_model=MarketStats)
async def market_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    source: Annotated[str, Query()],
    symbol: Annotated[str, Query()],
    timeframe: Annotated[str, Query()] = "1h",
) -> MarketStats:
    # Pull last 30 days of bars in the requested timeframe; everything else
    # derives from this single pass.
    cutoff = datetime.now(UTC) - timedelta(days=30)
    rows = (
        await session.execute(
            text(
                "SELECT ts, open, high, low, close, volume "
                "  FROM ohlcv "
                " WHERE source = :s AND symbol = :sym AND timeframe = :tf "
                "   AND ts >= :cutoff "
                " ORDER BY ts ASC",
            ),
            {"s": source, "sym": symbol, "tf": timeframe, "cutoff": cutoff},
        )
    ).all()
    if not rows:
        return MarketStats(source=source, symbol=symbol, timeframe=timeframe)

    bars = [
        {
            "ts": r[0],
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4]),
            "volume": float(r[5]),
        }
        for r in rows
    ]
    last = bars[-1]
    now_ts = last["ts"]

    def _close_at_or_before(target: datetime) -> float | None:
        for b in reversed(bars):
            if b["ts"] <= target:
                return b["close"]
        return None

    def _pct_change(window: timedelta) -> float | None:
        ref = _close_at_or_before(now_ts - window)
        if ref is None or ref == 0:
            return None
        return (last["close"] - ref) / ref

    in_24h = [b for b in bars if b["ts"] > now_ts - timedelta(hours=24)]
    annualization = math.sqrt(_PERIODS_PER_YEAR.get(timeframe, 24 * 365))

    def _ann_vol(window: timedelta) -> float | None:
        rets = [
            math.log(bars[i]["close"] / bars[i - 1]["close"])
            for i in range(1, len(bars))
            if bars[i - 1]["close"] > 0 and bars[i]["ts"] > now_ts - window
        ]
        if len(rets) < 2:
            return None
        return _stddev(rets) * annualization

    return MarketStats(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        last_price=last["close"],
        change_1h=_pct_change(timedelta(hours=1)),
        change_24h=_pct_change(timedelta(hours=24)),
        change_7d=_pct_change(timedelta(days=7)),
        change_30d=_pct_change(timedelta(days=30)),
        high_24h=max((b["high"] for b in in_24h), default=None),
        low_24h=min((b["low"] for b in in_24h), default=None),
        volume_24h=sum(b["volume"] for b in in_24h) if in_24h else None,
        realized_vol_24h=_ann_vol(timedelta(hours=24)),
        realized_vol_7d=_ann_vol(timedelta(days=7)),
        bar_count=len(bars),
        earliest_ts=bars[0]["ts"],
        latest_ts=last["ts"],
    )


# ----------------------------------------------------------------- correlation


@router.post("/correlation", response_model=CorrelationOut)
async def correlation(
    body: CorrelationRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> CorrelationOut:
    if len(body.symbols) < 2:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "need at least 2 symbols")

    cutoff = datetime.now(UTC) - timedelta(days=body.days)
    rows = (
        await session.execute(
            text(
                "SELECT symbol, ts, close FROM ohlcv "
                " WHERE source = :s AND symbol = ANY(:syms) "
                "   AND timeframe = :tf AND ts >= :cutoff "
                " ORDER BY symbol, ts ASC",
            ),
            {
                "s": body.source,
                "syms": body.symbols,
                "tf": body.timeframe,
                "cutoff": cutoff,
            },
        )
    ).all()

    # Build aligned series: dict[ts -> dict[symbol -> close]]
    by_ts: dict[datetime, dict[str, float]] = defaultdict(dict)
    for sym, ts, close in rows:
        by_ts[ts][sym] = float(close)

    # Returns aligned by ts only when ALL requested symbols have a close.
    returns: dict[str, list[float]] = {s: [] for s in body.symbols}
    prev: dict[str, float] = {}
    for ts in sorted(by_ts):
        snap = by_ts[ts]
        if all(s in snap for s in body.symbols) and all(s in prev for s in body.symbols):
            for s in body.symbols:
                cur = snap[s]
                p = prev[s]
                if p > 0:
                    returns[s].append(math.log(cur / p))
        # Always update prev to current snap (even if not all present)
        for s, c in snap.items():
            prev[s] = c

    n = len(body.symbols)
    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]
    samples: list[list[int]] = [[0] * n for _ in range(n)]
    for i, si in enumerate(body.symbols):
        for j, sj in enumerate(body.symbols):
            if i == j:
                matrix[i][j] = 1.0
                samples[i][j] = len(returns[si])
                continue
            corr, k = _pearson(returns[si], returns[sj])
            matrix[i][j] = corr
            samples[i][j] = k

    return CorrelationOut(
        source=body.source,
        timeframe=body.timeframe,
        days=body.days,
        symbols=body.symbols,
        matrix=matrix,
        samples=samples,
        computed_at=datetime.now(UTC),
    )
