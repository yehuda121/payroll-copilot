"""Numpy cosine vector store — INDEX only over approved legal chunks."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from payroll_copilot.application.dto.legal_knowledge import IndexedChunkMeta
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import LegalKnowledgeStore


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class NumpyLegalVectorStore:
    """Local durable cosine index. Production swap target: OpenSearch / managed vector DB via same port."""

    BACKEND_NAME = "numpy_cosine_file"

    def __init__(self, store: LegalKnowledgeStore | None = None) -> None:
        self._store = store or LegalKnowledgeStore()

    def upsert(
        self,
        chunks: list[IndexedChunkMeta],
        embeddings: list[list[float]],
        *,
        embedding_model: str,
    ) -> None:
        self._store.save_vector_chunks(
            chunks,
            embeddings,
            embedding_model=embedding_model,
            backend=self.BACKEND_NAME,
        )

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        effective_date: date | None = None,
        scope: str | None = None,
        approved_only: bool = True,
    ) -> list[tuple[float, dict[str, Any]]]:
        rows = self._store.load_vector_chunks()
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            if approved_only and str(row.get("approval_status") or "") != "approved":
                continue
            if scope and str(row.get("scope") or "general") not in {scope, "general"}:
                # Sector-specific must not apply globally: if query scope is general,
                # exclude non-general; if query has sector scope, allow that sector + general.
                row_scope = str(row.get("scope") or "general")
                if scope == "general" and row_scope != "general":
                    continue
                if scope != "general" and row_scope not in {scope, "general"}:
                    continue
            if effective_date is not None:
                vf_raw = row.get("valid_from")
                vt_raw = row.get("valid_to")
                try:
                    vf = date.fromisoformat(str(vf_raw)[:10]) if vf_raw else date.min
                except ValueError:
                    vf = date.min
                try:
                    vt = date.fromisoformat(str(vt_raw)[:10]) if vt_raw else None
                except ValueError:
                    vt = None
                if not (vf <= effective_date and (vt is None or vt >= effective_date)):
                    continue
            emb = row.get("embedding")
            if not isinstance(emb, list):
                continue
            score = cosine_similarity(query_embedding, [float(x) for x in emb])
            scored.append((score, row))
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[: max(1, top_k)]
