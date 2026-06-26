from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .connectors import Bar, Instrument, get_source, list_sources
from .engine import run_backtest_run
from .funding import FundingPoint, fetch_funding_history
from .settings import get_settings

log = structlog.get_logger()


# ----------------------------------------------------------------- engine
# One engine per worker process. arq invokes tasks repeatedly — recreating
# the engine on every call kills throughput.

_engine = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _sm() -> async_sessionmaker[AsyncSession]:
    global _engine, _session_maker
    if _session_maker is None:
        _engine = create_async_engine(
            str(get_settings().database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_maker


# ----------------------------------------------------------------- heartbeat


async def heartbeat(ctx: dict[str, Any]) -> str:
    """Per-minute pulse, audit_log row + structured log."""
    async with _sm()() as session:
        await session.execute(
            text(
                "INSERT INTO audit_log (actor_kind, action, payload) "
                "VALUES ('worker', 'worker.heartbeat', CAST(:p AS json))",
            ),
            {"p": '{"ts": "' + datetime.now(UTC).isoformat() + '"}'},
        )
        await session.commit()
    log.info("worker.heartbeat")
    return "ok"


# ----------------------------------------------------------------- instruments


_UPSERT_INSTRUMENT_SQL = text(
    """
    INSERT INTO instruments (
        source, symbol, raw_symbol, base, quote, kind, active, meta, updated_at
    )
    VALUES (
        :source, :symbol, :raw_symbol, :base, :quote, :kind, :active, CAST(:meta AS jsonb), now()
    )
    ON CONFLICT (source, symbol) DO UPDATE SET
        raw_symbol = EXCLUDED.raw_symbol,
        base       = EXCLUDED.base,
        quote      = EXCLUDED.quote,
        kind       = EXCLUDED.kind,
        active     = EXCLUDED.active,
        meta       = EXCLUDED.meta,
        updated_at = now()
    """,
)


async def _upsert_instruments(session: AsyncSession, instruments: list[Instrument]) -> int:
    if not instruments:
        return 0
    import orjson

    payload = [
        {
            "source": i.source,
            "symbol": i.symbol,
            "raw_symbol": i.raw_symbol,
            "base": i.base,
            "quote": i.quote,
            "kind": i.kind,
            "active": i.active,
            "meta": orjson.dumps(i.meta).decode("utf-8"),
        }
        for i in instruments
    ]
    await session.execute(_UPSERT_INSTRUMENT_SQL, payload)
    await session.commit()
    return len(payload)


async def sync_instruments(ctx: dict[str, Any], source: str | None = None) -> dict[str, int]:
    """Refresh instruments catalog. Per-source if `source` is given, else all sources."""
    targets = [source] if source else list_sources()
    counts: dict[str, int] = {}
    for name in targets:
        try:
            src = get_source(name)
        except ValueError as e:
            log.warning("sync_instruments.unknown_source", source=name, error=str(e))
            continue
        try:
            instruments = await src.list_instruments()
            async with _sm()() as session:
                written = await _upsert_instruments(session, instruments)
            counts[name] = written
            log.info("sync_instruments.done", source=name, count=written)
        except Exception as e:
            log.exception("sync_instruments.failed", source=name, error=str(e))
            counts[name] = -1
        finally:
            await src.close()
    return counts


# ----------------------------------------------------------------- OHLCV backfill


_UPSERT_OHLCV_SQL = text(
    """
    INSERT INTO ohlcv (source, symbol, timeframe, ts, open, high, low, close, volume, trades_count)
    VALUES (:source, :symbol, :timeframe, :ts, :open, :high, :low, :close, :volume, :trades_count)
    ON CONFLICT (source, symbol, timeframe, ts) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low  = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume,
        trades_count = EXCLUDED.trades_count
    """,
)


async def _upsert_bars(session: AsyncSession, bars: list[Bar]) -> int:
    if not bars:
        return 0
    payload = [
        {
            "source": b.source,
            "symbol": b.symbol,
            "timeframe": b.timeframe,
            "ts": b.ts,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "trades_count": b.trades_count,
        }
        for b in bars
    ]
    await session.execute(_UPSERT_OHLCV_SQL, payload)
    await session.commit()
    return len(payload)


async def reconcile_positions(ctx: dict[str, Any]) -> dict[str, Any]:
    """For every active live (Hyperliquid) account, compare local positions
    table to the exchange. Log + return any mismatches. Phase 6 hooks this
    into Telegram/Discord alerts.

    Read-only: we never write the exchange state back into our DB here —
    that's the job of fills landing through the broker.
    """
    import ccxt.pro as ccxtpro

    from .crypto import decrypt_str

    summary: dict[str, Any] = {"checked": 0, "mismatches": []}
    async with _sm()() as session:
        accs = (
            await session.execute(
                text(
                    "SELECT id, kind, api_key_enc, meta "
                    "  FROM accounts "
                    " WHERE is_active = TRUE AND kind LIKE 'live_hl_%' "
                    "   AND api_key_enc IS NOT NULL",
                ),
            )
        ).all()
    for acc_id, kind, api_key_enc, meta in accs:
        wallet = (meta or {}).get("wallet_address")
        if not wallet or not api_key_enc:
            continue
        try:
            client = ccxtpro.hyperliquid(
                {
                    "walletAddress": wallet,
                    "privateKey": decrypt_str(bytes(api_key_enc)),
                    "options": {"defaultType": "swap"},
                },
            )
            if kind == "live_hl_testnet":
                # Same fix as the broker: `test: True` in the constructor
                # doesn't reliably flip ccxt's HL URLs to testnet; use
                # set_sandbox_mode explicitly so we don't hit mainnet
                # and get rate-limited.
                client.set_sandbox_mode(True)
            try:
                exch_positions = await client.fetch_positions()
            finally:
                await client.close()
        except Exception as e:
            log.warning("reconcile.fetch_failed", account=str(acc_id), error=str(e))
            continue

        # Build {symbol_normalized: qty_signed} from exchange.
        exch_map: dict[str, float] = {}
        for p in exch_positions:
            raw_sym = p.get("symbol") or ""
            base = raw_sym.split("/", 1)[0]
            sym = f"{base}-PERP"
            exch_map[sym] = float(p.get("contracts") or 0) * (
                1 if (p.get("side") or "long") == "long" else -1
            )

        async with _sm()() as session:
            local_rows = (
                await session.execute(
                    text("SELECT symbol, qty FROM positions WHERE account_id = :id"),
                    {"id": str(acc_id)},
                )
            ).all()
        local_map = {sym: float(qty) for sym, qty in local_rows}

        mism: list[dict[str, Any]] = []
        for sym in set(exch_map) | set(local_map):
            l_qty = local_map.get(sym, 0.0)
            e_qty = exch_map.get(sym, 0.0)
            if abs(l_qty - e_qty) > 1e-9:
                mism.append({"symbol": sym, "local": l_qty, "exchange": e_qty})
        summary["checked"] += 1
        if mism:
            summary["mismatches"].append({"account_id": str(acc_id), "diffs": mism})
            log.warning("reconcile.mismatch", account=str(acc_id), diffs=mism)
        else:
            log.info("reconcile.ok", account=str(acc_id))
    return summary


_UPSERT_FUNDING_SQL = text(
    """
    INSERT INTO funding_rates (source, symbol, ts, rate)
    VALUES (:source, :symbol, :ts, :rate)
    ON CONFLICT (source, symbol, ts) DO UPDATE SET rate = EXCLUDED.rate
    """,
)


_FUNDING_SOURCES = ("binance", "hyperliquid")


async def _upsert_funding(session: AsyncSession, points: list[FundingPoint]) -> int:
    if not points:
        return 0
    await session.execute(
        _UPSERT_FUNDING_SQL,
        [{"source": p.source, "symbol": p.symbol, "ts": p.ts, "rate": p.rate} for p in points],
    )
    await session.commit()
    return len(points)


async def sync_funding_rates(
    ctx: dict[str, Any],
    source: str | None = None,
    symbols: list[str] | None = None,
) -> dict[str, int]:
    """Refresh funding-rate history for active perps.

    Per source: take the latest stored ts and fetch forward. New symbols get
    backfilled 30 days. Capped at ~30 symbols per source per run so a fresh
    deploy doesn't hammer the exchange.
    """
    targets = [source] if source else list(_FUNDING_SOURCES)
    counts: dict[str, int] = {}
    for src_name in targets:
        if src_name not in _FUNDING_SOURCES:
            log.warning("funding.unsupported_source", source=src_name)
            continue
        target_symbols: list[str]
        if symbols:
            target_symbols = list(symbols)
        else:
            async with _sm()() as session:
                rows = (
                    await session.execute(
                        text(
                            "SELECT symbol FROM instruments "
                            " WHERE source = :s AND kind = 'perp' AND active = TRUE "
                            " ORDER BY symbol LIMIT 30",
                        ),
                        {"s": src_name},
                    )
                ).all()
            target_symbols = [r[0] for r in rows]
        written = 0
        for sym in target_symbols:
            async with _sm()() as session:
                latest_row = (
                    await session.execute(
                        text(
                            "SELECT MAX(ts) FROM funding_rates "
                            " WHERE source = :s AND symbol = :sym",
                        ),
                        {"s": src_name, "sym": sym},
                    )
                ).first()
            latest = latest_row[0] if latest_row else None
            since = (latest or (datetime.now(UTC) - timedelta(days=30))) + timedelta(seconds=1)
            if since >= datetime.now(UTC):
                continue
            try:
                points = await fetch_funding_history(src_name, sym, since)
            except Exception as e:
                log.warning(
                    "funding.fetch_failed",
                    source=src_name,
                    symbol=sym,
                    error=str(e),
                )
                continue
            async with _sm()() as session:
                written += await _upsert_funding(session, points)
        counts[src_name] = written
        log.info("funding.sync.done", source=src_name, rows=written)
    return counts


# ----------------------------------------------------------------- data keeper
#
# Rolling-window history maintenance. For every active perp instrument
# this cron checks the newest stored bar per (source, symbol, tf) and
# pulls in whatever's missing up to "now". Once a (symbol, tf) has been
# bootstrapped, the daily run is small (just the trailing 24h of bars).
#
# Sized for ~150 HL perps + ~600 binance perps at default depths; total
# bytes added per run is well under 100 MB even on a cold start.

_KEEPER_TARGETS: dict[str, list[tuple[str, int]]] = {
    "hyperliquid": [
        ("1h", 365),  # 1 year of 1h bars
        ("5m", 30),  # 30 days of 5m bars
        ("1m", 7),  # 7 days of 1m bars
    ],
    "binance": [
        ("1h", 365),
        ("5m", 30),
    ],
}


async def _latest_bar_ts(
    session: AsyncSession,
    source: str,
    symbol: str,
    timeframe: str,
) -> datetime | None:
    row = (
        await session.execute(
            text(
                "SELECT MAX(ts) FROM ohlcv "
                " WHERE source = :s AND symbol = :sym AND timeframe = :tf",
            ),
            {"s": source, "sym": symbol, "tf": timeframe},
        )
    ).first()
    return row[0] if row and row[0] else None


_TIMEFRAME_TO_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


async def keep_market_data_fresh(
    ctx: dict[str, Any],
    source: str | None = None,
) -> dict[str, Any]:
    """Daily cron: ensure ohlcv has rolling history per _KEEPER_TARGETS.

    For each (source, symbol, timeframe) target:
      * if we have no rows: fetch the full target window in one go
      * if we have rows: fetch from `latest + 1 tf` to now

    Calls fetch_ohlcv on the connector directly (no backfill_jobs row);
    the keeper is a background utility, not user-initiated.
    """
    now = datetime.now(UTC)
    targets = [source] if source else list(_KEEPER_TARGETS.keys())
    summary: dict[str, Any] = {"sources": {}}
    for src_name in targets:
        if src_name not in _KEEPER_TARGETS:
            continue
        async with _sm()() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT symbol FROM instruments "
                        " WHERE source = :s AND kind = 'perp' AND active = TRUE "
                        " ORDER BY symbol",
                    ),
                    {"s": src_name},
                )
            ).all()
        symbols = [r[0] for r in rows]
        try:
            src = get_source(src_name)
        except ValueError:
            log.warning("keeper.unknown_source", source=src_name)
            continue

        per_tf_written: dict[str, int] = {}
        try:
            for tf, days in _KEEPER_TARGETS[src_name]:
                tf_seconds = _TIMEFRAME_TO_SECONDS.get(tf, 60)
                window_start = now - timedelta(days=days)
                tf_total = 0
                # Tracks how many sequential 429s we hit at the keeper level.
                # The connector already retries+backs off internally, but if
                # we're seeing repeated rate limits after that, the only
                # right move is to abandon this run — slamming harder will
                # just delay the live broker on the same IP.
                consecutive_rate_limited = 0
                for sym in symbols:
                    async with _sm()() as session:
                        latest = await _latest_bar_ts(session, src_name, sym, tf)
                    since = (
                        max(latest + timedelta(seconds=tf_seconds), window_start)
                        if latest
                        else window_start
                    )
                    if since >= now:
                        continue
                    try:
                        bars = await src.fetch_ohlcv(sym, tf, since, now)
                        consecutive_rate_limited = 0
                    except Exception as e:
                        msg = str(e)
                        log.warning(
                            "keeper.fetch_failed",
                            source=src_name,
                            symbol=sym,
                            tf=tf,
                            error=msg,
                        )
                        if "429" in msg:
                            consecutive_rate_limited += 1
                            if consecutive_rate_limited >= 5:
                                log.warning(
                                    "keeper.rate_limited_abort",
                                    source=src_name,
                                    tf=tf,
                                    symbols_processed=symbols.index(sym),
                                    symbols_total=len(symbols),
                                )
                                break
                        continue
                    if not bars:
                        continue
                    async with _sm()() as session:
                        written = await _upsert_bars(session, bars)
                    tf_total += written
                per_tf_written[tf] = tf_total
                log.info(
                    "keeper.tf.done",
                    source=src_name,
                    tf=tf,
                    bars_written=tf_total,
                    symbols=len(symbols),
                )
        finally:
            await src.close()
        summary["sources"][src_name] = {
            "symbols": len(symbols),
            "written_by_tf": per_tf_written,
        }
    log.info("keeper.done", summary=summary)
    return summary


async def run_backtest(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Execute a backtest_runs row to completion."""
    log.info("backtest.task.start", run_id=run_id)
    async with _sm()() as session:
        result = await run_backtest_run(session, run_id)
    log.info("backtest.task.done", run_id=run_id, status=result.get("status"))
    return result


async def close_position(
    ctx: dict[str, Any],
    account_id: str,
    symbol: str,
) -> dict[str, Any]:
    """Submit a market-close order outside any strategy.

    Reads the current position, picks the broker for the account kind,
    and submits an opposite-side market order sized to flatten the
    position. Routes through the same Broker abstraction as live
    strategies, so paper accounts simulate the fill and HL accounts
    hit the real exchange.
    """
    from .broker import HyperliquidBroker, OrderIntent, PaperBroker

    async with _sm()() as session:
        acc_row = (
            await session.execute(
                text(
                    "SELECT id, kind, source FROM accounts WHERE id = :id",
                ),
                {"id": account_id},
            )
        ).first()
        if acc_row is None:
            return {"status": "error", "error": "account not found"}
        pos_row = (
            await session.execute(
                text(
                    "SELECT qty, last_price FROM positions "
                    " WHERE account_id = :a AND symbol = :sym",
                ),
                {"a": account_id, "sym": symbol},
            )
        ).first()
    if pos_row is None or float(pos_row[0]) == 0:
        return {"status": "noop", "reason": "no open position"}

    qty = float(pos_row[0])
    last_price = float(pos_row[1] or 0)
    side = "sell" if qty > 0 else "buy"
    abs_qty = abs(qty)

    sm = _sm()
    kind = acc_row[1]
    broker: HyperliquidBroker | PaperBroker
    if kind.startswith("live_hl_"):
        broker = HyperliquidBroker(sm, account_id=account_id)
    else:
        broker = PaperBroker(sm)

    source = acc_row[2] or ("hyperliquid" if kind.startswith("live_hl_") else "binance")
    intent = OrderIntent(
        account_id=account_id,
        live_strategy_id=None,
        source=source,
        symbol=symbol,
        side=side,
        qty=abs_qty,
        reason="manual close",
        idempotency_key=f"manual-close:{account_id}:{symbol}:{datetime.now(UTC).timestamp():.6f}",
    )
    try:
        result = await broker.submit(intent, last_price or 0.0)
    finally:
        if hasattr(broker, "close"):
            await broker.close()
    log.info(
        "manual.close.done",
        account_id=account_id,
        symbol=symbol,
        side=side,
        qty=abs_qty,
        status=result.status,
    )
    return {
        "status": result.status,
        "filled_qty": result.filled_qty,
        "avg_fill_price": result.avg_fill_price,
        "pnl": result.pnl,
        "error": result.error,
    }


async def dry_run_strategy(
    ctx: dict[str, Any],
    code: str,
    source: str = "hyperliquid",
    symbol: str = "BTC-PERP",
    timeframe: str = "1h",
    hours: int = 24,
) -> dict[str, Any]:
    """Compile + execute a strategy against recently-stored OHLCV without
    persisting fills, recording the run, or hitting the exchange.

    Returns a small diagnostic payload the editor can render inline. Hard
    cap: 5 seconds wall time, ~500 bars max.
    """
    from .engine.runner import BacktestEngine, _compile_strategy

    cutoff = datetime.now(UTC) - timedelta(hours=max(1, min(hours, 168)))
    async with _sm()() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT ts, open, high, low, close, volume, trades_count "
                    "  FROM ohlcv "
                    " WHERE source = :s AND symbol = :sym AND timeframe = :tf "
                    "   AND ts >= :cutoff "
                    " ORDER BY ts ASC LIMIT 500",
                ),
                {"s": source, "sym": symbol, "tf": timeframe, "cutoff": cutoff},
            )
        ).all()

    if not rows:
        return {
            "compiled": False,
            "on_init_ran": False,
            "bars_fed": 0,
            "orders_queued": 0,
            "fills": 0,
            "rejects": 0,
            "sample_orders": [],
            "last_error": (
                f"No {timeframe} bars stored for {source}:{symbol} in the last {hours}h. "
                "Try a different symbol / timeframe, or run keep_market_data_fresh first."
            ),
        }

    bars = [
        Bar(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            ts=r[0],
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=float(r[5]),
            trades_count=r[6],
        )
        for r in rows
    ]
    # BacktestEngine expects its own EngineBar shape; the connector Bar's
    # shape happens to be identical for the fields it uses, so reuse.
    from .engine.types import EngineBar

    engine_bars = [
        EngineBar(
            source=b.source,
            symbol=b.symbol,
            ts=b.ts,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )
        for b in bars
    ]

    # Compile + smoke-run.
    try:
        cls = _compile_strategy(code)
    except Exception as e:
        return {
            "compiled": False,
            "on_init_ran": False,
            "bars_fed": 0,
            "orders_queued": 0,
            "fills": 0,
            "rejects": 0,
            "sample_orders": [],
            "last_error": f"{type(e).__name__}: {e}",
        }

    engine = BacktestEngine(initial_capital=10_000)
    strategy = cls()
    strategy._ctx = engine
    strategy._params = {}

    on_init_ran = False
    try:
        strategy.on_init()
        on_init_ran = True
    except Exception as e:
        return {
            "compiled": True,
            "on_init_ran": False,
            "bars_fed": 0,
            "orders_queued": 0,
            "fills": 0,
            "rejects": 0,
            "sample_orders": [],
            "last_error": f"on_init raised: {type(e).__name__}: {e}",
        }

    last_error: str | None = None
    orders_before = len(engine.fills)
    for b in engine_bars:
        engine._current_ts = b.ts
        engine.last_prices[b.symbol] = b.close
        engine.history_per_symbol[b.symbol].append(b)
        try:
            strategy.on_bar(b)
        except Exception as e:
            last_error = f"on_bar at {b.ts.isoformat()} raised: {type(e).__name__}: {e}"
            break

    fills = engine.fills
    sample = [
        {
            "ts": f.ts.isoformat(),
            "symbol": f.symbol,
            "side": f.side,
            "qty": f.qty,
            "price": f.price,
            "pnl": f.pnl,
            "reason": f.reason,
        }
        for f in fills[:5]
    ]
    return {
        "compiled": True,
        "on_init_ran": on_init_ran,
        "bars_fed": len(engine_bars),
        "orders_queued": len(fills) - orders_before,
        "fills": sum(1 for f in fills if f.qty > 0),
        "rejects": 0,
        "sample_orders": sample,
        "last_error": last_error,
    }


async def backfill_ohlcv(ctx: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Run a backfill_jobs row to completion."""
    log.info("backfill.start", job_id=job_id)
    async with _sm()() as session:
        row = (
            await session.execute(
                text(
                    "SELECT source, symbol, timeframe, range_start, range_end "
                    "FROM backfill_jobs WHERE id = :id",
                ),
                {"id": job_id},
            )
        ).first()
        if row is None:
            log.error("backfill.not_found", job_id=job_id)
            return {"status": "not_found"}
        await session.execute(
            text("UPDATE backfill_jobs SET status='running', updated_at=now() WHERE id=:id"),
            {"id": job_id},
        )
        await session.commit()

    source_name, symbol, timeframe, since, until = row
    total = 0
    src = get_source(source_name)
    try:
        bars = await src.fetch_ohlcv(symbol, timeframe, since, until)
        async with _sm()() as session:
            total = await _upsert_bars(session, bars)
            await session.execute(
                text(
                    "UPDATE backfill_jobs SET status='done', bars_written=:n, updated_at=now() "
                    "WHERE id=:id",
                ),
                {"id": job_id, "n": total},
            )
            await session.commit()
        log.info("backfill.done", job_id=job_id, bars=total)
        return {"status": "done", "bars": total}
    except Exception as e:
        log.exception("backfill.failed", job_id=job_id, error=str(e))
        async with _sm()() as session:
            await session.execute(
                text(
                    "UPDATE backfill_jobs SET status='failed', error=:err, updated_at=now() "
                    "WHERE id=:id",
                ),
                {"id": job_id, "err": str(e)[:2000]},
            )
            await session.commit()
        return {"status": "failed", "error": str(e)}
    finally:
        await src.close()
