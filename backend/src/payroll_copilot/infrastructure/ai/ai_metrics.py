"""AI usage metrics for the developer dashboard and model comparison.

CloudWatch is the production historical source (GetMetricData).
An in-process aggregator backs local/dev when CloudWatch is off or unreachable.
No DynamoDB event history.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal

from payroll_copilot.infrastructure.ai.cloudwatch_ai_metrics_reader import (
    CloudWatchAIMetricsReader,
    CloudWatchHistoryResult,
    MetricPoint,
    ProviderMetricSlice,
    choose_period_seconds,
)
from payroll_copilot.infrastructure.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

MetricsSource = Literal["cloudwatch", "process_local"]


@dataclass(slots=True)
class ModelComparisonRow:
    provider: str
    model: str
    request_count: int
    average_latency_ms: float
    average_tokens: float
    estimated_cost_usd: float
    success_rate: float
    error_rate: float = 0.0
    retry_rate: float = 0.0
    fallback_rate: float = 0.0
    capability: str = ""


@dataclass(slots=True)
class DashboardSummary:
    total_tokens: int
    tokens_by_provider: dict[str, int]
    tokens_by_model: dict[str, int]
    tokens_by_capability: dict[str, int]
    estimated_cost_usd: float
    average_latency_ms: float
    error_rate: float
    retry_rate: float
    fallback_rate: float
    request_count: int
    window_hours: int
    prompt_versions: dict[str, int] = field(default_factory=dict)
    source: MetricsSource = "process_local"


@dataclass(slots=True)
class HistorySeriesPoint:
    timestamp: str
    value: float


@dataclass(slots=True)
class ProviderHistoryRow:
    provider: str
    tokens: float
    estimated_cost_usd: float
    average_latency_ms: float
    success_count: float
    error_count: float
    retry_count: float
    fallback_count: float
    request_count: float
    success_rate: float


@dataclass(slots=True)
class AIMetricsHistory:
    source: MetricsSource
    window_hours: int
    period_seconds: int
    tokens: list[HistorySeriesPoint]
    cost_usd: list[HistorySeriesPoint]
    latency_ms: list[HistorySeriesPoint]
    successes: list[HistorySeriesPoint]
    errors: list[HistorySeriesPoint]
    retries: list[HistorySeriesPoint]
    fallbacks: list[HistorySeriesPoint]
    by_provider: list[ProviderHistoryRow]
    prompt_versions: dict[str, int] = field(default_factory=dict)


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


def _hour_bucket(ts: float | None = None) -> int:
    value = int(ts if ts is not None else time.time())
    return value - (value % 3600)


class InMemoryAIMetricsStore:
    """Process-local aggregates keyed by (provider, model, capability).

    Also keeps hourly buckets for local historical trends (no DynamoDB).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_model: dict[tuple[str, str, str], _AggregateBucket] = defaultdict(
            _AggregateBucket
        )
        self._hourly: dict[int, _AggregateBucket] = defaultdict(_AggregateBucket)
        self._hourly_by_provider: dict[tuple[int, str], _AggregateBucket] = defaultdict(
            _AggregateBucket
        )
        self._prompt_versions: dict[str, int] = defaultdict(int)
        self._started_at = time.time()

    def record(
        self,
        *,
        provider: str,
        model: str,
        capability: str = "general",
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        estimated_cost_usd: float,
        latency_ms: float,
        success: bool,
        retry_count: int,
        fallback_used: bool,
        prompt_version: str = "",
    ) -> None:
        del prompt_tokens, completion_tokens  # accepted for API symmetry; totals used
        provider_key = (provider or "unknown").lower()
        model_key = model or "unknown"
        capability_key = (capability or "general").strip() or "general"
        key = (provider_key, model_key, capability_key)
        hour = _hour_bucket()
        with self._lock:
            self._bump(
                self._by_model[key],
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                latency_ms=latency_ms,
                success=success,
                retry_count=retry_count,
                fallback_used=fallback_used,
            )
            self._bump(
                self._hourly[hour],
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                latency_ms=latency_ms,
                success=success,
                retry_count=retry_count,
                fallback_used=fallback_used,
            )
            self._bump(
                self._hourly_by_provider[(hour, provider_key)],
                total_tokens=total_tokens,
                estimated_cost_usd=estimated_cost_usd,
                latency_ms=latency_ms,
                success=success,
                retry_count=retry_count,
                fallback_used=fallback_used,
            )
            version = (prompt_version or "").strip()
            if version:
                self._prompt_versions[version] += 1
            self._prune_hourly_locked(keep_hours=168)

    @staticmethod
    def _bump(
        bucket: _AggregateBucket,
        *,
        total_tokens: int,
        estimated_cost_usd: float,
        latency_ms: float,
        success: bool,
        retry_count: int,
        fallback_used: bool,
    ) -> None:
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

    def _prune_hourly_locked(self, *, keep_hours: int) -> None:
        cutoff = _hour_bucket() - (keep_hours * 3600)
        stale = [h for h in self._hourly if h < cutoff]
        for hour in stale:
            del self._hourly[hour]
        stale_provider = [k for k in self._hourly_by_provider if k[0] < cutoff]
        for key in stale_provider:
            del self._hourly_by_provider[key]

    def summary(self, *, window_hours: int = 24) -> DashboardSummary:
        cutoff = _hour_bucket() - (max(int(window_hours), 1) * 3600)
        with self._lock:
            buckets = dict(self._by_model)
            prompt_versions = dict(self._prompt_versions)
            hourly = {h: b for h, b in self._hourly.items() if h >= cutoff}
            hourly_by_provider = {
                k: b for k, b in self._hourly_by_provider.items() if k[0] >= cutoff
            }

        # Prefer windowed hourly totals when available; else lifetime model buckets.
        if hourly:
            total_tokens = sum(b.tokens for b in hourly.values())
            total_cost = sum(b.cost for b in hourly.values())
            total_latency = sum(b.latency_sum for b in hourly.values())
            requests = sum(b.requests for b in hourly.values())
            errors = sum(b.errors for b in hourly.values())
            retries = sum(b.retries for b in hourly.values())
            fallbacks = sum(b.fallbacks for b in hourly.values())
            by_provider: dict[str, int] = defaultdict(int)
            for (_hour, provider), bucket in hourly_by_provider.items():
                by_provider[provider] += bucket.tokens
        else:
            total_tokens = total_cost = total_latency = 0.0
            requests = errors = retries = fallbacks = 0
            by_provider = defaultdict(int)
            for (provider, _model, _capability), bucket in buckets.items():
                total_tokens += bucket.tokens
                total_cost += bucket.cost
                total_latency += bucket.latency_sum
                requests += bucket.requests
                errors += bucket.errors
                retries += bucket.retries
                fallbacks += bucket.fallbacks
                by_provider[provider] += bucket.tokens

        by_model: dict[str, int] = defaultdict(int)
        by_capability: dict[str, int] = defaultdict(int)
        for (provider, model, capability), bucket in buckets.items():
            label = f"{provider}/{model}" if model else provider
            by_model[label] += bucket.tokens
            by_capability[capability] += bucket.tokens

        avg_latency = (total_latency / requests) if requests else 0.0
        return DashboardSummary(
            total_tokens=int(total_tokens),
            tokens_by_provider=dict(sorted(by_provider.items())),
            tokens_by_model=dict(sorted(by_model.items())),
            tokens_by_capability=dict(sorted(by_capability.items())),
            estimated_cost_usd=round(float(total_cost), 6),
            average_latency_ms=round(avg_latency, 2),
            error_rate=round(errors / requests, 4) if requests else 0.0,
            retry_rate=round(retries / requests, 4) if requests else 0.0,
            fallback_rate=round(fallbacks / requests, 4) if requests else 0.0,
            request_count=int(requests),
            window_hours=window_hours,
            prompt_versions=dict(sorted(prompt_versions.items())),
            source="process_local",
        )

    def model_comparison(self, *, window_hours: int = 24) -> list[ModelComparisonRow]:
        del window_hours  # model buckets are lifetime in-process; history uses hourly API
        with self._lock:
            buckets = dict(self._by_model)
        rows: list[ModelComparisonRow] = []
        for (provider, model, capability), bucket in sorted(buckets.items()):
            if bucket.requests <= 0:
                continue
            rows.append(
                ModelComparisonRow(
                    provider=provider,
                    model=model,
                    capability=capability,
                    request_count=bucket.requests,
                    average_latency_ms=round(bucket.latency_sum / bucket.requests, 2),
                    average_tokens=round(bucket.tokens / bucket.requests, 2),
                    estimated_cost_usd=round(bucket.cost, 6),
                    success_rate=round(bucket.successes / bucket.requests, 4),
                    error_rate=round(bucket.errors / bucket.requests, 4),
                    retry_rate=round(bucket.retries / bucket.requests, 4),
                    fallback_rate=round(bucket.fallbacks / bucket.requests, 4),
                )
            )
        return rows

    def history(self, *, window_hours: int = 24) -> AIMetricsHistory:
        period = 3600  # local store is hourly
        cutoff = _hour_bucket() - (max(int(window_hours), 1) * 3600)
        with self._lock:
            hourly = {h: b for h, b in self._hourly.items() if h >= cutoff}
            by_provider_raw = {
                k: b for k, b in self._hourly_by_provider.items() if k[0] >= cutoff
            }
            prompt_versions = dict(self._prompt_versions)

        hours = sorted(hourly)
        tokens = [_series_point(h, float(hourly[h].tokens)) for h in hours]
        cost = [_series_point(h, float(hourly[h].cost)) for h in hours]
        latency = [
            _series_point(
                h,
                (hourly[h].latency_sum / hourly[h].requests) if hourly[h].requests else 0.0,
            )
            for h in hours
        ]
        successes = [_series_point(h, float(hourly[h].successes)) for h in hours]
        errors = [_series_point(h, float(hourly[h].errors)) for h in hours]
        retries = [_series_point(h, float(hourly[h].retries)) for h in hours]
        fallbacks = [_series_point(h, float(hourly[h].fallbacks)) for h in hours]

        provider_acc: dict[str, _AggregateBucket] = defaultdict(_AggregateBucket)
        for (_hour, provider), bucket in by_provider_raw.items():
            acc = provider_acc[provider]
            acc.requests += bucket.requests
            acc.successes += bucket.successes
            acc.errors += bucket.errors
            acc.retries += bucket.retries
            acc.fallbacks += bucket.fallbacks
            acc.tokens += bucket.tokens
            acc.cost += bucket.cost
            acc.latency_sum += bucket.latency_sum

        by_provider = [
            ProviderHistoryRow(
                provider=provider,
                tokens=float(bucket.tokens),
                estimated_cost_usd=round(bucket.cost, 6),
                average_latency_ms=round(
                    (bucket.latency_sum / bucket.requests) if bucket.requests else 0.0, 2
                ),
                success_count=float(bucket.successes),
                error_count=float(bucket.errors),
                retry_count=float(bucket.retries),
                fallback_count=float(bucket.fallbacks),
                request_count=float(bucket.requests),
                success_rate=round(bucket.successes / bucket.requests, 4)
                if bucket.requests
                else 0.0,
            )
            for provider, bucket in sorted(provider_acc.items())
        ]

        return AIMetricsHistory(
            source="process_local",
            window_hours=window_hours,
            period_seconds=period,
            tokens=tokens,
            cost_usd=cost,
            latency_ms=latency,
            successes=successes,
            errors=errors,
            retries=retries,
            fallbacks=fallbacks,
            by_provider=by_provider,
            prompt_versions=dict(sorted(prompt_versions.items())),
        )

    def reset(self) -> None:
        with self._lock:
            self._by_model.clear()
            self._hourly.clear()
            self._hourly_by_provider.clear()
            self._prompt_versions.clear()
            self._started_at = time.time()


def _series_point(hour_epoch: int, value: float) -> HistorySeriesPoint:
    ts = datetime.fromtimestamp(hour_epoch, tz=timezone.utc).isoformat()
    return HistorySeriesPoint(timestamp=ts, value=round(float(value), 6))


def _cw_points_to_series(points: list[MetricPoint]) -> list[HistorySeriesPoint]:
    return [
        HistorySeriesPoint(
            timestamp=p.timestamp.astimezone(timezone.utc).isoformat(),
            value=round(float(p.value), 6),
        )
        for p in points
    ]


def _history_from_cloudwatch(
    cw: CloudWatchHistoryResult,
    *,
    prompt_versions: dict[str, int],
) -> AIMetricsHistory:
    by_provider = [
        ProviderHistoryRow(
            provider=row.provider,
            tokens=float(row.tokens),
            estimated_cost_usd=round(float(row.cost_usd), 6),
            average_latency_ms=round(float(row.average_latency_ms), 2),
            success_count=float(row.successes),
            error_count=float(row.errors),
            retry_count=float(row.retries),
            fallback_count=float(row.fallbacks),
            request_count=float(row.sample_count),
            success_rate=round(row.successes / row.sample_count, 4)
            if row.sample_count
            else 0.0,
        )
        for row in cw.by_provider
    ]
    return AIMetricsHistory(
        source="cloudwatch",
        window_hours=cw.window_hours,
        period_seconds=cw.period_seconds,
        tokens=_cw_points_to_series(cw.tokens),
        cost_usd=_cw_points_to_series(cw.cost_usd),
        latency_ms=_cw_points_to_series(cw.latency_ms),
        successes=_cw_points_to_series(cw.successes),
        errors=_cw_points_to_series(cw.errors),
        retries=_cw_points_to_series(cw.retries),
        fallbacks=_cw_points_to_series(cw.fallbacks),
        by_provider=by_provider,
        prompt_versions=prompt_versions,
    )


_PROCESS_STORE = InMemoryAIMetricsStore()


class AIMetricsRecorder:
    """Record AI call aggregates and optionally emit/read CloudWatch custom metrics."""

    def __init__(
        self,
        settings: Settings,
        store: InMemoryAIMetricsStore | None = None,
        cloudwatch_reader: CloudWatchAIMetricsReader | None = None,
    ) -> None:
        self._settings = settings
        self._store = store or _PROCESS_STORE
        self._cw_client: Any | None = None
        self._cw_reader = cloudwatch_reader

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
        prompt_version: str = "",
    ) -> None:
        self._store.record(
            provider=provider,
            model=model,
            capability=capability,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            latency_ms=latency_ms,
            success=success,
            retry_count=retry_count,
            fallback_used=fallback_used,
            prompt_version=prompt_version,
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
        return self._store.summary(window_hours=window_hours)

    def model_comparison(self, *, window_hours: int = 24) -> list[ModelComparisonRow]:
        return self._store.model_comparison(window_hours=window_hours)

    def history(self, *, window_hours: int = 24) -> AIMetricsHistory:
        """Prefer CloudWatch history; fall back to process-local hourly buckets."""
        local = self._store.history(window_hours=window_hours)
        if not self._settings.cloudwatch_enabled:
            return local
        try:
            reader = self._reader()
            cw = reader.fetch_history(window_hours=window_hours)
            has_series = any(
                (
                    cw.tokens,
                    cw.cost_usd,
                    cw.latency_ms,
                    cw.successes,
                    cw.errors,
                    cw.retries,
                    cw.fallbacks,
                )
            )
            if has_series or cw.by_provider:
                return _history_from_cloudwatch(cw, prompt_versions=local.prompt_versions)
            # CW reachable but empty — keep real process-local samples when present.
            if local.tokens or local.by_provider:
                return local
            return _history_from_cloudwatch(cw, prompt_versions=local.prompt_versions)
        except Exception:  # noqa: BLE001 — never break the dashboard
            logger.debug("CloudWatch AI history read failed; using process_local", exc_info=True)
            return local

    def _reader(self) -> CloudWatchAIMetricsReader:
        if self._cw_reader is None:
            self._cw_reader = CloudWatchAIMetricsReader(self._settings)
        return self._cw_reader

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


__all__ = [
    "AIMetricsHistory",
    "AIMetricsRecorder",
    "DashboardSummary",
    "HistorySeriesPoint",
    "InMemoryAIMetricsStore",
    "ModelComparisonRow",
    "ProviderHistoryRow",
    "choose_period_seconds",
    "get_ai_metrics_recorder",
    "reset_ai_metrics_for_tests",
]
