"""LLM-powered endpoints: provider config + strategy generation."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import audit, crypto
from maelstrom_api.auth import current_active_user
from maelstrom_api.db import get_session
from maelstrom_api.llm import get_router
from maelstrom_api.llm.prompts import STRATEGY_GEN_SYSTEM
from maelstrom_api.models import LLMCall, LLMProvider, User
from maelstrom_api.schemas.llm import (
    LLMCallOut,
    LLMProviderOut,
    LLMProviderUpsert,
    StrategyGenRequest,
    StrategyGenResponse,
)

router = APIRouter(
    prefix="/ai",
    tags=["ai"],
    dependencies=[Depends(current_active_user)],
)


# ----------------------------------------------------------------- providers


def _to_out(p: LLMProvider) -> LLMProviderOut:
    return LLMProviderOut(
        name=p.name,
        default_model=p.default_model,
        enabled=p.enabled,
        has_key=p.api_key_enc is not None,
        updated_at=p.updated_at,
    )


@router.get("/providers", response_model=list[LLMProviderOut])
async def list_providers(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> list[LLMProviderOut]:
    rows = list(
        (await session.execute(select(LLMProvider).order_by(LLMProvider.name))).scalars().all()
    )
    return [_to_out(p) for p in rows]


@router.put("/providers/{name}", response_model=LLMProviderOut)
async def upsert_provider(
    name: str,
    body: LLMProviderUpsert,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> LLMProviderOut:
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    if name not in ("openai", "anthropic"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown provider")
    p = await session.get(LLMProvider, name)
    if p is None:
        p = LLMProvider(name=name)
        session.add(p)
    if body.api_key:
        p.api_key_enc = crypto.encrypt_str(body.api_key)
    if body.default_model is not None:
        p.default_model = body.default_model
    if body.enabled is not None:
        p.enabled = body.enabled
    await audit.record(
        session,
        action="llm.provider.upsert",
        actor_id=user.id,
        target_kind="llm_provider",
        target_id=name,
        payload={
            "default_model": body.default_model,
            "enabled": body.enabled,
            "rotated_key": bool(body.api_key),
        },
    )
    await session.commit()
    await session.refresh(p)
    # Bust the cached key in the router so the new key is used immediately.
    get_router()._keys.pop(name, None)
    return _to_out(p)


# ----------------------------------------------------------------- strategy gen


_FENCED_PATTERN = re.compile(r"^```(?:python)?\s*([\s\S]*?)```\s*$", re.IGNORECASE)


def _unfence(code: str) -> str:
    """Strip ```python ... ``` fences if the model added them anyway."""
    m = _FENCED_PATTERN.match(code.strip())
    return m.group(1).strip() if m else code.strip()


@router.post("/strategies/generate", response_model=StrategyGenResponse)
async def generate_strategy(
    body: StrategyGenRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> StrategyGenResponse:
    rtr = get_router()
    try:
        result = await rtr.complete(
            session,
            provider=body.provider,
            purpose="strategy_gen",
            system=STRATEGY_GEN_SYSTEM,
            user_message=body.prompt,
            user_id=user.id,
            model=body.model,
            max_tokens=4096,
            temperature=0.4,
        )
    except RuntimeError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"LLM call failed: {e}. Configure the provider key in Settings first.",
        ) from e
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM error: {e!s}"[:400]) from e

    code = _unfence(result.text)
    return StrategyGenResponse(
        code=code,
        provider=result.provider,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cached_tokens=result.cached_tokens,
        cost_usd=result.cost_usd,
        duration_ms=result.duration_ms,
    )


# ----------------------------------------------------------------- usage


@router.get("/calls", response_model=list[LLMCallOut])
async def recent_calls(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> list[LLMCall]:
    stmt = select(LLMCall).order_by(desc(LLMCall.created_at)).limit(50)
    return list((await session.execute(stmt)).scalars().all())
