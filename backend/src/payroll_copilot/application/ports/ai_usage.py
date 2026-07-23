"""Shared AI usage contract for telemetry and conversation footers."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class AIUsageStats:
    """Provider-normalized usage for one logical LLM completion (or aggregated turn)."""

    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: float = 0.0
    retry_count: int = 0
    fallback_used: bool = False
    prompt_version: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def merge(self, other: AIUsageStats) -> AIUsageStats:
        """Combine multiple calls in one turn (sum tokens/cost/latency; OR fallback)."""
        provider = self.provider or other.provider
        model = self.model or other.model
        if other.provider and self.provider and other.provider != self.provider:
            provider = f"{self.provider}+{other.provider}"
        if other.model and self.model and other.model != self.model:
            model = other.model
        return AIUsageStats(
            provider=provider,
            model=model,
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            estimated_cost_usd=round(
                self.estimated_cost_usd + other.estimated_cost_usd, 8
            ),
            latency_ms=self.latency_ms + other.latency_ms,
            retry_count=max(self.retry_count, other.retry_count),
            fallback_used=self.fallback_used or other.fallback_used,
            prompt_version=self.prompt_version or other.prompt_version,
        )
