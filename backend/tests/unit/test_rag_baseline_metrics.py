"""Unit tests for Phase-1 RAG baseline retrieval metrics / invalid modes."""

from __future__ import annotations

import math

from payroll_copilot.application.dto.legal_knowledge import RagEvalMetricValue
from payroll_copilot.application.services.rag_evaluation import (
    _INVALID_VECTOR_MODES,
    _aggregate,
    _retrieval_metrics,
)


def test_retrieval_metrics_hit_recall_mrr() -> None:
    metrics = _retrieval_metrics(
        expected_rules=["legal.minimum_wage", "legal.overtime.daily_limit"],
        retrieved_rule_ids=[
            "legal.pension.contribution",
            "legal.minimum_wage",
            "legal.overtime.daily_limit",
        ],
        k=5,
    )
    assert metrics["hit_at_k"] is True
    assert metrics["first_relevant_rank"] == 2
    assert metrics["mrr"] == 0.5
    assert metrics["recall_at_k"] == 1.0


def test_retrieval_metrics_miss() -> None:
    metrics = _retrieval_metrics(
        expected_rules=["legal.minimum_wage"],
        retrieved_rule_ids=["legal.pension.contribution"],
        k=5,
    )
    assert metrics["hit_at_k"] is False
    assert metrics["first_relevant_rank"] is None
    assert metrics["mrr"] == 0.0
    assert metrics["recall_at_k"] == 0.0


def test_retrieval_metrics_no_expected() -> None:
    metrics = _retrieval_metrics(expected_rules=[], retrieved_rule_ids=["a"], k=5)
    assert metrics["hit_at_k"] is None
    assert metrics["mrr"] is None


def test_invalid_vector_modes_include_unavailable() -> None:
    assert "unavailable" in _INVALID_VECTOR_MODES
    assert "yaml_fallback" in _INVALID_VECTOR_MODES


def test_aggregate_skips_nan_scores() -> None:
    agg = _aggregate(
        [
            RagEvalMetricValue(value=0.5, status="ok"),
            RagEvalMetricValue(value=float("nan"), status="ok"),
            RagEvalMetricValue(value=1.0, status="ok"),
        ]
    )
    assert agg.status == "ok"
    assert agg.value == 0.75
    assert not math.isnan(agg.value or 0.0)


def test_aggregate_all_nan_is_unavailable() -> None:
    agg = _aggregate([RagEvalMetricValue(value=float("nan"), status="ok")])
    assert agg.status == "unavailable"
