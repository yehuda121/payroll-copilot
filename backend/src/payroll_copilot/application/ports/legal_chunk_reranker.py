"""Port for authorized legal-chunk reranking (reorder/truncate only)."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

# Candidate dicts carry vector-store metadata (chunk_id, rule_id, text, scores, …).
LegalRerankCandidate = Mapping[str, Any]


@runtime_checkable
class LegalChunkReranker(Protocol):
    """Reorder or truncate already-authorized retrieval candidates.

    Implementations MUST NOT fetch or invent chunks outside ``candidates``.
    """

    def rerank(
        self,
        query: str,
        candidates: Sequence[LegalRerankCandidate],
    ) -> Sequence[LegalRerankCandidate]:
        """Return a reordered (and optionally truncated) view of ``candidates``."""
        ...
