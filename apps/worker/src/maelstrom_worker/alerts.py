"""Alerts evaluator.

Cron tick every minute. For each enabled alert past its cooldown,
re-evaluate against latest market data; if condition holds, fire the
matching notification event ("price_alert") and stamp last_triggered_at.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

log = structlog.get_logger()


async def _latest_close(
    sm: async_sessionmaker,
    source: str,
    symbol: str,
) -> float | None:
    """Newest 1m bar close, or None if streams haven't populated."""
    async with sm() as session:
        row = (
            await session.execute(
                text(
                    "SELECT close FROM ohlcv "
                    " WHERE source = :s AND symbol = :sym AND timeframe = '1m' "
                    " ORDER BY ts DESC LIMIT 1",
                ),
                {"s": source, "sym": symbol},
            )
        ).first()
    return float(row[0]) if row else None


async def _change_24h(
    sm: async_sessionmaker,
    source: str,
    symbol: str,
) -> float | None:
    async with sm() as session:
        row = (
            await session.execute(
                text(
                    "SELECT "
                    "  (array_agg(close ORDER BY ts DESC))[1] AS now_close, "
                    "  (array_agg(close ORDER BY ts ASC))[1]  AS old_close "
                    "  FROM ohlcv "
                    " WHERE source = :s AND symbol = :sym AND timeframe = '1h' "
                    "   AND ts >= now() - INTERVAL '25 hours'",
                ),
                {"s": source, "sym": symbol},
            )
        ).first()
    if not row or row[0] is None or row[1] is None or float(row[1]) == 0:
        return None
    return (float(row[0]) - float(row[1])) / float(row[1])


async def _latest_funding(
    sm: async_sessionmaker,
    source: str,
    symbol: str,
) -> float | None:
    async with sm() as session:
        row = (
            await session.execute(
                text(
                    "SELECT rate FROM funding_rates "
                    " WHERE source = :s AND symbol = :sym "
                    " ORDER BY ts DESC LIMIT 1",
                ),
                {"s": source, "sym": symbol},
            )
        ).first()
    return float(row[0]) if row else None


# (current_value, condition_met) for the row
async def _evaluate(
    sm: async_sessionmaker,
    source: str,
    symbol: str,
    condition: str,
    threshold: float,
) -> tuple[float | None, bool]:
    if condition in ("price_above", "price_below"):
        value = await _latest_close(sm, source, symbol)
    elif condition in ("change_24h_above", "change_24h_below"):
        value = await _change_24h(sm, source, symbol)
    elif condition in ("funding_above", "funding_below"):
        value = await _latest_funding(sm, source, symbol)
    else:
        log.warning("alerts.unknown_condition", condition=condition)
        return None, False

    if value is None:
        return None, False

    if condition.endswith("_above"):
        return value, value > threshold
    return value, value < threshold


def _format_message(
    label: str,
    source: str,
    symbol: str,
    condition: str,
    threshold: float,
    value: float,
) -> str:
    if condition.startswith("price_"):
        return (
            f"🔔 *{label}*  {source}:{symbol}\n"
            f"price `{value:,.4g}` crossed threshold `{threshold:,.4g}` ({condition})"
        )
    if condition.startswith("change_24h_"):
        return (
            f"🔔 *{label}*  {source}:{symbol}\n"
            f"24h change `{value * 100:+.2f}%` crossed `{threshold * 100:+.2f}%` ({condition})"
        )
    return (
        f"🔔 *{label}*  {source}:{symbol}\n"
        f"funding `{value * 100:+.4f}%` crossed `{threshold * 100:+.4f}%` ({condition})"
    )


async def evaluate_alerts(ctx: dict[str, Any]) -> dict[str, int]:
    """Cron: walk every enabled alert past cooldown; fire if triggered."""
    from .notify import notify_all
    from .tasks import _sm

    sm = _sm()
    now = datetime.now(UTC)

    async with sm() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, user_id, label, source, symbol, condition, threshold, "
                    "       cooldown_minutes, last_triggered_at "
                    "  FROM alerts "
                    " WHERE enabled = TRUE",
                ),
            )
        ).all()

    fired = 0
    skipped_cooldown = 0
    pool = ctx.get("redis")
    for r in rows:
        (
            alert_id,
            user_id,
            label,
            source,
            symbol,
            condition,
            threshold,
            cooldown_minutes,
            last_triggered_at,
        ) = r
        if last_triggered_at and now - last_triggered_at < timedelta(minutes=cooldown_minutes):
            skipped_cooldown += 1
            continue
        try:
            value, met = await _evaluate(sm, source, symbol, condition, float(threshold))
        except Exception as e:
            log.warning("alerts.eval_failed", alert_id=str(alert_id), error=str(e))
            continue
        if not met or value is None:
            continue

        message = _format_message(label, source, symbol, condition, float(threshold), value)
        if pool is not None:
            try:
                await notify_all(
                    sm,
                    pool,
                    "price_alert",
                    {
                        "text": message,
                        "alert_id": str(alert_id),
                        "source": source,
                        "symbol": symbol,
                        "condition": condition,
                        "threshold": float(threshold),
                        "value": value,
                    },
                    user_id=str(user_id),
                )
            except Exception as e:
                log.warning("alerts.notify_failed", alert_id=str(alert_id), error=str(e))

        async with sm() as session:
            await session.execute(
                text(
                    "UPDATE alerts SET "
                    "  last_triggered_at = now(), "
                    "  last_value = :v, "
                    "  trigger_count = trigger_count + 1 "
                    "WHERE id = :id",
                ),
                {"v": value, "id": alert_id},
            )
            await session.commit()
        fired += 1
        log.info(
            "alerts.fired",
            alert_id=str(alert_id),
            source=source,
            symbol=symbol,
            condition=condition,
            value=value,
        )

    log.info(
        "alerts.tick",
        total=len(rows),
        fired=fired,
        skipped_cooldown=skipped_cooldown,
    )
    return {"checked": len(rows), "fired": fired, "skipped_cooldown": skipped_cooldown}
