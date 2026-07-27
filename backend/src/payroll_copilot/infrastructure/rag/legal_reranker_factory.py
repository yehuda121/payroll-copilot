"""Factory for legal chunk rerankers from Settings (no model load when disabled)."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.ports.legal_chunk_reranker import LegalChunkReranker
from payroll_copilot.application.services.legal_chunk_reranker import (
    FailOpenLegalChunkReranker,
    NoOpLegalChunkReranker,
)
from payroll_copilot.infrastructure.rag.cross_encoder_legal_reranker import (
    DEFAULT_LEGAL_RERANK_MODEL,
    CrossEncoderLegalChunkReranker,
)


class _WarmFailOpenLegalChunkReranker(FailOpenLegalChunkReranker):
    """Fail-open wrapper that warms the model outside the inference timeout budget."""

    def rerank(self, query: str, candidates):  # type: ignore[no-untyped-def]
        if not candidates:
            return []
        inner = self._inner
        ensure = getattr(inner, "ensure_loaded", None)
        if callable(ensure):
            try:
                ensure()
            except Exception:
                # Propagate so apply_rerank_fail_open falls back to vector order.
                raise
        return super().rerank(query, candidates)


def build_legal_chunk_reranker(settings: Any) -> LegalChunkReranker | None:
    """Return a fail-open reranker when enabled; otherwise ``None`` (no model load).

    When enabled:
    - empty / default model id → ``BAAI/bge-reranker-v2-m3``
    - ``noop`` / ``identity`` → Phase 2 identity placeholder (tests / dry-run)
    """
    if not bool(getattr(settings, "legal_rag_rerank_enabled", False)):
        return None

    model_name = str(getattr(settings, "legal_rag_rerank_model", "") or "").strip()
    timeout_ms = int(getattr(settings, "legal_rag_rerank_timeout_ms", 15000) or 15000)
    alias = model_name.lower()
    if alias in {"noop", "identity", "none"}:
        inner: LegalChunkReranker = NoOpLegalChunkReranker()
        return _WarmFailOpenLegalChunkReranker(inner, timeout_ms=timeout_ms)

    model_id = model_name or DEFAULT_LEGAL_RERANK_MODEL
    device = str(getattr(settings, "legal_rag_rerank_device", "") or "").strip() or None
    inner = CrossEncoderLegalChunkReranker(model_id=model_id, device=device)
    return _WarmFailOpenLegalChunkReranker(inner, timeout_ms=timeout_ms)
