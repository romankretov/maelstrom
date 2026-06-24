import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LLMProviderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    default_model: str | None = None
    enabled: bool
    has_key: bool
    updated_at: datetime


class LLMProviderUpsert(BaseModel):
    api_key: str | None = Field(default=None, min_length=10, max_length=400)
    default_model: str | None = None
    enabled: bool | None = None


class StrategyGenRequest(BaseModel):
    prompt: str = Field(min_length=4, max_length=4000)
    provider: str = Field(default="anthropic")
    model: str | None = None


class StrategyGenResponse(BaseModel):
    code: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    duration_ms: int


class StrategyOptimizeRequest(BaseModel):
    backtest_run_id: uuid.UUID
    provider: str = Field(default="anthropic")
    model: str | None = None


class StrategyOptimizeResponse(BaseModel):
    rationale: str
    code: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    duration_ms: int


class JournalRequest(BaseModel):
    question: str = Field(min_length=4, max_length=2000)
    account_id: uuid.UUID | None = None
    strategy_id: uuid.UUID | None = None
    days: int = Field(default=14, ge=1, le=180)
    provider: str = Field(default="anthropic")
    model: str | None = None


class JournalResponse(BaseModel):
    answer: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    duration_ms: int


class LLMCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    model: str
    purpose: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    cached: bool
    duration_ms: int
    error: str | None = None
    request_summary: str | None = None
    created_at: datetime
