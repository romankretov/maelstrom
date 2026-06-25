"""LLMRouter — one client for OpenAI + Anthropic with audit/cost tracking.

Loads API keys at first use from llm_providers (encrypted column). Every
call writes one row to llm_calls so we can later show a cost dashboard
and rate-limit per user.

The Anthropic path uses prompt caching for the system prompt — strategy
generation reuses the same system message thousands of times, and caching
drops input cost ~90%.
"""

import time
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from maelstrom_api import crypto

from .pricing import compute_cost

log = structlog.get_logger()


@dataclass(slots=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_usd: float
    duration_ms: int


_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
}


class LLMRouter:
    def __init__(self) -> None:
        self._anthropic: object | None = None
        self._openai: object | None = None
        self._keys: dict[str, str] = {}

    async def _ensure_key(self, session: AsyncSession, provider: str) -> str:
        if provider in self._keys:
            return self._keys[provider]
        row = (
            await session.execute(
                text(
                    "SELECT api_key_enc, enabled FROM llm_providers WHERE name = :n",
                ),
                {"n": provider},
            )
        ).first()
        if row is None or not row[0]:
            raise RuntimeError(f"no API key configured for {provider}")
        if not row[1]:
            raise RuntimeError(f"{provider} provider is disabled")
        api_key = crypto.decrypt_str(bytes(row[0]))
        self._keys[provider] = api_key
        return api_key

    async def _default_model(self, session: AsyncSession, provider: str) -> str:
        row = (
            await session.execute(
                text("SELECT default_model FROM llm_providers WHERE name = :n"),
                {"n": provider},
            )
        ).first()
        if row and row[0]:
            return str(row[0])
        return _DEFAULT_MODELS.get(provider, "")

    async def complete(
        self,
        session: AsyncSession,
        *,
        provider: str,
        purpose: str,
        system: str,
        user_message: str,
        user_id: uuid.UUID | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.5,
        cache_system: bool = True,
        assistant_prefill: str = "",
    ) -> CompletionResult:
        if provider not in ("anthropic", "openai"):
            raise ValueError(f"unknown provider {provider}")
        key = await self._ensure_key(session, provider)
        model = model or await self._default_model(session, provider)
        if not model:
            raise RuntimeError(f"no default_model set for {provider}")

        t0 = time.perf_counter()
        try:
            if provider == "anthropic":
                text_out, ptoks, ctoks, cached_toks = await self._anthropic_call(
                    key,
                    model,
                    system,
                    user_message,
                    max_tokens,
                    temperature,
                    cache_system,
                    assistant_prefill,
                )
            else:
                text_out, ptoks, ctoks, cached_toks = await self._openai_call(
                    key,
                    model,
                    system,
                    user_message,
                    max_tokens,
                    temperature,
                )
        except Exception as e:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            await self._record(
                session,
                user_id=user_id,
                provider=provider,
                model=model,
                purpose=purpose,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                cached=False,
                duration_ms=duration_ms,
                error=str(e)[:2000],
                summary=user_message[:200],
            )
            raise

        duration_ms = int((time.perf_counter() - t0) * 1000)
        cost = compute_cost(provider, model, ptoks, ctoks, cached_toks)
        await self._record(
            session,
            user_id=user_id,
            provider=provider,
            model=model,
            purpose=purpose,
            prompt_tokens=ptoks,
            completion_tokens=ctoks,
            cost_usd=cost,
            cached=cached_toks > 0,
            duration_ms=duration_ms,
            error=None,
            summary=user_message[:200],
        )
        log.info(
            "llm.complete",
            provider=provider,
            model=model,
            purpose=purpose,
            prompt=ptoks,
            completion=ctoks,
            cached=cached_toks,
            cost_usd=round(cost, 4),
            ms=duration_ms,
        )
        return CompletionResult(
            text=text_out,
            provider=provider,
            model=model,
            prompt_tokens=ptoks,
            completion_tokens=ctoks,
            cached_tokens=cached_toks,
            cost_usd=cost,
            duration_ms=duration_ms,
        )

    # ---- provider-specific impls ----------------------------------------

    async def _anthropic_call(
        self,
        api_key: str,
        model: str,
        system: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
        cache_system: bool,
        assistant_prefill: str = "",
    ) -> tuple[str, int, int, int]:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        sys_blocks: list[dict[str, object]] = (
            [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            if cache_system
            else [{"type": "text", "text": system}]
        )
        messages: list[dict[str, str]] = [{"role": "user", "content": user_message}]
        if assistant_prefill:
            # Anthropic's prefill: the model continues from this string,
            # forcing structured output. The prefilled tokens come back
            # only as our local prepend — they aren't in resp.content.
            messages.append({"role": "assistant", "content": assistant_prefill})
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=sys_blocks,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )
        text_out = "".join((b.text if hasattr(b, "text") else "") for b in resp.content).strip()
        if assistant_prefill:
            text_out = assistant_prefill + text_out
        usage = resp.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
        ptoks = (usage.input_tokens or 0) + cache_create + cache_read
        return text_out, ptoks, usage.output_tokens or 0, cache_read

    async def _openai_call(
        self,
        api_key: str,
        model: str,
        system: str,
        user_message: str,
        max_tokens: int,
        temperature: float,
    ) -> tuple[str, int, int, int]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
        )
        text_out = (resp.choices[0].message.content or "").strip()
        usage = resp.usage
        ptoks = usage.prompt_tokens if usage else 0
        ctoks = usage.completion_tokens if usage else 0
        cached = 0
        if usage and hasattr(usage, "prompt_tokens_details"):
            cached = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
        return text_out, ptoks, ctoks, cached

    # ---- audit -----------------------------------------------------------

    async def _record(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID | None,
        provider: str,
        model: str,
        purpose: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        cached: bool,
        duration_ms: int,
        error: str | None,
        summary: str | None,
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO llm_calls "
                " (user_id, provider, model, purpose, prompt_tokens, "
                "  completion_tokens, cost_usd, cached, duration_ms, "
                "  error, request_summary) "
                "VALUES (:uid, :prov, :model, :purpose, :pt, :ct, "
                "        :cost, :cached, :ms, :err, :summary)",
            ),
            {
                "uid": user_id,
                "prov": provider,
                "model": model,
                "purpose": purpose,
                "pt": prompt_tokens,
                "ct": completion_tokens,
                "cost": cost_usd,
                "cached": cached,
                "ms": duration_ms,
                "err": error,
                "summary": summary,
            },
        )
        await session.commit()


_router_singleton: LLMRouter | None = None


def get_router() -> LLMRouter:
    global _router_singleton
    if _router_singleton is None:
        _router_singleton = LLMRouter()
    return _router_singleton
