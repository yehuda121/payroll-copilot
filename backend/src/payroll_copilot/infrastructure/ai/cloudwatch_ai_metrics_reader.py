"""CloudWatch GetMetricData reader for AI observability historical series.

Reads the same custom metrics emitted by AIMetricsRecorder.PutMetricData.
Does not invent values — empty results mean no published datapoints in range.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from payroll_copilot.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)

# Must match PutMetricData MetricName values in AIMetricsRecorder.
CW_METRIC_TOKENS = "AITokens"
CW_METRIC_COST = "AICostUSD"
CW_METRIC_LATENCY = "AILatencyMs"
CW_METRIC_SUCCESS = "AISuccess"
CW_METRIC_ERROR = "AIError"
CW_METRIC_RETRY = "AIRetry"
CW_METRIC_FALLBACK = "AIFallback"

# Dimension names on emitted metrics (alphabetical for SEARCH).
_DIM_SET = "Capability,Model,Provider"


@dataclass(slots=True)
class MetricPoint:
    timestamp: datetime
    value: float


@dataclass(slots=True)
class ProviderMetricSlice:
    provider: str
    tokens: float = 0.0
    cost_usd: float = 0.0
    average_latency_ms: float = 0.0
    successes: float = 0.0
    errors: float = 0.0
    retries: float = 0.0
    fallbacks: float = 0.0
    sample_count: float = 0.0


@dataclass(slots=True)
class CloudWatchHistoryResult:
    """Aggregated history from CloudWatch; empty series when no data."""

    window_hours: int
    period_seconds: int
    namespace: str
    tokens: list[MetricPoint] = field(default_factory=list)
    cost_usd: list[MetricPoint] = field(default_factory=list)
    latency_ms: list[MetricPoint] = field(default_factory=list)
    successes: list[MetricPoint] = field(default_factory=list)
    errors: list[MetricPoint] = field(default_factory=list)
    retries: list[MetricPoint] = field(default_factory=list)
    fallbacks: list[MetricPoint] = field(default_factory=list)
    by_provider: list[ProviderMetricSlice] = field(default_factory=list)


def choose_period_seconds(window_hours: int) -> int:
    """Pick a CloudWatch period that keeps datapoint counts reasonable."""
    if window_hours <= 6:
        return 300  # 5 min
    if window_hours <= 48:
        return 3600  # 1 hour
    return 21600  # 6 hours


class CloudWatchAIMetricsReader:
    """Thin GetMetricData client for AI custom metrics."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._settings = settings
        self._client = client
        self._namespace = settings.cloudwatch_metrics_namespace or "PayrollCopilot"

    def fetch_history(self, *, window_hours: int) -> CloudWatchHistoryResult:
        period = choose_period_seconds(window_hours)
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=window_hours)
        client = self._cloudwatch()

        result = CloudWatchHistoryResult(
            window_hours=window_hours,
            period_seconds=period,
            namespace=self._namespace,
        )

        # Aggregate totals across all Provider/Model/Capability dimension sets.
        queries = [
            ("tokens", CW_METRIC_TOKENS, "Sum", "SUM", True),
            ("cost", CW_METRIC_COST, "Sum", "SUM", True),
            ("latency", CW_METRIC_LATENCY, "Average", "AVG", True),
            ("success", CW_METRIC_SUCCESS, "Sum", "SUM", True),
            ("error", CW_METRIC_ERROR, "Sum", "SUM", True),
            ("retry", CW_METRIC_RETRY, "Sum", "SUM", True),
            ("fallback", CW_METRIC_FALLBACK, "Sum", "SUM", True),
        ]
        metric_queries: list[dict[str, Any]] = []
        for metric_id, metric_name, stat, reducer, return_data in queries:
            search = (
                f"SEARCH('{{{self._namespace},{_DIM_SET}}} MetricName=\"{metric_name}\"', "
                f"'{stat}', {period})"
            )
            metric_queries.append(
                {
                    "Id": f"raw_{metric_id}",
                    "Expression": search,
                    "ReturnData": False,
                }
            )
            metric_queries.append(
                {
                    "Id": metric_id,
                    "Expression": f"{reducer}(raw_{metric_id})",
                    "ReturnData": return_data,
                }
            )

        # Provider breakdown: return SEARCH series for tokens so we can group by Provider.
        metric_queries.append(
            {
                "Id": "provider_tokens",
                "Expression": (
                    f"SEARCH('{{{self._namespace},{_DIM_SET}}} MetricName=\"{CW_METRIC_TOKENS}\"', "
                    f"'Sum', {period})"
                ),
                "ReturnData": True,
            }
        )
        metric_queries.append(
            {
                "Id": "provider_cost",
                "Expression": (
                    f"SEARCH('{{{self._namespace},{_DIM_SET}}} MetricName=\"{CW_METRIC_COST}\"', "
                    f"'Sum', {period})"
                ),
                "ReturnData": True,
            }
        )
        metric_queries.append(
            {
                "Id": "provider_latency",
                "Expression": (
                    f"SEARCH('{{{self._namespace},{_DIM_SET}}} MetricName=\"{CW_METRIC_LATENCY}\"', "
                    f"'Average', {period})"
                ),
                "ReturnData": True,
            }
        )
        metric_queries.append(
            {
                "Id": "provider_success",
                "Expression": (
                    f"SEARCH('{{{self._namespace},{_DIM_SET}}} MetricName=\"{CW_METRIC_SUCCESS}\"', "
                    f"'Sum', {period})"
                ),
                "ReturnData": True,
            }
        )
        metric_queries.append(
            {
                "Id": "provider_error",
                "Expression": (
                    f"SEARCH('{{{self._namespace},{_DIM_SET}}} MetricName=\"{CW_METRIC_ERROR}\"', "
                    f"'Sum', {period})"
                ),
                "ReturnData": True,
            }
        )
        metric_queries.append(
            {
                "Id": "provider_retry",
                "Expression": (
                    f"SEARCH('{{{self._namespace},{_DIM_SET}}} MetricName=\"{CW_METRIC_RETRY}\"', "
                    f"'Sum', {period})"
                ),
                "ReturnData": True,
            }
        )
        metric_queries.append(
            {
                "Id": "provider_fallback",
                "Expression": (
                    f"SEARCH('{{{self._namespace},{_DIM_SET}}} MetricName=\"{CW_METRIC_FALLBACK}\"', "
                    f"'Sum', {period})"
                ),
                "ReturnData": True,
            }
        )

        response = client.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=start,
            EndTime=end,
            ScanBy="TimestampAscending",
        )

        results_by_id: dict[str, list[dict[str, Any]]] = {}
        for entry in response.get("MetricDataResults", []):
            results_by_id.setdefault(entry.get("Id", ""), []).append(entry)

        result.tokens = _points_from_results(results_by_id.get("tokens", []))
        result.cost_usd = _points_from_results(results_by_id.get("cost", []))
        result.latency_ms = _points_from_results(results_by_id.get("latency", []))
        result.successes = _points_from_results(results_by_id.get("success", []))
        result.errors = _points_from_results(results_by_id.get("error", []))
        result.retries = _points_from_results(results_by_id.get("retry", []))
        result.fallbacks = _points_from_results(results_by_id.get("fallback", []))
        result.by_provider = _provider_slices_from_search(
            tokens=results_by_id.get("provider_tokens", []),
            cost=results_by_id.get("provider_cost", []),
            latency=results_by_id.get("provider_latency", []),
            success=results_by_id.get("provider_success", []),
            error=results_by_id.get("provider_error", []),
            retry=results_by_id.get("provider_retry", []),
            fallback=results_by_id.get("provider_fallback", []),
        )
        return result

    def _cloudwatch(self) -> Any:
        if self._client is not None:
            return self._client
        import boto3

        self._client = boto3.client(
            "cloudwatch",
            region_name=self._settings.aws_region or "us-east-1",
        )
        return self._client


def _points_from_results(entries: list[dict[str, Any]]) -> list[MetricPoint]:
    points: list[MetricPoint] = []
    for entry in entries:
        timestamps = entry.get("Timestamps") or []
        values = entry.get("Values") or []
        for ts, value in zip(timestamps, values, strict=False):
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                points.append(MetricPoint(timestamp=ts, value=float(value)))
    points.sort(key=lambda p: p.timestamp)
    return points


def _provider_from_label(label: str | None) -> str:
    """Extract Provider from CloudWatch SEARCH label when possible.

    Typical label examples:
    - \"AITokens, assistant, gpt-4o-mini, openai\"
    - \"openai\"
    """
    if not label:
        return "unknown"
    parts = [p.strip() for p in str(label).split(",") if p.strip()]
    if not parts:
        return "unknown"
    # Prefer last token (Provider is last in alphabetical dim listing for SEARCH labels).
    candidate = parts[-1].lower()
    if candidate.lower() in {m.lower() for m in (
        CW_METRIC_TOKENS,
        CW_METRIC_COST,
        CW_METRIC_LATENCY,
        CW_METRIC_SUCCESS,
        CW_METRIC_ERROR,
        CW_METRIC_RETRY,
        CW_METRIC_FALLBACK,
    )}:
        return "unknown"
    return candidate


def _sum_values(entries: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for entry in entries:
        provider = _provider_from_label(entry.get("Label"))
        values = entry.get("Values") or []
        totals[provider] = totals.get(provider, 0.0) + float(sum(values))
    return totals


def _avg_values(entries: list[dict[str, Any]]) -> dict[str, float]:
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for entry in entries:
        provider = _provider_from_label(entry.get("Label"))
        values = [float(v) for v in (entry.get("Values") or [])]
        if not values:
            continue
        sums[provider] = sums.get(provider, 0.0) + sum(values)
        counts[provider] = counts.get(provider, 0) + len(values)
    return {
        provider: (sums[provider] / counts[provider]) if counts.get(provider) else 0.0
        for provider in sums
    }


def _provider_slices_from_search(
    *,
    tokens: list[dict[str, Any]],
    cost: list[dict[str, Any]],
    latency: list[dict[str, Any]],
    success: list[dict[str, Any]],
    error: list[dict[str, Any]],
    retry: list[dict[str, Any]],
    fallback: list[dict[str, Any]],
) -> list[ProviderMetricSlice]:
    token_totals = _sum_values(tokens)
    cost_totals = _sum_values(cost)
    latency_avgs = _avg_values(latency)
    success_totals = _sum_values(success)
    error_totals = _sum_values(error)
    retry_totals = _sum_values(retry)
    fallback_totals = _sum_values(fallback)

    providers = sorted(
        set(token_totals)
        | set(cost_totals)
        | set(latency_avgs)
        | set(success_totals)
        | set(error_totals)
        | set(retry_totals)
        | set(fallback_totals)
    )
    slices: list[ProviderMetricSlice] = []
    for provider in providers:
        successes = success_totals.get(provider, 0.0)
        errors = error_totals.get(provider, 0.0)
        samples = successes + errors
        slices.append(
            ProviderMetricSlice(
                provider=provider,
                tokens=token_totals.get(provider, 0.0),
                cost_usd=cost_totals.get(provider, 0.0),
                average_latency_ms=latency_avgs.get(provider, 0.0),
                successes=successes,
                errors=errors,
                retries=retry_totals.get(provider, 0.0),
                fallbacks=fallback_totals.get(provider, 0.0),
                sample_count=samples,
            )
        )
    return slices
