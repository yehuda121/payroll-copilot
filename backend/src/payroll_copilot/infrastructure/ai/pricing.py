"""Estimate USD cost from token counts using a small static price map."""

from __future__ import annotations

# Prices are USD per 1M tokens (input, output). Ollama / unknown → 0.
_PRICE_PER_1M: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-5": (5.0, 15.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    # Bedrock Anthropic (approximate list prices)
    "anthropic.claude-3-5-sonnet": (3.0, 15.0),
    "anthropic.claude-3-5-haiku": (0.8, 4.0),
    "anthropic.claude-3-sonnet": (3.0, 15.0),
    "anthropic.claude-sonnet-4": (3.0, 15.0),
    # Embeddings (output unused)
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    "amazon.titan-embed-text-v2": (0.02, 0.0),
}


def _lookup_rates(provider: str, model: str) -> tuple[float, float]:
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider == "ollama":
        return (0.0, 0.0)
    model_key = (model or "").strip().lower()
    if not model_key:
        return (0.0, 0.0)
    if model_key in _PRICE_PER_1M:
        return _PRICE_PER_1M[model_key]
    for prefix, rates in _PRICE_PER_1M.items():
        if model_key.startswith(prefix) or prefix in model_key:
            return rates
    return (0.0, 0.0)


def estimate_cost_usd(
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    input_rate, output_rate = _lookup_rates(provider, model)
    cost = (max(prompt_tokens, 0) / 1_000_000.0) * input_rate + (
        max(completion_tokens, 0) / 1_000_000.0
    ) * output_rate
    return round(cost, 8)
