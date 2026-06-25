"""Minimal LLM client used by worker tasks (opportunity scanner, etc).

Mirrors apps/api/maelstrom_api/llm/router.py but standalone — workers
don't import from api. Reads provider keys from llm_providers, decrypts
via crypto.py, records calls into llm_calls so the audit ledger stays
unified across both processes.
"""

import time
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from .crypto import decrypt_str

log = structlog.get_logger()


# USD per token; mirrors the api pricing table — keep in sync.
_PRICING: dict[tuple[str, str], tuple[float, float]] = {
    ("anthropic", "claude-opus-4-7"): (15.00 / 1e6, 75.00 / 1e6),
    ("anthropic", "claude-sonnet-4-6"): (3.00 / 1e6, 15.00 / 1e6),
    ("anthropic", "claude-haiku-4-5"): (0.80 / 1e6, 4.00 / 1e6),
    ("openai", "gpt-4o"): (2.50 / 1e6, 10.00 / 1e6),
    ("openai", "gpt-4o-mini"): (0.15 / 1e6, 0.60 / 1e6),
    ("openai", "o1"): (15.00 / 1e6, 60.00 / 1e6),
    ("openai", "o1-mini"): (3.00 / 1e6, 12.00 / 1e6),
}


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
}


@dataclass(slots=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    duration_ms: int
    call_id: str | None  # row in llm_calls; None on persistence error


async def _load_provider(sm: async_sessionmaker, provider: str) -> tuple[str, str]:
    """Return (api_key, default_model) or raise."""
    async with sm() as session:
        row = (
            await session.execute(
                text(
                    "SELECT api_key_enc, default_model, enabled "
                    "  FROM llm_providers WHERE name = :n",
                ),
                {"n": provider},
            )
        ).first()
    if row is None or not row[0]:
        raise RuntimeError(f"no API key configured for {provider}")
    if not row[2]:
        raise RuntimeError(f"{provider} provider is disabled")
    api_key = decrypt_str(bytes(row[0]))
    default_model = row[1] or _DEFAULT_MODELS.get(provider, "")
    return api_key, default_model


async def _record(
    sm: async_sessionmaker,
    *,
    provider: str,
    model: str,
    purpose: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    duration_ms: int,
    error: str | None,
    summary: str | None,
) -> str | None:
    try:
        async with sm() as session:
            row = (
                await session.execute(
                    text(
                        "INSERT INTO llm_calls "
                        " (provider, model, purpose, prompt_tokens, completion_tokens, "
                        "  cost_usd, duration_ms, error, request_summary) "
                        "VALUES (:p, :m, :pur, :pt, :ct, :cost, :ms, :err, :s) "
                        "RETURNING id",
                    ),
                    {
                        "p": provider,
                        "m": model,
                        "pur": purpose,
                        "pt": prompt_tokens,
                        "ct": completion_tokens,
                        "cost": cost_usd,
                        "ms": duration_ms,
                        "err": error,
                        "s": summary,
                    },
                )
            ).scalar_one()
            await session.commit()
            return str(row)
    except Exception as e:
        log.warning("worker.llm.record_failed", error=str(e))
        return None


async def complete(
    sm: async_sessionmaker,
    *,
    provider: str,
    purpose: str,
    system: str,
    user_message: str,
    model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.4,
    assistant_prefill: str = "",
) -> CompletionResult:
    if provider not in ("anthropic", "openai"):
        raise ValueError(f"unknown provider {provider}")
    api_key, default_model = await _load_provider(sm, provider)
    model = model or default_model
    if not model:
        raise RuntimeError(f"no default_model set for {provider}")

    t0 = time.perf_counter()
    try:
        if provider == "anthropic":
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key)
            messages: list[dict[str, str]] = [{"role": "user", "content": user_message}]
            if assistant_prefill:
                # Anthropic prefill: the model continues from this string.
                # Prefilled chars aren't echoed in resp.content, so we prepend
                # them manually below for downstream parsers.
                messages.append({"role": "assistant", "content": assistant_prefill})
            resp = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,  # type: ignore[arg-type]
            )
            text_out = "".join((b.text if hasattr(b, "text") else "") for b in resp.content).strip()
            if assistant_prefill:
                text_out = assistant_prefill + text_out
            ptoks = resp.usage.input_tokens or 0
            ctoks = resp.usage.output_tokens or 0
        else:
            from openai import AsyncOpenAI

            client_o = AsyncOpenAI(api_key=api_key)
            resp_o = await client_o.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
            )
            text_out = (resp_o.choices[0].message.content or "").strip()
            usage = resp_o.usage
            ptoks = usage.prompt_tokens if usage else 0
            ctoks = usage.completion_tokens if usage else 0
    except Exception as e:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        call_id = await _record(
            sm,
            provider=provider,
            model=model,
            purpose=purpose,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            duration_ms=duration_ms,
            error=str(e)[:2000],
            summary=user_message[:200],
        )
        log.exception("worker.llm.failed", provider=provider, model=model, purpose=purpose)
        raise RuntimeError(f"LLM call failed: {e}") from e

    duration_ms = int((time.perf_counter() - t0) * 1000)
    in_rate, out_rate = _PRICING.get((provider, model), (0.0, 0.0))
    cost = ptoks * in_rate + ctoks * out_rate
    call_id = await _record(
        sm,
        provider=provider,
        model=model,
        purpose=purpose,
        prompt_tokens=ptoks,
        completion_tokens=ctoks,
        cost_usd=cost,
        duration_ms=duration_ms,
        error=None,
        summary=user_message[:200],
    )
    log.info(
        "worker.llm.complete",
        provider=provider,
        model=model,
        purpose=purpose,
        in_tokens=ptoks,
        out_tokens=ctoks,
        cost_usd=round(cost, 4),
        ms=duration_ms,
    )
    return CompletionResult(
        text=text_out,
        provider=provider,
        model=model,
        prompt_tokens=ptoks,
        completion_tokens=ctoks,
        cost_usd=cost,
        duration_ms=duration_ms,
        call_id=call_id,
    )
