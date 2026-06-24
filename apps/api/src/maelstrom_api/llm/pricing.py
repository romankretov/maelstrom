"""USD per token, by (provider, model). Update when prices move.

Returns (input_per_token, output_per_token, cache_read_per_token).
For Anthropic, cache_read is ~10% of input. For OpenAI we don't bill
discounted cache reads yet (the SDK reports cached tokens, but at the
same rate as input).
"""

PRICING: dict[tuple[str, str], tuple[float, float, float]] = {
    # ---------- Anthropic (USD / 1M tokens, divided to per-token here)
    ("anthropic", "claude-opus-4-7"): (15.00 / 1e6, 75.00 / 1e6, 1.50 / 1e6),
    ("anthropic", "claude-sonnet-4-6"): (3.00 / 1e6, 15.00 / 1e6, 0.30 / 1e6),
    ("anthropic", "claude-haiku-4-5"): (0.80 / 1e6, 4.00 / 1e6, 0.08 / 1e6),
    # ---------- OpenAI
    ("openai", "gpt-4o"): (2.50 / 1e6, 10.00 / 1e6, 2.50 / 1e6),
    ("openai", "gpt-4o-mini"): (0.15 / 1e6, 0.60 / 1e6, 0.15 / 1e6),
    ("openai", "o1"): (15.00 / 1e6, 60.00 / 1e6, 15.00 / 1e6),
    ("openai", "o1-mini"): (3.00 / 1e6, 12.00 / 1e6, 3.00 / 1e6),
}


def compute_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> float:
    rates = PRICING.get((provider, model))
    if rates is None:
        return 0.0
    in_rate, out_rate, cache_rate = rates
    uncached = max(prompt_tokens - cached_tokens, 0)
    return uncached * in_rate + cached_tokens * cache_rate + completion_tokens * out_rate
