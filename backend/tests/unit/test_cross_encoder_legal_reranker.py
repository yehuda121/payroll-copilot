"""Unit tests for CrossEncoderLegalChunkReranker — no real model download."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from payroll_copilot.infrastructure.rag.cross_encoder_legal_reranker import (
    CrossEncoderLegalChunkReranker,
    reset_legal_rerank_model_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    reset_legal_rerank_model_cache()
    yield
    reset_legal_rerank_model_cache()


def test_cross_encoder_reorders_by_descending_score() -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.2, 0.1, 0.9]
    candidates = [
        {"chunk_id": "a", "text": "ta", "rule_id": "r.a"},
        {"chunk_id": "b", "text": "tb", "rule_id": "r.b"},
        {"chunk_id": "c", "text": "tc", "rule_id": "r.c"},
    ]
    with patch.dict(
        "payroll_copilot.infrastructure.rag.cross_encoder_legal_reranker._MODEL_CACHE",
        {"BAAI/bge-reranker-v2-m3": fake_model},
    ):
        reranker = CrossEncoderLegalChunkReranker(model_id="BAAI/bge-reranker-v2-m3")
        out = list(reranker.rerank("minimum wage", candidates))
    assert [r["chunk_id"] for r in out] == ["c", "a", "b"]
    assert out[0]["rerank_score"] == pytest.approx(0.9)
    assert out[0]["rule_id"] == "r.c"
    fake_model.predict.assert_called_once()


def test_cross_encoder_rejects_nan_scores() -> None:
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.1, float("nan")]
    candidates = [
        {"chunk_id": "a", "text": "ta"},
        {"chunk_id": "b", "text": "tb"},
    ]
    with patch.dict(
        "payroll_copilot.infrastructure.rag.cross_encoder_legal_reranker._MODEL_CACHE",
        {"m": fake_model},
    ):
        reranker = CrossEncoderLegalChunkReranker(model_id="m")
        with pytest.raises(ValueError, match="non_finite"):
            reranker.rerank("q", candidates)


def test_cross_encoder_missing_dependency_fails_clearly() -> None:
    reranker = CrossEncoderLegalChunkReranker(model_id="missing-dep-model")

    import builtins

    real_import = builtins.__import__

    def blocked(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == "sentence_transformers":
            raise ModuleNotFoundError("No module named 'sentence_transformers'")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=blocked):
        with pytest.raises(RuntimeError, match="sentence_transformers_unavailable"):
            reranker.ensure_loaded()
