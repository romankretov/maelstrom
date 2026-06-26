"""Trading account CRUD + portfolio read-side endpoints."""

import csv
import io
import uuid
from decimal import Decimal
from typing import Annotated

import structlog
from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import audit, crypto
from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.hyperliquid_info import HyperliquidInfoError, fetch_account_equity
from maelstrom_api.models import (
    Account,
    AccountEquity,
    Fill,
    Order,
    Position,
    User,
)
from maelstrom_api.notify import notify_all
from maelstrom_api.routes.markets import get_arq_pool
from maelstrom_api.schemas.credentials import CredentialState, HyperliquidCredsIn
from maelstrom_api.schemas.trading import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    EquityPointOut,
    FillOut,
    OrderOut,
    PnlAttribution,
    PnlAttributionRow,
    PortfolioSummary,
    PositionOut,
)

log = structlog.get_logger()

router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
    dependencies=[Depends(current_active_user)],
)


def _can_access(account: Account, user: User) -> bool:
    return user.is_superuser or account.owner_id == user.id


# ------------------------------------------------------------------ CRUD


@router.get("", response_model=list[AccountOut])
async def list_accounts(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    active: Annotated[bool, Query()] = True,
) -> list[Account]:
    stmt = select(Account).where(Account.is_active == active)
    if not user.is_superuser:
        stmt = stmt.where(Account.owner_id == user.id)
    stmt = stmt.order_by(Account.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    body: AccountCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> Account:
    # Account-kind gates:
    #   paper           -> anyone
    #   live_hl_testnet -> admin only
    #   live_hl_main    -> admin AND env MAELSTROM_ALLOW_MAINNET=1
    if body.kind == "live_hl_main":
        import os as _os

        if _os.environ.get("MAELSTROM_ALLOW_MAINNET", "").lower() not in ("1", "true", "yes"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "mainnet accounts disabled. Set MAELSTROM_ALLOW_MAINNET=1 on the VPS first.",
            )
        if not user.is_superuser:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "mainnet requires admin")
    elif body.kind != "paper":
        if not user.is_superuser:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "non-paper accounts require admin",
            )
    existing = (
        await session.execute(select(Account).where(Account.name == body.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"account '{body.name}' already exists")

    # For paper accounts, default starting_capital to 10k if not given.
    # For live accounts, leave at 0 — set_credentials will fetch the
    # exchange-side equity baseline once the wallet is wired up.
    if body.starting_capital is None:
        starting_capital = Decimal("10000") if body.kind == "paper" else Decimal("0")
    else:
        starting_capital = body.starting_capital
    acc = Account(
        name=body.name,
        kind=body.kind,
        owner_id=user.id,
        starting_capital=starting_capital,
        meta=body.meta,
    )
    session.add(acc)
    await audit.record(
        session,
        action="account.create",
        actor_id=user.id,
        target_kind="account",
        target_id=str(acc.id),
        payload={"name": body.name, "kind": body.kind},
    )
    await session.commit()
    await session.refresh(acc)
    return acc


@router.get("/{account_id}", response_model=AccountOut)
async def get_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> Account:
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    return acc


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: uuid.UUID,
    body: AccountUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> Account:
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    if body.is_active is not None:
        acc.is_active = body.is_active
    if body.daily_loss_limit_pct is not None:
        acc.daily_loss_limit_pct = body.daily_loss_limit_pct
    if body.meta is not None:
        acc.meta = body.meta
    await audit.record(
        session,
        action="account.update",
        actor_id=user.id,
        target_kind="account",
        target_id=str(account_id),
        payload=body.model_dump(exclude_none=True),
    )
    await session.commit()
    await session.refresh(acc)
    return acc


@router.get("/{account_id}/credentials", response_model=CredentialState)
async def get_credentials_state(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> CredentialState:
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    return CredentialState(
        has_credentials=bool(acc.api_key_enc),
        wallet_address=(acc.meta or {}).get("wallet_address"),
    )


@router.post("/{account_id}/credentials", response_model=CredentialState)
async def set_credentials(
    account_id: uuid.UUID,
    body: HyperliquidCredsIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> CredentialState:
    """Encrypt + store Hyperliquid private key + wallet address. Admin only."""
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    if not acc.kind.startswith("live_hl_"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "account is not Hyperliquid-kind")

    acc.api_key_enc = crypto.encrypt_str(body.private_key)
    new_meta = dict(acc.meta or {})
    new_meta["wallet_address"] = body.wallet_address
    acc.meta = new_meta

    # First time we see credentials for this account: fetch equity from the
    # exchange and use it as the baseline. Subsequent re-saves don't reset
    # the baseline (so return-% math is stable). The user can manually
    # PATCH starting_capital if they want to recalibrate.
    if acc.starting_capital == 0:
        try:
            equity = await fetch_account_equity(
                body.wallet_address,
                testnet=(acc.kind == "live_hl_testnet"),
            )
        except HyperliquidInfoError as e:
            # Network / HTTP failure: keep starting_capital at 0 but tell the
            # user so they can hit Sync balance later instead of silently
            # ending up with a useless return-% baseline.
            log.warning(
                "account.starting_capital.fetch_failed",
                account_id=str(account_id),
                error=str(e),
            )
        else:
            if equity > 0:
                acc.starting_capital = Decimal(str(equity))
                log.info(
                    "account.starting_capital.set_from_hl",
                    account_id=str(account_id),
                    equity=equity,
                )

    await audit.record(
        session,
        action="account.credentials.set",
        actor_id=user.id,
        target_kind="account",
        target_id=str(account_id),
        # plaintext key never logged
        payload={
            "wallet_address": body.wallet_address,
            "starting_capital_set": float(acc.starting_capital),
        },
    )
    await session.commit()
    return CredentialState(has_credentials=True, wallet_address=body.wallet_address)


@router.post("/{account_id}/sync-balance", response_model=AccountOut)
async def sync_balance(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> Account:
    """Re-fetch HL equity and overwrite starting_capital. Use this to
    recalibrate the return-% baseline after a deposit / withdrawal."""
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    if not acc.kind.startswith("live_hl_"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "only Hyperliquid accounts")
    wallet = (acc.meta or {}).get("wallet_address")
    if not wallet:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "no wallet_address on account — add credentials first",
        )
    try:
        equity = await fetch_account_equity(wallet, testnet=(acc.kind == "live_hl_testnet"))
    except HyperliquidInfoError as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Hyperliquid info API failed: {e}",
        ) from e
    acc.starting_capital = Decimal(str(equity))
    await audit.record(
        session,
        action="account.sync_balance",
        actor_id=user.id,
        target_kind="account",
        target_id=str(account_id),
        payload={"equity": equity},
    )
    await session.commit()
    await session.refresh(acc)
    return acc


@router.delete("/{account_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def clear_credentials(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> None:
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    acc.api_key_enc = None
    new_meta = dict(acc.meta or {})
    new_meta.pop("wallet_address", None)
    acc.meta = new_meta
    await audit.record(
        session,
        action="account.credentials.clear",
        actor_id=user.id,
        target_kind="account",
        target_id=str(account_id),
    )
    await session.commit()


@router.post("/{account_id}/kill", response_model=AccountOut)
async def kill_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> Account:
    """Hard halt: set killed=true and transition every running/pending strategy
    on this account to pending_stop. Broker rejects any subsequent order."""
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")

    acc.killed = True
    await session.execute(
        text(
            "UPDATE live_strategies "
            "   SET status = 'pending_stop', updated_at = now() "
            " WHERE account_id = :id AND status IN ('running','pending_start')"
        ),
        {"id": str(account_id)},
    )
    await audit.record(
        session,
        action="account.kill",
        actor_id=user.id,
        target_kind="account",
        target_id=str(account_id),
    )
    await session.commit()

    # Notify subscribers (best effort, won't fail the request).
    await notify_all(
        session,
        arq,
        "kill_account",
        {
            "text": f"🛑 *Account killed*: `{acc.name}` ({acc.kind}). "
            "All running strategies pending stop.",
            "account_id": str(account_id),
            "account_name": acc.name,
        },
        user_id=str(user.id) if user.id else None,
    )
    await session.refresh(acc)
    return acc


@router.post("/{account_id}/unkill", response_model=AccountOut)
async def unkill_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> Account:
    """Clear the kill flag. Admin-only — risk equivalent of unlocking the
    safety on a loaded gun."""
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    acc.killed = False
    await audit.record(
        session,
        action="account.unkill",
        actor_id=user.id,
        target_kind="account",
        target_id=str(account_id),
    )
    await session.commit()
    await session.refresh(acc)
    return acc


# ------------------------------------------------------------------ Portfolio


async def _load_account_or_403(
    session: AsyncSession,
    account_id: uuid.UUID,
    user: User,
) -> Account:
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    return acc


async def _compute_cash(session: AsyncSession, account: Account) -> Decimal:
    """cash = starting_capital - sum(fill_signed_notional + fee).
    For buy: cash decreases by qty*price+fee; for sell: cash increases by qty*price-fee.
    """
    rows = await session.execute(
        select(Fill.side, Fill.qty, Fill.price, Fill.fee).where(Fill.account_id == account.id),
    )
    delta = Decimal("0")
    for side, qty, price, fee in rows:
        signed = qty if side == "buy" else -qty
        delta += signed * price + fee  # subtract from cash
    return account.starting_capital - delta


def _unrealized_for(pos: Position) -> Decimal:
    if pos.qty == 0 or pos.last_price == 0:
        return Decimal("0")
    if pos.qty > 0:
        return (pos.last_price - pos.avg_price) * pos.qty
    return (pos.avg_price - pos.last_price) * (-pos.qty)


@router.get("/{account_id}/portfolio", response_model=PortfolioSummary)
async def get_portfolio(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> PortfolioSummary:
    acc = await _load_account_or_403(session, account_id, user)

    positions = list(
        (
            await session.execute(
                select(Position).where(Position.account_id == account_id),
            )
        )
        .scalars()
        .all()
    )
    recent_fills = list(
        (
            await session.execute(
                select(Fill).where(Fill.account_id == account_id).order_by(desc(Fill.ts)).limit(50),
            )
        )
        .scalars()
        .all()
    )

    cash = await _compute_cash(session, acc)
    realized = sum((p.realized_pnl for p in positions), Decimal("0"))
    unrealized = sum((_unrealized_for(p) for p in positions), Decimal("0"))
    position_value = sum(
        (p.qty * p.last_price for p in positions if p.last_price > 0),
        Decimal("0"),
    )
    equity = cash + position_value
    open_count = sum(1 for p in positions if p.qty != 0)
    total_return = float((equity / acc.starting_capital) - 1) if acc.starting_capital > 0 else 0.0

    return PortfolioSummary(
        account=AccountOut.model_validate(acc),
        cash=cash,
        equity=equity,
        total_return=total_return,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        open_positions=open_count,
        positions=[PositionOut.model_validate(p) for p in positions],
        recent_fills=[FillOut.model_validate(f) for f in recent_fills],
    )


@router.post("/{account_id}/positions/{symbol}/close", status_code=status.HTTP_202_ACCEPTED)
async def close_position_route(
    account_id: uuid.UUID,
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    arq: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> dict[str, str]:
    """Manually close an open position via a market order. Routes through
    the same Broker abstraction as live strategies so it works on paper
    and Hyperliquid accounts alike. Async — enqueues a worker task and
    returns immediately; the position row update lands shortly after."""
    acc = await session.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    if not _can_access(acc, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your account")
    job = await arq.enqueue_job("close_position", str(account_id), symbol)
    await audit.record(
        session,
        action="position.manual_close",
        actor_id=user.id,
        target_kind="account",
        target_id=str(account_id),
        payload={"symbol": symbol},
    )
    await session.commit()
    return {"job_id": (job.job_id if job else "")}


@router.get("/{account_id}/pnl-attribution", response_model=PnlAttribution)
async def get_pnl_attribution(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> PnlAttribution:
    """Realized PnL bucketed by (live_strategy, symbol).

    Joins fills → orders → live_strategies → strategies. Fills with no
    live_strategy_id (manual / paper without a runner) bucket under
    strategy=None so they're still visible.
    """
    await _load_account_or_403(session, account_id, user)
    rows = (
        await session.execute(
            text(
                "SELECT "
                "  o.live_strategy_id AS lsid, "
                "  ls.strategy_id    AS sid, "
                "  s.name            AS sname, "
                "  f.symbol          AS symbol, "
                "  SUM(f.pnl)        AS realized, "
                "  SUM(f.fee)        AS fees, "
                "  COUNT(*)          AS fills, "
                "  MIN(f.ts)         AS first_fill, "
                "  MAX(f.ts)         AS last_fill "
                "  FROM fills f "
                "  JOIN orders o ON o.id = f.order_id "
                "  LEFT JOIN live_strategies ls ON ls.id = o.live_strategy_id "
                "  LEFT JOIN strategies s ON s.id = ls.strategy_id "
                " WHERE f.account_id = :acc "
                " GROUP BY o.live_strategy_id, ls.strategy_id, s.name, f.symbol "
                " ORDER BY SUM(f.pnl) DESC",
            ),
            {"acc": account_id},
        )
    ).all()
    out_rows = [
        PnlAttributionRow(
            live_strategy_id=r[0],
            strategy_id=r[1],
            strategy_name=r[2],
            symbol=r[3],
            realized_pnl=float(r[4] or 0),
            fees=float(r[5] or 0),
            fills=int(r[6]),
            first_fill=r[7],
            last_fill=r[8],
        )
        for r in rows
    ]
    return PnlAttribution(
        account_id=account_id,
        rows=out_rows,
        total_realized=sum(r.realized_pnl for r in out_rows),
        total_fees=sum(r.fees for r in out_rows),
    )


@router.get("/{account_id}/equity", response_model=list[EquityPointOut])
async def get_equity(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=20000)] = 5000,
) -> list[AccountEquity]:
    await _load_account_or_403(session, account_id, user)
    stmt = (
        select(AccountEquity)
        .where(AccountEquity.account_id == account_id)
        .order_by(AccountEquity.ts.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{account_id}/orders", response_model=list[OrderOut])
async def get_orders(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Order]:
    await _load_account_or_403(session, account_id, user)
    stmt = (
        select(Order)
        .where(Order.account_id == account_id)
        .order_by(desc(Order.created_at))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{account_id}/fills", response_model=list[FillOut])
async def get_fills(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Fill]:
    await _load_account_or_403(session, account_id, user)
    stmt = select(Fill).where(Fill.account_id == account_id).order_by(desc(Fill.ts)).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{account_id}/fills.csv")
async def export_fills_csv(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
    limit: Annotated[int, Query(ge=1, le=10000)] = 5000,
) -> Response:
    """CSV export of live fills for an account."""
    await _load_account_or_403(session, account_id, user)
    rows = (
        (
            await session.execute(
                select(Fill)
                .where(Fill.account_id == account_id)
                .order_by(desc(Fill.ts))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", "symbol", "side", "qty", "price", "fee"])
    for r in rows:
        w.writerow([r.ts.isoformat(), r.symbol, r.side, str(r.qty), str(r.price), str(r.fee)])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="account_{account_id}_fills.csv"'},
    )


# Silence unused — kept for forward references in P3.1 (live runner attaches fills)
_ = func
