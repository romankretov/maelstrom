import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scanner: str
    source: str
    symbol: str
    direction: str
    score: Decimal
    confidence: Decimal | None = None
    horizon: str | None = None
    rationale: str
    context: dict[str, Any] = Field(default_factory=dict)
    llm_call_id: uuid.UUID | None = None
    ts: datetime
    expires_at: datetime | None = None
