import uuid
from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    kind: str
    label: str
    config: dict[str, Any] = Field(default_factory=dict)
    has_secret: bool = False
    enabled: bool
    events: list[str] = Field(default_factory=list)
    quiet_start: time | None = None
    quiet_end: time | None = None
    created_at: datetime
    updated_at: datetime


class NotificationChannelCreate(BaseModel):
    kind: str
    label: str = Field(min_length=1, max_length=120)
    # For telegram: { "chat_id": "<int as str>" }; for discord: { "webhook_url": "https://..." }
    config: dict[str, Any] = Field(default_factory=dict)
    # For telegram only: the bot token. Stored encrypted, never returned.
    secret: str | None = None
    events: list[str] = Field(default_factory=list)
    quiet_start: time | None = None
    quiet_end: time | None = None


class NotificationChannelUpdate(BaseModel):
    label: str | None = None
    config: dict[str, Any] | None = None
    secret: str | None = None
    enabled: bool | None = None
    events: list[str] | None = None
    quiet_start: time | None = None
    quiet_end: time | None = None
