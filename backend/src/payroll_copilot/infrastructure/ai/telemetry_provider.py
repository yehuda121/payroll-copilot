"""Telemetry wrapper around ModelProvider — single choke point for AI usage."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel  # noqa: TC002

from payroll_copilot.application.ports import (  # noqa: TC001
    CompletionResult,
    Message,
    StructuredResult,
)
from payroll_copilot.application.ports.ai_usage import AIUsageStats
from payroll_copilot.infrastructure.ai.ai_call_context import get_ai_call_context
from payroll_copilot.infrastructure.ai.ai_metrics import get_ai_metrics_recorder
from payroll_copilot.infrastructure.ai.pricing import estimate_cost_usd


class TelemetryModelProvider:
    """Decorates any ModelProvider with normalized usage + metrics emission."""

    def __init__(
        self,
        inner: Any,
        *,
        provider_name: str,
        default_model: str = "",
    ) -> None:
        self._inner = inner
        self._provider_name = (provider_name or "unknown").strip().lower()
        self._default_model = (default_model or "").strip()

    @property
    def embedding_dimensions(self) -> int:
        return int(self._inner.embedding_dimensions)

    @property
    def inner(self) -> Any:
        return self._inner

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> CompletionResult:
        started = time.perf_counter()
        try:
            result = await self._inner.complete(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            return self._attach_completion_usage(result, started=started, success=True)
        except Exception:
            self._record_failure(started=started, model=self._default_model)
            raise

    async def complete_structured(
        self,
        messages: list[Message],
        response_schema: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> StructuredResult:
        started = time.perf_counter()
        try:
            result = await self._inner.complete_structured(
                messages,
                response_schema,
                temperature=temperature,
            )
            return self._attach_structured_usage(result, started=started, success=True)
        except Exception:
            self._record_failure(started=started, model=self._default_model)
            raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        started = time.perf_counter()
        try:
            vectors = await self._inner.embed(texts)
            latency_ms = (time.perf_counter() - started) * 1000.0
            stats = AIUsageStats(
                provider=self._provider_name,
                model=self._default_model,
                latency_ms=latency_ms,
            )
            self._publish(stats, success=True)
            return vectors
        except Exception:
            self._record_failure(started=started, model=self._default_model)
            raise

    def _attach_completion_usage(
        self,
        result: CompletionResult,
        *,
        started: float,
        success: bool,
    ) -> CompletionResult:
        usage = self._build_usage(
            prompt_tokens=int(result.prompt_tokens or 0),
            completion_tokens=int(result.completion_tokens or 0),
            total_tokens=int(result.total_tokens or result.tokens_used or 0),
            model=result.model,
            started=started,
        )
        self._publish(usage, success=success)
        if ctx := get_ai_call_context():
            ctx.record_usage(usage)
        result.provider = self._provider_name
        result.prompt_tokens = usage.prompt_tokens
        result.completion_tokens = usage.completion_tokens
        result.total_tokens = usage.total_tokens
        result.tokens_used = usage.total_tokens
        result.estimated_cost_usd = usage.estimated_cost_usd
        result.latency_ms = usage.latency_ms
        result.usage = usage
        return result

    def _attach_structured_usage(
        self,
        result: StructuredResult,
        *,
        started: float,
        success: bool,
    ) -> StructuredResult:
        usage = self._build_usage(
            prompt_tokens=int(result.prompt_tokens or 0),
            completion_tokens=int(result.completion_tokens or 0),
            total_tokens=int(result.total_tokens or 0),
            model=result.model,
            started=started,
        )
        self._publish(usage, success=success)
        if ctx := get_ai_call_context():
            ctx.record_usage(usage)
        result.provider = self._provider_name
        result.prompt_tokens = usage.prompt_tokens
        result.completion_tokens = usage.completion_tokens
        result.total_tokens = usage.total_tokens
        result.estimated_cost_usd = usage.estimated_cost_usd
        result.latency_ms = usage.latency_ms
        result.usage = usage
        return result

    def _build_usage(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        model: str,
        started: float,
    ) -> AIUsageStats:
        if total_tokens <= 0 and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens
        if prompt_tokens <= 0 and completion_tokens <= 0 and total_tokens > 0:
            completion_tokens = total_tokens
        model_name = (model or self._default_model or "").strip()
        ctx = get_ai_call_context()
        cost = estimate_cost_usd(
            provider=self._provider_name,
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return AIUsageStats(
            provider=self._provider_name,
            model=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            retry_count=ctx.retry_count if ctx else 0,
            fallback_used=ctx.fallback_used if ctx else False,
        )

    def _record_failure(self, *, started: float, model: str) -> None:
        ctx = get_ai_call_context()
        stats = AIUsageStats(
            provider=self._provider_name,
            model=model or self._default_model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
            retry_count=ctx.retry_count if ctx else 0,
            fallback_used=ctx.fallback_used if ctx else False,
        )
        self._publish(stats, success=False)

    def _publish(self, usage: AIUsageStats, *, success: bool) -> None:
        ctx = get_ai_call_context()
        get_ai_metrics_recorder().record(
            provider=usage.provider,
            model=usage.model,
            capability=(ctx.capability if ctx else "") or "general",
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            estimated_cost_usd=usage.estimated_cost_usd,
            latency_ms=usage.latency_ms,
            success=success,
            retry_count=usage.retry_count,
            fallback_used=usage.fallback_used,
        )
