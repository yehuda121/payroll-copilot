"""Unit tests for AI telemetry wrapper, pricing, and popular-question normalization."""

from __future__ import annotations

import pytest

from payroll_copilot.application.ports import CompletionResult, Message
from payroll_copilot.infrastructure.ai.ai_call_context import ai_call_context
from payroll_copilot.infrastructure.ai.ai_metrics import reset_ai_metrics_for_tests
from payroll_copilot.infrastructure.ai.pricing import estimate_cost_usd
from payroll_copilot.infrastructure.ai.telemetry_provider import TelemetryModelProvider
from payroll_copilot.infrastructure.persistence.dynamodb.popular_questions import (
    normalize_question,
    question_hash,
    rank_sort_key,
    strip_session_context,
)


class _StubProvider:
    embedding_dimensions = 8

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, **kwargs):
        self.calls += 1
        return CompletionResult(
            content="ok",
            confidence=0.9,
            model="stub-model",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            tokens_used=15,
            provider="stub",
        )

    async def complete_structured(self, messages, response_schema, **kwargs):
        raise NotImplementedError

    async def embed(self, texts):
        return [[0.0] * 8 for _ in texts]


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_ai_metrics_for_tests()
    yield
    reset_ai_metrics_for_tests()


@pytest.mark.asyncio
async def test_telemetry_wrapper_normalizes_usage_and_records_metrics() -> None:
    wrapped = TelemetryModelProvider(
        _StubProvider(),
        provider_name="openai",
        default_model="gpt-4o-mini",
    )
    with ai_call_context(capability="assistant") as ctx:
        result = await wrapped.complete([Message(role="user", content="hi")])
        usage = ctx.aggregated_usage()

    assert result.provider == "openai"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.total_tokens == 15
    assert result.usage is not None
    assert usage is not None
    assert usage.total_tokens == 15
    assert usage.latency_ms >= 0


def test_estimate_cost_zero_for_ollama() -> None:
    assert estimate_cost_usd(
        provider="ollama",
        model="llama3.1:8b",
        prompt_tokens=1000,
        completion_tokens=1000,
    ) == 0.0


def test_normalize_question_strips_session_and_punctuation() -> None:
    raw = "What is overtime?  \n\n[Session context — do not invent documents]\nUploaded payslip"
    assert strip_session_context(raw) == "What is overtime?"
    assert normalize_question(raw) == "what is overtime"
    assert question_hash("what is overtime") == question_hash(normalize_question(raw))
    assert rank_sort_key(12, "abc") == "0000000000000012#abc"
