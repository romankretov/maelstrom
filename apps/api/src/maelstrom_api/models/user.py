import enum
import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from maelstrom_api.db import Base


class Role(enum.StrEnum):
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"
    READONLY = "readonly"


class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID]
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role"),
        default=Role.VIEWER,
        nullable=False,
    )
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    totp_secret: Mapped[str | None] = mapped_column(String(64), default=None)
    totp_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
