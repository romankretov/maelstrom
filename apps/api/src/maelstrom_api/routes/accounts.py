"""Trading account CRUD + portfolio read-side endpoints."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import audit
from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.models import (
    Account,
    AccountEquity,
    Fill,
    Order,
    Position,
    User,
)
from maelstrom_api.schemas.trading import (
    AccountCreate,
    AccountOut,
    AccountUpdate,
    EquityPointOut,
    FillOut,
    OrderOut,
    PortfolioSummary,
    PositionOut,
)

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
    # Only paper allowed for non-admins via plain create. Live accounts get
    # gated in P3.2 (require admin role + per-account toggle).
    if body.kind != "paper" and not user.is_superuser:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "only paper accounts can be created via this endpoint",
        )
    existing = (
        await session.execute(select(Account).where(Account.name == body.name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"account '{body.name}' already exists")

    acc = Account(
        name=body.name,
        kind=body.kind,
        owner_id=user.id,
        starting_capital=body.starting_capital,
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


@router.post("/{account_id}/kill", response_model=AccountOut)
async def kill_account(
    account_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
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


# Silence unused — kept for forward references in P3.1 (live runner attaches fills)
_ = func
