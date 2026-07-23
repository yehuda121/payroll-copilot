"""Request-scoped AI call context (retry/fallback flags, turn aggregation)."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from payroll_copilot.application.ports.ai_usage import AIUsageStats

_ai_call_context: ContextVar[AICallContext | None] = ContextVar(
    "ai_call_context", default=None
)


@dataclass
class AICallContext:
    """Mutable bag attached to one chat turn / extraction attempt."""

    capability: str = ""
    retry_count: int = 0
    fallback_used: bool = False
    fallback_from: str = ""
    fallback_to: str = ""
    usages: list[AIUsageStats] = field(default_factory=list)

    def record_usage(self, usage: AIUsageStats) -> None:
        enriched = AIUsageStats(
            provider=usage.provider,
            model=usage.model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
            latency_ms=usage.latency_ms,
            retry_count=max(usage.retry_count, self.retry_count),
            fallback_used=usage.fallback_used or self.fallback_used,
        )
        self.usages.append(enriched)

    def aggregated_usage(self) -> AIUsageStats | None:
        if not self.usages:
            return None
        merged = self.usages[0]
        for item in self.usages[1:]:
            merged = merged.merge(item)
        return AIUsageStats(
            provider=merged.provider,
            model=merged.model,
            prompt_tokens=merged.prompt_tokens,
            completion_tokens=merged.completion_tokens,
            total_tokens=merged.total_tokens,
            estimated_cost_usd=merged.estimated_cost_usd,
            latency_ms=merged.latency_ms,
            retry_count=max(merged.retry_count, self.retry_count),
            fallback_used=merged.fallback_used or self.fallback_used,
        )


def get_ai_call_context() -> AICallContext | None:
    return _ai_call_context.get()


@contextmanager
def ai_call_context(
    *,
    capability: str = "",
    retry_count: int = 0,
    fallback_used: bool = False,
) -> Iterator[AICallContext]:
    ctx = AICallContext(
        capability=capability,
        retry_count=retry_count,
        fallback_used=fallback_used,
    )
    token = _ai_call_context.set(ctx)
    try:
        yield ctx
    finally:
        _ai_call_context.reset(token)
