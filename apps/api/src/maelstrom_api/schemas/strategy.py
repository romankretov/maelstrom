import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    code: str
    params: dict[str, Any] = Field(default_factory=dict)
    author_id: uuid.UUID | None = None
    message: str | None = None
    created_at: datetime


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    notes: str | None = None
    owner_id: uuid.UUID | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    latest_version: StrategyVersionOut | None = None


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    code: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class StrategyVersionCreate(BaseModel):
    code: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class StrategyUpdate(BaseModel):
    description: str | None = None
    notes: str | None = None
    is_archived: bool | None = None
