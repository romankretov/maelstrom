"""Funding-rate history fetcher.

Doesn't go through the MarketDataSource Protocol — that's tightly scoped
to OHLCV/trades. Instead, we open the same ccxt clients directly and call
`fetch_funding_rate_history`. Two sources only (binance, hyperliquid),
so the duplication is cheap.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import ccxt.pro as ccxtpro
import structlog

log = structlog.get_logger()


@dataclass(slots=True)
class FundingPoint:
    source: str
    symbol: str  # normalized "BTC-PERP"
    ts: datetime
    rate: float


def _normalize_base(raw: str) -> str:
    return raw.split("/", 1)[0]


def _ms(ts: datetime) -> int:
    return int(ts.timestamp() * 1000)


async def fetch_funding_history(
    source: str,
    symbol: str,
    since: datetime,
    until: datetime | None = None,
) -> list[FundingPoint]:
    """Fetch funding-rate history for one perp from `since` until `until` (now).

    Uses ccxt's `fetchFundingRateHistory` under the hood. Pagination via
    repeated calls — Binance caps at 1000 per call, HL similarly.
    """
    if source == "binance":
        client: Any = ccxtpro.binanceusdm({"enableRateLimit": True})
        base = symbol.removesuffix("-PERP")
        raw_symbol = f"{base}/USDT:USDT"
    elif source == "hyperliquid":
        client = ccxtpro.hyperliquid({"enableRateLimit": True})
        base = symbol.removesuffix("-PERP")
        raw_symbol = f"{base}/USDC:USDC"
    else:
        raise ValueError(f"funding history not supported for source={source}")

    out: list[FundingPoint] = []
    cursor_ms = _ms(since)
    until_ms = _ms(until) if until else None
    try:
        await client.load_markets()
        if raw_symbol not in client.markets:
            log.warning("funding.unknown_symbol", source=source, symbol=symbol, raw=raw_symbol)
            return out
        while True:
            chunk = await client.fetch_funding_rate_history(raw_symbol, since=cursor_ms, limit=1000)
            if not chunk:
                break
            for item in chunk:
                ts_ms = int(item.get("timestamp") or 0)
                rate = item.get("fundingRate")
                if ts_ms == 0 or rate is None:
                    continue
                if until_ms is not None and ts_ms >= until_ms:
                    break
                out.append(
                    FundingPoint(
                        source=source,
                        symbol=symbol,
                        ts=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                        rate=float(rate),
                    ),
                )
            last_ts = int(chunk[-1].get("timestamp") or 0)
            if last_ts <= cursor_ms:
                break
            cursor_ms = last_ts + 1
            if len(chunk) < 1000:
                break
            if until_ms is not None and cursor_ms >= until_ms:
                break
    finally:
        await client.close()
    return out
