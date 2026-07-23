"""Unit tests for AI observability metrics store and CloudWatch history reader."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from payroll_copilot.infrastructure.ai.ai_metrics import (
    AIMetricsRecorder,
    InMemoryAIMetricsStore,
)
from payroll_copilot.infrastructure.ai.cloudwatch_ai_metrics_reader import (
    CloudWatchAIMetricsReader,
    choose_period_seconds,
)


def _settings(**overrides):
    base = {
        "cloudwatch_enabled": True,
        "cloudwatch_metrics_namespace": "PayrollCopilot",
        "aws_region": "us-east-1",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_choose_period_seconds() -> None:
    assert choose_period_seconds(3) == 300
    assert choose_period_seconds(24) == 3600
    assert choose_period_seconds(100) == 21600


def test_in_memory_store_records_hourly_history_and_capability() -> None:
    store = InMemoryAIMetricsStore()
    store.record(
        provider="openai",
        model="gpt-4o-mini",
        capability="assistant",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        estimated_cost_usd=0.001,
        latency_ms=120.0,
        success=True,
        retry_count=1,
        fallback_used=False,
        prompt_version="payslip-v2",
    )
    store.record(
        provider="ollama",
        model="llama",
        capability="rag",
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=20,
        estimated_cost_usd=0.0,
        latency_ms=80.0,
        success=False,
        retry_count=0,
        fallback_used=True,
        prompt_version="",
    )

    summary = store.summary(window_hours=24)
    assert summary.request_count == 2
    assert summary.tokens_by_capability["assistant"] == 15
    assert summary.tokens_by_capability["rag"] == 20
    assert summary.prompt_versions == {"payslip-v2": 1}
    assert summary.error_rate == pytest.approx(0.5)
    assert summary.retry_rate == pytest.approx(0.5)
    assert summary.fallback_rate == pytest.approx(0.5)

    history = store.history(window_hours=24)
    assert history.source == "process_local"
    assert len(history.tokens) == 1
    assert history.tokens[0].value == 35
    assert {row.provider for row in history.by_provider} == {"openai", "ollama"}

    rows = store.model_comparison(window_hours=24)
    assert len(rows) == 2
    openai_row = next(r for r in rows if r.provider == "openai")
    assert openai_row.capability == "assistant"
    assert openai_row.retry_rate == 1.0


def test_recorder_history_falls_back_when_cloudwatch_disabled() -> None:
    store = InMemoryAIMetricsStore()
    store.record(
        provider="openai",
        model="m",
        capability="general",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        estimated_cost_usd=0.0,
        latency_ms=10.0,
        success=True,
        retry_count=0,
        fallback_used=False,
    )
    recorder = AIMetricsRecorder(_settings(cloudwatch_enabled=False), store=store)
    history = recorder.history(window_hours=24)
    assert history.source == "process_local"
    assert history.tokens[0].value == 2


def test_recorder_history_uses_cloudwatch_when_available() -> None:
    store = InMemoryAIMetricsStore()
    store.record(
        provider="openai",
        model="m",
        capability="general",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=99,
        estimated_cost_usd=0.0,
        latency_ms=10.0,
        success=True,
        retry_count=0,
        fallback_used=False,
        prompt_version="v1",
    )

    ts = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)

    class _FakeCW:
        def get_metric_data(self, **kwargs):
            del kwargs
            return {
                "MetricDataResults": [
                    {"Id": "tokens", "Timestamps": [ts], "Values": [42.0], "Label": "tokens"},
                    {"Id": "cost", "Timestamps": [ts], "Values": [0.5], "Label": "cost"},
                    {"Id": "latency", "Timestamps": [ts], "Values": [100.0], "Label": "latency"},
                    {"Id": "success", "Timestamps": [ts], "Values": [3.0], "Label": "success"},
                    {"Id": "error", "Timestamps": [ts], "Values": [1.0], "Label": "error"},
                    {"Id": "retry", "Timestamps": [ts], "Values": [1.0], "Label": "retry"},
                    {"Id": "fallback", "Timestamps": [ts], "Values": [0.0], "Label": "fallback"},
                    {
                        "Id": "provider_tokens",
                        "Timestamps": [ts],
                        "Values": [42.0],
                        "Label": "AITokens, general, m, openai",
                    },
                    {
                        "Id": "provider_cost",
                        "Timestamps": [ts],
                        "Values": [0.5],
                        "Label": "AICostUSD, general, m, openai",
                    },
                    {
                        "Id": "provider_latency",
                        "Timestamps": [ts],
                        "Values": [100.0],
                        "Label": "AILatencyMs, general, m, openai",
                    },
                    {
                        "Id": "provider_success",
                        "Timestamps": [ts],
                        "Values": [3.0],
                        "Label": "AISuccess, general, m, openai",
                    },
                    {
                        "Id": "provider_error",
                        "Timestamps": [ts],
                        "Values": [1.0],
                        "Label": "AIError, general, m, openai",
                    },
                    {
                        "Id": "provider_retry",
                        "Timestamps": [ts],
                        "Values": [1.0],
                        "Label": "AIRetry, general, m, openai",
                    },
                    {
                        "Id": "provider_fallback",
                        "Timestamps": [ts],
                        "Values": [0.0],
                        "Label": "AIFallback, general, m, openai",
                    },
                ]
            }

    reader = CloudWatchAIMetricsReader(
        _settings(cloudwatch_metrics_namespace="TestNS"),
        client=_FakeCW(),
    )
    recorder = AIMetricsRecorder(
        _settings(cloudwatch_enabled=True, cloudwatch_metrics_namespace="TestNS"),
        store=store,
        cloudwatch_reader=reader,
    )
    history = recorder.history(window_hours=24)
    assert history.source == "cloudwatch"
    assert history.tokens[0].value == 42.0
    assert history.prompt_versions == {"v1": 1}
    assert history.by_provider[0].provider == "openai"
    assert history.by_provider[0].request_count == 4.0


def test_cloudwatch_reader_parses_empty_results() -> None:
    class _EmptyCW:
        def get_metric_data(self, **kwargs):
            del kwargs
            return {"MetricDataResults": []}

    reader = CloudWatchAIMetricsReader(_settings(), client=_EmptyCW())
    result = reader.fetch_history(window_hours=24)
    assert result.tokens == []
    assert result.by_provider == []


def test_recorder_history_falls_back_on_cloudwatch_error() -> None:
    store = InMemoryAIMetricsStore()
    store.record(
        provider="openai",
        model="m",
        capability="general",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=7,
        estimated_cost_usd=0.0,
        latency_ms=10.0,
        success=True,
        retry_count=0,
        fallback_used=False,
    )

    class _Boom:
        def get_metric_data(self, **kwargs):
            raise RuntimeError("no aws")

    reader = CloudWatchAIMetricsReader(_settings(), client=_Boom())
    recorder = AIMetricsRecorder(
        _settings(cloudwatch_enabled=True),
        store=store,
        cloudwatch_reader=reader,
    )
    history = recorder.history(window_hours=24)
    assert history.source == "process_local"
    assert history.tokens[0].value == 7
