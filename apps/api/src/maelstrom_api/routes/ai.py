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
from maelstrom_api.llm.prompts import STRATEGY_GEN_SYSTEM, STRATEGY_OPTIMIZE_SYSTEM
from maelstrom_api.models import BacktestRun, LLMCall, LLMProvider, StrategyVersion, User
from maelstrom_api.schemas.llm import (
    LLMCallOut,
    LLMProviderOut,
    LLMProviderUpsert,
    StrategyGenRequest,
    StrategyGenResponse,
    StrategyOptimizeRequest,
    StrategyOptimizeResponse,
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


# ----------------------------------------------------------------- optimize


_SECTION_SPLIT = re.compile(r"^\s*===\s*CODE\s*===\s*$", re.MULTILINE)


def _split_rationale_code(raw: str) -> tuple[str, str]:
    parts = _SECTION_SPLIT.split(raw, maxsplit=1)
    if len(parts) != 2:
        return "", _unfence(raw)
    rationale = parts[0].replace("RATIONALE:", "", 1).strip()
    return rationale, _unfence(parts[1])


@router.post("/strategies/optimize", response_model=StrategyOptimizeResponse)
async def optimize_strategy(
    body: StrategyOptimizeRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(current_active_user)],
) -> StrategyOptimizeResponse:
    run = await session.get(BacktestRun, body.backtest_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "backtest run not found")
    version = await session.get(StrategyVersion, run.strategy_version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "strategy version not found")
    metrics = run.metrics or {}

    user_message = (
        f"## Current strategy code (v{version.version})\n"
        f"```python\n{version.code}\n```\n\n"
        "## Backtest metrics\n"
        f"- source: {run.source}\n"
        f"- symbols: {', '.join(run.symbols)}\n"
        f"- timeframe: {run.timeframe}\n"
        f"- range: {run.range_start.isoformat()} → {run.range_end.isoformat()}\n"
        f"- initial_capital: {run.initial_capital}\n"
        f"- total_return: {metrics.get('total_return')}\n"
        f"- sharpe: {metrics.get('sharpe')}\n"
        f"- sortino: {metrics.get('sortino')}\n"
        f"- max_drawdown: {metrics.get('max_drawdown')}\n"
        f"- calmar: {metrics.get('calmar')}\n"
        f"- win_rate: {metrics.get('win_rate')}\n"
        f"- trade_count: {metrics.get('trade_count')}\n"
        f"- profit_factor: {metrics.get('profit_factor')}\n"
        f"- final_equity: {metrics.get('final_equity')}\n\n"
        "Propose one focused improvement and output the revised code "
        "as specified."
    )
    rtr = get_router()
    try:
        result = await rtr.complete(
            session,
            provider=body.provider,
            purpose="strategy_optimize",
            system=STRATEGY_OPTIMIZE_SYSTEM,
            user_message=user_message,
            user_id=user.id,
            model=body.model,
            max_tokens=4096,
            temperature=0.4,
        )
    except RuntimeError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"LLM call failed: {e}. Configure the provider key in Settings.",
        ) from e
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM error: {e!s}"[:400]) from e

    rationale, code = _split_rationale_code(result.text)
    return StrategyOptimizeResponse(
        rationale=rationale or "(model did not emit a rationale section)",
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
