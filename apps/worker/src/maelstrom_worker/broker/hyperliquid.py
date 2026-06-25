"""HyperliquidBroker — submits real orders to Hyperliquid (testnet or mainnet
depending on account.kind). NB: this module is *not* yet exercised end-to-end
on testnet; see docs/test-backlog.md.

Order flow (market orders only for v1):
    1. RiskEngine pre-check.
    2. Resolve raw symbol via ccxt.pro markets (e.g. BTC-PERP -> BTC/USDC:USDC).
    3. Submit order via ccxt.pro.create_order(type='market', amount=qty, side=...).
    4. Persist `orders` row as `filled` with the avg fill from the exchange
       response. (Hyperliquid market orders typically fill in a single transaction.)
    5. Insert `fills` row + UPSERT `positions`.

If we get any non-fill response (rejected, error) we record a `rejected` order
with the error string. Reconciliation (see worker/tasks.reconcile_positions)
catches any drift over time.
"""

from datetime import UTC, datetime
from typing import Any

import ccxt.pro as ccxtpro
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from maelstrom_worker.crypto import decrypt_str
from maelstrom_worker.risk import RiskEngine

from .base import Broker, OrderIntent, OrderResult
from .paper import _INSERT_FILL_SQL, _MARK_SQL, _UPSERT_POSITION_SQL

log = structlog.get_logger()


_LOAD_ACCOUNT_SQL = text(
    """
    SELECT api_key_enc, meta, kind, killed
      FROM accounts WHERE id = :id
    """,
)


_INSERT_FILLED_ORDER_SQL = text(
    """
    INSERT INTO orders
      (account_id, live_strategy_id, source, symbol, side, qty, order_type,
       status, filled_qty, avg_fill_price, reason, idempotency_key,
       exchange_order_id, submitted_at, completed_at)
    VALUES
      (:account_id, :live_strategy_id, :source, :symbol, :side, :qty, :order_type,
       'filled', :filled_qty, :avg_fill_price, :reason, :idempotency_key,
       :exchange_order_id, now(), now())
    RETURNING id
    """,
)


_INSERT_REJECTED_ORDER_SQL = text(
    """
    INSERT INTO orders
      (account_id, live_strategy_id, source, symbol, side, qty, order_type,
       status, error, reason, idempotency_key, completed_at)
    VALUES
      (:account_id, :live_strategy_id, :source, :symbol, :side, :qty, :order_type,
       'rejected', :err, :reason, :idempotency_key, now())
    RETURNING id
    """,
)


class HyperliquidBroker(Broker):
    """Live broker for Hyperliquid perps. Testnet vs mainnet decided by the
    bound account's `kind` (live_hl_testnet vs live_hl_main)."""

    def __init__(
        self,
        session_maker: async_sessionmaker,
        account_id: str,
        risk_engine: RiskEngine | None = None,
    ) -> None:
        self.sm = session_maker
        self.account_id = account_id
        self.risk = risk_engine or RiskEngine()
        self._client: ccxtpro.hyperliquid | None = None
        self._raw_by_symbol: dict[str, str] = {}

    async def _client_or_die(self) -> ccxtpro.hyperliquid:
        if self._client is not None:
            return self._client
        async with self.sm() as session:
            row = (await session.execute(_LOAD_ACCOUNT_SQL, {"id": self.account_id})).first()
        if row is None:
            raise RuntimeError("account not found")
        api_key_enc, meta, kind, killed = row
        if killed:
            raise RuntimeError("account killed")
        if not api_key_enc:
            raise RuntimeError("account has no credentials")
        wallet = (meta or {}).get("wallet_address")
        if not wallet:
            raise RuntimeError("missing wallet_address in account.meta")
        private_key = decrypt_str(bytes(api_key_enc))
        config: dict[str, Any] = {
            "walletAddress": wallet,
            "privateKey": private_key,
            "options": {
                "defaultType": "swap",
                # HL ccxt requires a price for market orders to cap slippage.
                # 5% is the ccxt default; we pass last_price explicitly on
                # every submit too, so this is just a safety net.
                "defaultSlippage": 0.05,
            },
        }
        self._client = ccxtpro.hyperliquid(config)
        if kind == "live_hl_testnet":
            # `test: True` in the constructor doesn't reliably flip ccxt's
            # HL URLs to testnet; using set_sandbox_mode is the canonical
            # way and updates both REST and WS endpoints. Without this we
            # were signing testnet agents but submitting to mainnet, which
            # rejected with "User or API Wallet ... does not exist".
            self._client.set_sandbox_mode(True)
        log.info(
            "hl.client.init",
            account=self.account_id,
            kind=kind,
            wallet=wallet[:6] + "…" + wallet[-4:],
            api_url=str(self._client.urls.get("api", "")),
        )
        return self._client

    async def _resolve_raw(self, symbol: str) -> str:
        if symbol in self._raw_by_symbol:
            return self._raw_by_symbol[symbol]
        client = await self._client_or_die()
        if not client.markets:
            await client.load_markets()
        base = symbol.removesuffix("-PERP")
        raw = f"{base}/USDC:USDC"
        if raw not in client.markets:
            raise RuntimeError(f"unknown Hyperliquid perp symbol: {symbol}")
        self._raw_by_symbol[symbol] = raw
        return raw

    async def submit(self, intent: OrderIntent, last_price: float) -> OrderResult:
        ts = datetime.now(UTC)

        risk = await self.risk.check(self.sm, intent, last_price)
        if not risk.ok:
            return await self._reject(intent, risk.reason or "risk rejected", ts)

        qty = intent.qty
        if qty is None and intent.notional is not None and last_price > 0:
            qty = float(intent.notional) / float(last_price)
        if qty is None or qty <= 0 or last_price <= 0:
            return await self._reject(intent, "invalid qty/price", ts)

        try:
            client = await self._client_or_die()
            raw = await self._resolve_raw(intent.symbol)
            # HL's market-order path uses `price` to compute the max
            # slippage bound (price * (1 ± defaultSlippage)). Pass the
            # latest mark so it sizes the slippage band correctly.
            order = await client.create_order(
                symbol=raw,
                type="market",
                side=intent.side,
                amount=qty,
                price=last_price,
            )
        except Exception as e:
            return await self._reject(intent, str(e)[:500], ts)

        # ccxt normalizes to: average (fill price), filled (qty), id (exchange id)
        avg_price = float(order.get("average") or order.get("price") or last_price)
        filled_qty = float(order.get("filled") or qty)
        exch_id = str(order.get("id") or "")
        fee_info = order.get("fee") or {}
        fee = float(fee_info.get("cost") or 0)

        # PnL calc — use existing helper logic by querying position then math.
        async with self.sm() as session:
            cur = (
                await session.execute(
                    text(
                        "SELECT qty, avg_price FROM positions "
                        " WHERE account_id = :a AND symbol = :s"
                    ),
                    {"a": intent.account_id, "s": intent.symbol},
                )
            ).first()
            old_qty = float(cur[0]) if cur else 0.0
            old_avg = float(cur[1]) if cur else 0.0
            signed = filled_qty if intent.side == "buy" else -filled_qty
            new_qty = old_qty + signed
            pnl = 0.0
            if (old_qty > 0 > signed) or (old_qty < 0 < signed):
                closing = min(abs(signed), abs(old_qty))
                pnl = (
                    (avg_price - old_avg) * closing
                    if old_qty > 0
                    else (old_avg - avg_price) * closing
                )
            if new_qty == 0:
                new_avg = 0.0
            elif (old_qty >= 0 and new_qty > old_qty) or (old_qty <= 0 and new_qty < old_qty):
                new_avg = (old_avg * old_qty + avg_price * signed) / new_qty
            else:
                new_avg = old_avg

            order_id = (
                await session.execute(
                    _INSERT_FILLED_ORDER_SQL,
                    {
                        "account_id": intent.account_id,
                        "live_strategy_id": intent.live_strategy_id,
                        "source": intent.source,
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "qty": qty,
                        "order_type": intent.order_type,
                        "filled_qty": filled_qty,
                        "avg_fill_price": avg_price,
                        "reason": intent.reason,
                        "idempotency_key": intent.idempotency_key,
                        "exchange_order_id": exch_id or None,
                    },
                )
            ).scalar_one()

            await session.execute(
                _INSERT_FILL_SQL,
                {
                    "order_id": order_id,
                    "account_id": intent.account_id,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "qty": filled_qty,
                    "price": avg_price,
                    "fee": fee,
                    "pnl": pnl,
                    "ts": ts,
                },
            )
            await session.execute(
                _UPSERT_POSITION_SQL,
                {
                    "account_id": intent.account_id,
                    "symbol": intent.symbol,
                    "qty": new_qty,
                    "avg_price": new_avg,
                    "realized_pnl": pnl,
                    "last_price": avg_price,
                },
            )
            await session.commit()

        log.info(
            "hl.fill",
            symbol=intent.symbol,
            side=intent.side,
            qty=filled_qty,
            price=avg_price,
            exch_id=exch_id,
            pnl=pnl,
        )
        return OrderResult(
            order_id=str(order_id),
            status="filled",
            filled_qty=filled_qty,
            avg_fill_price=avg_price,
            fee=fee,
            pnl=pnl,
            ts=ts,
        )

    async def update_mark(self, account_id: str, symbol: str, last_price: float) -> None:
        async with self.sm() as session:
            await session.execute(
                _MARK_SQL,
                {"account_id": account_id, "symbol": symbol, "price": last_price},
            )
            await session.commit()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def _reject(self, intent: OrderIntent, error: str, ts: datetime) -> OrderResult:
        async with self.sm() as session:
            row = (
                await session.execute(
                    _INSERT_REJECTED_ORDER_SQL,
                    {
                        "account_id": intent.account_id,
                        "live_strategy_id": intent.live_strategy_id,
                        "source": intent.source,
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "qty": intent.qty or 0,
                        "order_type": intent.order_type,
                        "err": error,
                        "reason": intent.reason,
                        "idempotency_key": intent.idempotency_key,
                    },
                )
            ).scalar_one()
            await session.commit()
        log.warning("hl.reject", symbol=intent.symbol, side=intent.side, error=error)
        return OrderResult(
            order_id=str(row),
            status="rejected",
            filled_qty=0.0,
            avg_fill_price=0.0,
            fee=0.0,
            pnl=0.0,
            ts=ts,
            error=error,
        )
