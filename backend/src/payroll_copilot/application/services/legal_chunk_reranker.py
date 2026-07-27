"""Legal chunk reranker adapters: no-op, fail-open, and authorized sanitization."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Sequence

from payroll_copilot.application.ports.legal_chunk_reranker import (
    LegalChunkReranker,
    LegalRerankCandidate,
)

logger = logging.getLogger(__name__)


class NoOpLegalChunkReranker:
    """Identity reranker — preserves vector order (Phase 2 placeholder / tests)."""

    def rerank(
        self,
        query: str,
        candidates: Sequence[LegalRerankCandidate],
    ) -> Sequence[LegalRerankCandidate]:
        return list(candidates)


class FailOpenLegalChunkReranker:
    """Wraps an inner reranker; on failure returns the original vector-ranked list."""

    def __init__(
        self,
        inner: LegalChunkReranker,
        *,
        timeout_ms: int = 250,
    ) -> None:
        self._inner = inner
        self._timeout_ms = max(1, int(timeout_ms))

    def rerank(
        self,
        query: str,
        candidates: Sequence[LegalRerankCandidate],
    ) -> Sequence[LegalRerankCandidate]:
        if not candidates:
            return []
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self._inner.rerank, query, list(candidates))
                raw = future.result(timeout=self._timeout_ms / 1000.0)
            return sanitize_authorized_rerank_result(candidates, raw)
        except FuturesTimeoutError:
            logger.warning("legal_rerank_timeout", extra={"timeout_ms": self._timeout_ms})
            raise
        except Exception:
            logger.warning("legal_rerank_failed", exc_info=True)
            raise


def sanitize_authorized_rerank_result(
    authorized: Sequence[LegalRerankCandidate],
    reranked: Sequence[LegalRerankCandidate] | None,
) -> list[dict[str, Any]]:
    """Keep only authorized candidates; preserve original metadata; reject foreign IDs.

    Raises ``ValueError`` on empty/invalid results so callers can fail open.
    """
    if reranked is None:
        raise ValueError("rerank_result_none")
    if not authorized:
        return []

    by_id: dict[str, dict[str, Any]] = {}
    order_ids: list[str] = []
    for row in authorized:
        cid = str(row.get("chunk_id") or "")
        if not cid:
            continue
        if cid not in by_id:
            by_id[cid] = dict(row)
            order_ids.append(cid)

    if not by_id:
        # No stable ids — cannot safely accept a rerank; treat as invalid.
        raise ValueError("authorized_candidates_missing_chunk_id")

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in reranked:
        cid = str((row or {}).get("chunk_id") or "")
        if not cid:
            raise ValueError("rerank_result_missing_chunk_id")
        if cid not in by_id:
            raise ValueError(f"foreign_chunk_id:{cid}")
        if cid in seen:
            continue
        # Always emit the authorized metadata snapshot (never trust reranker fields).
        out.append(dict(by_id[cid]))
        seen.add(cid)

    if not out:
        raise ValueError("rerank_result_empty")
    return out


def apply_rerank_fail_open(
    *,
    query: str,
    candidates: Sequence[LegalRerankCandidate],
    reranker: LegalChunkReranker | None,
    final_n: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply optional reranker with fail-open; return (hits, diagnostics_delta)."""
    vector_ordered = [dict(c) for c in candidates]
    diag: dict[str, Any] = {
        "retrieval_candidate_count": len(vector_ordered),
        "rerank_fallback": False,
        "order_changed": False,
    }
    if not vector_ordered:
        diag["final_chunk_count"] = 0
        return [], diag

    final_n = max(0, int(final_n))
    if reranker is None:
        final_hits = vector_ordered[:final_n]
        diag["final_chunk_count"] = len(final_hits)
        return final_hits, diag

    try:
        reranked = list(reranker.rerank(query, vector_ordered))
        # FailOpen wrapper may raise; plain rerankers still need sanitization.
        if not isinstance(reranker, FailOpenLegalChunkReranker):
            reranked = sanitize_authorized_rerank_result(vector_ordered, reranked)
        final_hits = reranked[:final_n]
    except Exception as exc:  # noqa: BLE001
        diag["rerank_fallback"] = True
        diag["rerank_fallback_reason"] = f"{type(exc).__name__}:{exc}"
        final_hits = vector_ordered[:final_n]
    else:
        vector_ids = [str(h.get("chunk_id") or "") for h in vector_ordered[: len(final_hits)]]
        final_ids = [str(h.get("chunk_id") or "") for h in final_hits]
        diag["order_changed"] = vector_ids != final_ids

    diag["final_chunk_count"] = len(final_hits)
    return final_hits, diag
