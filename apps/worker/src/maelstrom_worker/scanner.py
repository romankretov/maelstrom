"""Opportunity scanner: cron task that snapshots top market movers, asks an
LLM for ranked trade ideas, and persists them into the `signals` table.

Runs every 30 min by default. Costs a few cents per call on Sonnet 4.6.
Skips silently if no provider key is configured (so a fresh deploy doesn't
spam errors)."""

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import orjson
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from .llm import complete

log = structlog.get_logger()


SCANNER_NAME = "movers_v1"
SIGNAL_TTL = timedelta(hours=6)


SCANNER_SYSTEM = """\
You are a crypto perp trading analyst. Given a snapshot of the top market
movers over the last 24 hours, identify 3 to 5 high-conviction trade ideas
for the next 4 to 24 hours.

Reasoning style: momentum continuation OR mean-reversion (call out which),
weighted by volume relative to recent average. Be skeptical of moves on
thin volume.

Output rules — STRICT:
- Output ONLY a JSON array. No markdown fences. No prose before or after.
- Each element MUST have these exact keys:
    "symbol":     string, e.g. "BTC-PERP"  (verbatim from the snapshot)
    "source":     string, "binance" or "hyperliquid" (from the snapshot)
    "direction":  string, "long" or "short"
    "score":      number, -100 to 100 (signed conviction)
    "confidence": number, 0 to 1
    "horizon":    string, "intraday" | "swing" | "position"
    "rationale":  string, one sentence (<= 150 chars)

If nothing in the snapshot is compelling, output `[]`. Don't fabricate.
"""


_TOP_MOVERS_SQL = text(
    """
    WITH latest AS (
        SELECT source, symbol, ts, close, volume,
               ROW_NUMBER() OVER (PARTITION BY source, symbol ORDER BY ts DESC) AS rn
          FROM ohlcv
         WHERE timeframe = '1h'
           AND ts >= now() - INTERVAL '25 hours'
    ),
    pivot AS (
        SELECT
            source, symbol,
            MAX(close)  FILTER (WHERE rn = 1)  AS close_now,
            MAX(close)  FILTER (WHERE rn = 24) AS close_24h,
            SUM(volume) FILTER (WHERE rn <= 24) AS vol_24h
          FROM latest
         WHERE rn <= 24
         GROUP BY source, symbol
    )
    SELECT source, symbol, close_now, close_24h,
           (close_now - close_24h) / close_24h AS pct_change,
           vol_24h
      FROM pivot
     WHERE close_24h > 0 AND close_now IS NOT NULL
     ORDER BY abs((close_now - close_24h) / close_24h) DESC
     LIMIT 20
    """,
)


async def _build_snapshot(sm: async_sessionmaker) -> tuple[list[dict[str, Any]], str]:
    """Return (rows, formatted_markdown_table)."""
    async with sm() as session:
        rows = (await session.execute(_TOP_MOVERS_SQL)).all()
    if not rows:
        return [], ""

    out_rows: list[dict[str, Any]] = []
    lines = ["| source | symbol | last | 24h % | 24h vol |", "|---|---|---|---|---|"]
    for source, symbol, close_now, close_24h, pct, vol in rows:
        d = {
            "source": source,
            "symbol": symbol,
            "close": float(close_now),
            "pct_24h": float(pct),
            "vol_24h": float(vol or 0),
            "close_24h_ago": float(close_24h),
        }
        out_rows.append(d)
        lines.append(
            f"| {source} | {symbol} | {d['close']:.4g} | "
            f"{d['pct_24h'] * 100:+.2f}% | {d['vol_24h']:,.0f} |",
        )
    return out_rows, "\n".join(lines)


_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)```\s*$", re.IGNORECASE)


def _parse_signals(raw: str) -> list[dict[str, Any]]:
    text_raw = raw.strip()
    m = _FENCE_RE.match(text_raw)
    if m:
        text_raw = m.group(1).strip()
    try:
        data = json.loads(text_raw)
    except json.JSONDecodeError as e:
        log.warning("scanner.parse_failed", error=str(e), preview=text_raw[:200])
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        direction = item.get("direction")
        if not symbol or direction not in ("long", "short", "neutral"):
            continue
        try:
            score = float(item.get("score") or 0)
            conf = item.get("confidence")
            conf_v = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "source": str(item.get("source") or "binance"),
                "symbol": str(symbol),
                "direction": str(direction),
                "score": score,
                "confidence": conf_v,
                "horizon": str(item.get("horizon")) if item.get("horizon") else None,
                "rationale": str(item.get("rationale") or "")[:1000],
            },
        )
    return out


_INSERT_SIGNAL_SQL = text(
    """
    INSERT INTO signals
      (scanner, source, symbol, direction, score, confidence, horizon,
       rationale, context, llm_call_id, expires_at)
    VALUES
      (:scanner, :source, :symbol, :direction, :score, :confidence, :horizon,
       :rationale, CAST(:context AS jsonb), :llm_call_id, :expires_at)
    """,
)


async def scan_opportunities(ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron entry. Skipped silently if no anthropic key is configured."""
    from .tasks import _sm  # reuse the cached session maker

    sm = _sm()
    rows, table = await _build_snapshot(sm)
    if not rows:
        log.info("scanner.no_data", reason="no 1h ohlcv in last 25h")
        return {"status": "skipped", "reason": "no data"}

    try:
        result = await complete(
            sm,
            provider="anthropic",
            purpose="scan_opportunities",
            system=SCANNER_SYSTEM,
            user_message=(
                "Top movers in the last 24h (1h-bar derived):\n\n"
                + table
                + "\n\nReturn the JSON array per the system instructions."
            ),
            temperature=0.5,
            max_tokens=2048,
        )
    except RuntimeError as e:
        # No key, disabled, etc — skip cleanly.
        log.info("scanner.skipped", reason=str(e))
        return {"status": "skipped", "reason": str(e)}

    signals = _parse_signals(result.text)
    if not signals:
        log.info("scanner.no_signals", call_id=result.call_id)
        return {"status": "ok", "signals": 0, "call_id": result.call_id}

    expires = datetime.now(UTC) + SIGNAL_TTL
    async with sm() as session:
        await session.execute(
            _INSERT_SIGNAL_SQL,
            [
                {
                    "scanner": SCANNER_NAME,
                    "source": s["source"],
                    "symbol": s["symbol"],
                    "direction": s["direction"],
                    "score": s["score"],
                    "confidence": s["confidence"],
                    "horizon": s["horizon"],
                    "rationale": s["rationale"],
                    "context": orjson.dumps(
                        {
                            "snapshot_rows": rows[:5],
                            "model": result.model,
                        },
                    ).decode(),
                    "llm_call_id": result.call_id,
                    "expires_at": expires,
                }
                for s in signals
            ],
        )
        await session.commit()
    log.info("scanner.persisted", count=len(signals), call_id=result.call_id)

    # Notify subscribers about the highest-conviction signal in this batch.
    top = max(signals, key=lambda s: abs(float(s["score"])), default=None)
    if top is not None and ctx.get("redis") is not None:
        from .notify import notify_all

        body_text = (
            f"📡 *Top signal* {top['symbol']} *{top['direction'].upper()}*  "
            f"score={top['score']:+.0f} conf={top['confidence']}  "
            f"horizon={top['horizon']}\n"
            f"_{top['rationale']}_"
        )
        try:
            await notify_all(
                sm,
                ctx["redis"],
                "signal_top",
                {
                    "text": body_text,
                    "symbol": top["symbol"],
                    "direction": top["direction"],
                    "score": top["score"],
                },
            )
        except Exception as e:
            log.warning("scanner.notify_failed", error=str(e))

    return {"status": "ok", "signals": len(signals), "call_id": result.call_id}
