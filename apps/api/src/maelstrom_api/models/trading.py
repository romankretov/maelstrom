import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    LargeBinary,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from maelstrom_api.db import Base


class AccountKind(enum.StrEnum):
    PAPER = "paper"
    LIVE_HL_TESTNET = "live_hl_testnet"
    LIVE_HL_MAIN = "live_hl_main"


class LiveStatus(enum.StrEnum):
    PAUSED = "paused"
    PENDING_START = "pending_start"
    RUNNING = "running"
    PENDING_STOP = "pending_stop"
    STOPPED = "stopped"
    FAILED = "failed"


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    starting_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    killed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    daily_loss_limit_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    api_key_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    api_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LiveStrategy(Base):
    __tablename__ = "live_strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="paused")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_notional_per_symbol: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    max_position_qty: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requester_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    live_strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("live_strategies.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 10), nullable=True)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default="market")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    filled_qty: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False, default=0)
    avg_fill_price: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False, default=0)
    pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exchange_fill_id: Mapped[str | None] = mapped_column(String(160), nullable=True)


class Position(Base):
    __tablename__ = "positions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
    )
    symbol: Mapped[str] = mapped_column(String(64))
    qty: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False, default=0)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False, default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    last_price: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (PrimaryKeyConstraint("account_id", "symbol", name="pk_positions"),)


class AccountEquity(Base):
    __tablename__ = "account_equity"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)

    __table_args__ = (PrimaryKeyConstraint("account_id", "ts", name="pk_account_equity"),)
