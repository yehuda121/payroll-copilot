"""AI usage metrics for the developer dashboard and model comparison.

CloudWatch is the production aggregate store (no DynamoDB event history).
An in-process aggregator backs local/dev and unit tests when CloudWatch is off.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from payroll_copilot.infrastructure.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ModelComparisonRow:
    provider: str
    model: str
    request_count: int
    average_latency_ms: float
    average_tokens: float
    estimated_cost_usd: float
    success_rate: float


@dataclass(slots=True)
class DashboardSummary:
    total_tokens: int
    tokens_by_provider: dict[str, int]
    tokens_by_model: dict[str, int]
    estimated_cost_usd: float
    average_latency_ms: float
    error_rate: float
    retry_rate: float
    fallback_rate: float
    request_count: int
    window_hours: int


class _AggregateBucket:
    __slots__ = (
        "requests",
        "successes",
        "errors",
        "retries",
        "fallbacks",
        "tokens",
        "cost",
        "latency_sum",
    )

    def __init__(self) -> None:
        self.requests = 0
        self.successes = 0
        self.errors = 0
        self.retries = 0
        self.fallbacks = 0
        self.tokens = 0
        self.cost = 0.0
        self.latency_sum = 0.0


class InMemoryAIMetricsStore:
    """Process-local aggregates keyed by (provider, model). Not event history."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_model: dict[tuple[str, str], _AggregateBucket] = defaultdict(
            _AggregateBucket
        )
        self._started_at = time.time()

    def record(
        self,
        *,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost_usd: float,
        latency_ms: float,
        success: bool,
        retry_count: int,
        fallback_used: bool,
    ) -> None:
        key = ((provider or "unknown").lower(), model or "unknown")
        with self._lock:
            bucket = self._by_model[key]
            bucket.requests += 1
            if success:
                bucket.successes += 1
            else:
                bucket.errors += 1
            if retry_count > 0:
                bucket.retries += 1
            if fallback_used:
                bucket.fallbacks += 1
            bucket.tokens += max(int(total_tokens), 0)
            bucket.cost += float(estimated_cost_usd or 0.0)
            bucket.latency_sum += float(latency_ms or 0.0)

    def summary(self, *, window_hours: int = 24) -> DashboardSummary:
        # Process-local store has no time index; window_hours is informational.
        with self._lock:
            buckets = dict(self._by_model)
        total_tokens = 0
        total_cost = 0.0
        total_latency = 0.0
        requests = 0
        errors = 0
        retries = 0
        fallbacks = 0
        by_provider: dict[str, int] = defaultdict(int)
        by_model: dict[str, int] = defaultdict(int)
        for (provider, model), bucket in buckets.items():
            total_tokens += bucket.tokens
            total_cost += bucket.cost
            total_latency += bucket.latency_sum
            requests += bucket.requests
            errors += bucket.errors
            retries += bucket.retries
            fallbacks += bucket.fallbacks
            by_provider[provider] += bucket.tokens
            label = f"{provider}/{model}" if model else provider
            by_model[label] += bucket.tokens
        avg_latency = (total_latency / requests) if requests else 0.0
        return DashboardSummary(
            total_tokens=total_tokens,
            tokens_by_provider=dict(sorted(by_provider.items())),
            tokens_by_model=dict(sorted(by_model.items())),
            estimated_cost_usd=round(total_cost, 6),
            average_latency_ms=round(avg_latency, 2),
            error_rate=round(errors / requests, 4) if requests else 0.0,
            retry_rate=round(retries / requests, 4) if requests else 0.0,
            fallback_rate=round(fallbacks / requests, 4) if requests else 0.0,
            request_count=requests,
            window_hours=window_hours,
        )

    def model_comparison(self, *, window_hours: int = 24) -> list[ModelComparisonRow]:
        del window_hours  # informational only for in-memory store
        with self._lock:
            buckets = dict(self._by_model)
        rows: list[ModelComparisonRow] = []
        for (provider, model), bucket in sorted(buckets.items()):
            if bucket.requests <= 0:
                continue
            rows.append(
                ModelComparisonRow(
                    provider=provider,
                    model=model,
                    request_count=bucket.requests,
                    average_latency_ms=round(bucket.latency_sum / bucket.requests, 2),
                    average_tokens=round(bucket.tokens / bucket.requests, 2),
                    estimated_cost_usd=round(bucket.cost, 6),
                    success_rate=round(bucket.successes / bucket.requests, 4),
                )
            )
        return rows

    def reset(self) -> None:
        with self._lock:
            self._by_model.clear()
            self._started_at = time.time()


_PROCESS_STORE = InMemoryAIMetricsStore()


class AIMetricsRecorder:
    """Record AI call aggregates and optionally emit CloudWatch custom metrics."""

    def __init__(self, settings: Settings, store: InMemoryAIMetricsStore | None = None) -> None:
        self._settings = settings
        self._store = store or _PROCESS_STORE
        self._cw_client: Any | None = None

    def record(
        self,
        *,
        provider: str,
        model: str,
        capability: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost_usd: float,
        latency_ms: float,
        success: bool,
        retry_count: int,
        fallback_used: bool,
    ) -> None:
        self._store.record(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            latency_ms=latency_ms,
            success=success,
            retry_count=retry_count,
            fallback_used=fallback_used,
        )
        if self._settings.cloudwatch_enabled:
            self._emit_cloudwatch(
                provider=provider,
                model=model,
                capability=capability,
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                latency_ms=latency_ms,
                success=success,
                retry_count=retry_count,
                fallback_used=fallback_used,
            )

    def summary(self, *, window_hours: int = 24) -> DashboardSummary:
        # Prefer process aggregates (same shape as CloudWatch dims). CloudWatch
        # PutMetricData is for alarms/ops; GetMetricData is not required for the UI.
        return self._store.summary(window_hours=window_hours)

    def model_comparison(self, *, window_hours: int = 24) -> list[ModelComparisonRow]:
        return self._store.model_comparison(window_hours=window_hours)

    def _emit_cloudwatch(
        self,
        *,
        provider: str,
        model: str,
        capability: str,
        total_tokens: int,
        estimated_cost_usd: float,
        latency_ms: float,
        success: bool,
        retry_count: int,
        fallback_used: bool,
    ) -> None:
        try:
            client = self._cloudwatch()
            dims = [
                {"Name": "Provider", "Value": (provider or "unknown")[:256]},
                {"Name": "Model", "Value": (model or "unknown")[:256]},
                {"Name": "Capability", "Value": (capability or "general")[:256]},
            ]
            namespace = self._settings.cloudwatch_metrics_namespace or "PayrollCopilot"
            metric_data = [
                {
                    "MetricName": "AITokens",
                    "Dimensions": dims,
                    "Value": float(max(total_tokens, 0)),
                    "Unit": "Count",
                },
                {
                    "MetricName": "AICostUSD",
                    "Dimensions": dims,
                    "Value": float(estimated_cost_usd or 0.0),
                    "Unit": "None",
                },
                {
                    "MetricName": "AILatencyMs",
                    "Dimensions": dims,
                    "Value": float(max(latency_ms, 0.0)),
                    "Unit": "Milliseconds",
                },
                {
                    "MetricName": "AISuccess",
                    "Dimensions": dims,
                    "Value": 1.0 if success else 0.0,
                    "Unit": "Count",
                },
                {
                    "MetricName": "AIError",
                    "Dimensions": dims,
                    "Value": 0.0 if success else 1.0,
                    "Unit": "Count",
                },
                {
                    "MetricName": "AIRetry",
                    "Dimensions": dims,
                    "Value": 1.0 if retry_count > 0 else 0.0,
                    "Unit": "Count",
                },
                {
                    "MetricName": "AIFallback",
                    "Dimensions": dims,
                    "Value": 1.0 if fallback_used else 0.0,
                    "Unit": "Count",
                },
            ]
            client.put_metric_data(Namespace=namespace, MetricData=metric_data)
        except Exception:  # noqa: BLE001 — metrics must never break AI calls
            logger.debug("CloudWatch AI metric emit failed", exc_info=True)

    def _cloudwatch(self) -> Any:
        if self._cw_client is None:
            import boto3

            self._cw_client = boto3.client(
                "cloudwatch",
                region_name=self._settings.aws_region or "us-east-1",
            )
        return self._cw_client


@lru_cache
def get_ai_metrics_recorder() -> AIMetricsRecorder:
    return AIMetricsRecorder(get_settings())


def reset_ai_metrics_for_tests() -> None:
    _PROCESS_STORE.reset()
    get_ai_metrics_recorder.cache_clear()
