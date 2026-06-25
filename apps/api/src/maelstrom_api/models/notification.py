import enum
import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Time, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from maelstrom_api.db import Base


class ChannelKind(enum.StrEnum):
    TELEGRAM = "telegram"
    DISCORD = "discord"


class NotificationEvent(enum.StrEnum):
    KILL_ACCOUNT = "kill_account"
    BACKTEST_DONE = "backtest_done"
    SIGNAL_TOP = "signal_top"
    PRICE_ALERT = "price_alert"
    LIVE_FAILED = "live_failed"
    FILL = "fill"
    ORDER_REJECTED = "order_rejected"
    DAILY_SUMMARY = "daily_summary"
    TEST = "test"


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    events: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False, default=list)
    quiet_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
