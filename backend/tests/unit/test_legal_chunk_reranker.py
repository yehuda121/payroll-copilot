"""Phase 2: legal chunk reranker abstraction + disabled-path compatibility."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Sequence
from unittest.mock import MagicMock

import pytest

from payroll_copilot.application.dto.legal_knowledge import IndexedChunkMeta
from payroll_copilot.application.services.legal_chunk_reranker import (
    FailOpenLegalChunkReranker,
    NoOpLegalChunkReranker,
    apply_rerank_fail_open,
    sanitize_authorized_rerank_result,
)
from payroll_copilot.application.services.version_aware_legal_retriever import (
    VersionAwareLegalRetriever,
)
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import LegalKnowledgeStore
from payroll_copilot.infrastructure.rag.legal_reranker_factory import build_legal_chunk_reranker
from payroll_copilot.infrastructure.rag.numpy_vector_store import NumpyLegalVectorStore


class _FakeEmbedModel:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


class _ReverseReranker:
    """Deterministic fake: reverses authorized candidates."""

    def rerank(self, query: str, candidates: Sequence[dict[str, Any]]):
        return list(reversed(list(candidates)))


class _ForeignReranker:
    def rerank(self, query: str, candidates: Sequence[dict[str, Any]]):
        return [{"chunk_id": "foreign-not-authorized", "text": "injected"}]


class _EmptyReranker:
    def rerank(self, query: str, candidates: Sequence[dict[str, Any]]):
        return []


class _ExplodingReranker:
    def rerank(self, query: str, candidates: Sequence[dict[str, Any]]):
        raise RuntimeError("boom")


class _MutatingReranker:
    """Tries to rewrite metadata; sanitizer must restore authorized fields."""

    def rerank(self, query: str, candidates: Sequence[dict[str, Any]]):
        out = []
        for c in candidates:
            forged = dict(c)
            forged["text"] = "FORGED"
            forged["rule_id"] = "forged.rule"
            out.append(forged)
        return list(reversed(out))


def _candidate(cid: str, rule_id: str, score: float) -> dict[str, Any]:
    return {
        "chunk_id": cid,
        "rule_id": rule_id,
        "rule_version": "1",
        "title": rule_id,
        "section": "body",
        "text": f"text-{cid}",
        "score": score,
        "valid_from": "2026-01-01",
        "valid_to": None,
        "scope": "general",
        "approval_status": "approved",
    }


def test_disabled_factory_loads_no_reranker() -> None:
    settings = MagicMock()
    settings.legal_rag_rerank_enabled = False
    assert build_legal_chunk_reranker(settings) is None


def test_enabled_factory_uses_noop_placeholder_not_external_model() -> None:
    settings = MagicMock()
    settings.legal_rag_rerank_enabled = True
    settings.legal_rag_rerank_model = "noop"
    settings.legal_rag_rerank_timeout_ms = 250
    settings.legal_rag_rerank_device = ""
    reranker = build_legal_chunk_reranker(settings)
    assert isinstance(reranker, FailOpenLegalChunkReranker)
    assert isinstance(reranker._inner, NoOpLegalChunkReranker)


def test_enabled_factory_selects_cross_encoder_adapter() -> None:
    settings = MagicMock()
    settings.legal_rag_rerank_enabled = True
    settings.legal_rag_rerank_model = "BAAI/bge-reranker-v2-m3"
    settings.legal_rag_rerank_timeout_ms = 15000
    settings.legal_rag_rerank_device = "cpu"
    reranker = build_legal_chunk_reranker(settings)
    assert isinstance(reranker, FailOpenLegalChunkReranker)
    from payroll_copilot.infrastructure.rag.cross_encoder_legal_reranker import (
        CrossEncoderLegalChunkReranker,
    )

    assert isinstance(reranker._inner, CrossEncoderLegalChunkReranker)
    assert reranker._inner.model_id == "BAAI/bge-reranker-v2-m3"


def test_disabled_flag_preserves_vector_ordering() -> None:
    candidates = [
        _candidate("a", "legal.a", 0.9),
        _candidate("b", "legal.b", 0.8),
        _candidate("c", "legal.c", 0.7),
    ]
    hits, diag = apply_rerank_fail_open(
        query="q",
        candidates=candidates,
        reranker=None,
        final_n=5,
    )
    assert [h["chunk_id"] for h in hits] == ["a", "b", "c"]
    assert diag["rerank_fallback"] is False
    assert diag["order_changed"] is False
    assert diag["retrieval_candidate_count"] == 3
    assert diag["final_chunk_count"] == 3


def test_fake_reranker_changes_ordering() -> None:
    candidates = [
        _candidate("a", "legal.a", 0.9),
        _candidate("b", "legal.b", 0.8),
        _candidate("c", "legal.c", 0.7),
    ]
    hits, diag = apply_rerank_fail_open(
        query="q",
        candidates=candidates,
        reranker=_ReverseReranker(),
        final_n=5,
    )
    assert [h["chunk_id"] for h in hits] == ["c", "b", "a"]
    assert diag["order_changed"] is True
    assert diag["rerank_fallback"] is False


def test_top_n_is_respected() -> None:
    candidates = [_candidate(str(i), f"r.{i}", 1.0 - i * 0.1) for i in range(6)]
    hits, diag = apply_rerank_fail_open(
        query="q",
        candidates=candidates,
        reranker=_ReverseReranker(),
        final_n=2,
    )
    assert [h["chunk_id"] for h in hits] == ["5", "4"]
    assert diag["final_chunk_count"] == 2
    assert diag["retrieval_candidate_count"] == 6


def test_metadata_preserved_after_rerank() -> None:
    candidates = [
        _candidate("a", "legal.a", 0.9),
        _candidate("b", "legal.b", 0.8),
    ]
    hits, _ = apply_rerank_fail_open(
        query="q",
        candidates=candidates,
        reranker=_MutatingReranker(),
        final_n=5,
    )
    assert [h["chunk_id"] for h in hits] == ["b", "a"]
    assert hits[0]["text"] == "text-b"
    assert hits[0]["rule_id"] == "legal.b"
    assert hits[1]["text"] == "text-a"
    assert hits[1]["rule_id"] == "legal.a"


def test_reranker_cannot_introduce_foreign_candidates() -> None:
    candidates = [_candidate("a", "legal.a", 0.9)]
    with pytest.raises(ValueError, match="foreign_chunk_id"):
        sanitize_authorized_rerank_result(
            candidates,
            [{"chunk_id": "evil", "text": "nope"}],
        )
    hits, diag = apply_rerank_fail_open(
        query="q",
        candidates=candidates,
        reranker=_ForeignReranker(),
        final_n=5,
    )
    assert [h["chunk_id"] for h in hits] == ["a"]
    assert diag["rerank_fallback"] is True


def test_reranker_exception_falls_back_to_vector_ordering() -> None:
    candidates = [
        _candidate("a", "legal.a", 0.9),
        _candidate("b", "legal.b", 0.8),
    ]
    hits, diag = apply_rerank_fail_open(
        query="q",
        candidates=candidates,
        reranker=FailOpenLegalChunkReranker(_ExplodingReranker(), timeout_ms=250),
        final_n=5,
    )
    assert [h["chunk_id"] for h in hits] == ["a", "b"]
    assert diag["rerank_fallback"] is True


def test_empty_rerank_result_falls_back() -> None:
    candidates = [_candidate("a", "legal.a", 0.9)]
    hits, diag = apply_rerank_fail_open(
        query="q",
        candidates=candidates,
        reranker=_EmptyReranker(),
        final_n=5,
    )
    assert [h["chunk_id"] for h in hits] == ["a"]
    assert diag["rerank_fallback"] is True


def test_empty_candidates_work() -> None:
    hits, diag = apply_rerank_fail_open(
        query="q",
        candidates=[],
        reranker=_ReverseReranker(),
        final_n=5,
    )
    assert hits == []
    assert diag["retrieval_candidate_count"] == 0
    assert diag["final_chunk_count"] == 0


def test_fewer_candidates_than_top_n() -> None:
    candidates = [_candidate("a", "legal.a", 0.9)]
    hits, diag = apply_rerank_fail_open(
        query="q",
        candidates=candidates,
        reranker=_ReverseReranker(),
        final_n=5,
    )
    assert len(hits) == 1
    assert diag["final_chunk_count"] == 1


def _seed_store(tmp_path: Path, n: int = 8) -> tuple[LegalKnowledgeStore, NumpyLegalVectorStore]:
    knowledge = LegalKnowledgeStore(tmp_path)
    store = NumpyLegalVectorStore(knowledge)
    chunks = [
        IndexedChunkMeta(
            chunk_id=f"c{i}",
            rule_id=f"legal.r{i}",
            rule_version="1",
            valid_from=date(2026, 1, 1),
            approval_status="approved",
            text=f"body {i}",
            content_hash=f"h{i}",
        )
        for i in range(n)
    ]
    embs = [[1.0 - i * 0.05, float(i) * 0.01] for i in range(n)]
    store.upsert(chunks, embs, embedding_model="test")
    return knowledge, store


@pytest.mark.asyncio
async def test_disabled_retriever_pool_equals_top_k(tmp_path: Path) -> None:
    """With rerank disabled, vector search top_k matches caller top_k (Phase 1)."""
    knowledge, store = _seed_store(tmp_path, n=8)

    searched: dict[str, Any] = {}
    original_search = store.search

    def tracking_search(*args, **kwargs):
        searched["top_k"] = kwargs.get("top_k")
        searched["approved_only"] = kwargs.get("approved_only")
        searched["effective_date"] = kwargs.get("effective_date")
        return original_search(*args, **kwargs)

    store.search = tracking_search  # type: ignore[method-assign]

    retriever = VersionAwareLegalRetriever(
        model=_FakeEmbedModel(),
        store=knowledge,
        vector_store=store,
        reranker=None,
        rerank_enabled=False,
        retrieval_top_k=20,
        rerank_top_n=5,
    )
    result = await retriever.retrieve("q", effective_date=date(2026, 6, 1), top_k=5)
    assert searched["top_k"] == 5
    assert searched["approved_only"] is True
    assert result["diagnostics"]["rerank_enabled"] is False
    assert result["diagnostics"]["vector_pool_k"] == 5
    assert result["diagnostics"]["final_chunk_count"] == 5
    assert len(result["hits"]) == 5
    assert [h["chunk_id"] for h in result["hits"]] == [f"c{i}" for i in range(5)]


@pytest.mark.asyncio
async def test_enabled_retriever_uses_larger_pool_then_top_n(tmp_path: Path) -> None:
    knowledge, store = _seed_store(tmp_path, n=8)

    searched: dict[str, Any] = {}
    original_search = store.search

    def tracking_search(*args, **kwargs):
        searched["top_k"] = kwargs.get("top_k")
        return original_search(*args, **kwargs)

    store.search = tracking_search  # type: ignore[method-assign]

    retriever = VersionAwareLegalRetriever(
        model=_FakeEmbedModel(),
        store=knowledge,
        vector_store=store,
        reranker=_ReverseReranker(),
        rerank_enabled=True,
        retrieval_top_k=20,
        rerank_top_n=3,
    )
    result = await retriever.retrieve("q", effective_date=date(2026, 6, 1), top_k=5)
    assert searched["top_k"] == 20
    assert result["diagnostics"]["rerank_enabled"] is True
    assert result["diagnostics"]["retrieval_candidate_count"] == 8
    assert result["diagnostics"]["final_chunk_count"] == 3
    assert result["diagnostics"]["order_changed"] is True
    # Vector order c0..c7; reverse then Top-3 → c7,c6,c5
    assert [h["chunk_id"] for h in result["hits"]] == ["c7", "c6", "c5"]


@pytest.mark.asyncio
async def test_eligibility_filters_before_rerank(tmp_path: Path) -> None:
    """Pending / out-of-date chunks never reach the reranker."""
    knowledge = LegalKnowledgeStore(tmp_path)
    store = NumpyLegalVectorStore(knowledge)
    chunks = [
        IndexedChunkMeta(
            chunk_id="ok",
            rule_id="legal.ok",
            rule_version="1",
            valid_from=date(2026, 1, 1),
            approval_status="approved",
            text="approved current",
            content_hash="h1",
        ),
        IndexedChunkMeta(
            chunk_id="pending",
            rule_id="legal.pending",
            rule_version="1",
            valid_from=date(2026, 1, 1),
            approval_status="pending",
            text="should not retrieve",
            content_hash="h2",
        ),
        IndexedChunkMeta(
            chunk_id="future",
            rule_id="legal.future",
            rule_version="1",
            valid_from=date(2027, 1, 1),
            approval_status="approved",
            text="future dated",
            content_hash="h3",
        ),
    ]
    store.upsert(chunks, [[1.0, 0.0], [0.99, 0.01], [0.98, 0.02]], embedding_model="test")

    seen: list[str] = []

    class RecordingReranker:
        def rerank(self, query: str, candidates: Sequence[dict[str, Any]]):
            seen.extend(str(c.get("chunk_id")) for c in candidates)
            return list(candidates)

    retriever = VersionAwareLegalRetriever(
        model=_FakeEmbedModel(),
        store=knowledge,
        vector_store=store,
        reranker=RecordingReranker(),
        rerank_enabled=True,
        retrieval_top_k=20,
        rerank_top_n=5,
    )
    result = await retriever.retrieve("q", effective_date=date(2026, 6, 1), top_k=5)
    assert seen == ["ok"]
    assert [h["chunk_id"] for h in result["hits"]] == ["ok"]
    assert "pending" not in seen
    assert "future" not in seen
