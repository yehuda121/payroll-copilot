"""Version-aware legal RAG retriever with explicit YAML fallback."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from payroll_copilot.application.ports import ModelProvider
from payroll_copilot.application.ports.assistant import ApprovedLaborLawSearchPort, LaborLawSearchHit
from payroll_copilot.application.ports.legal_chunk_reranker import LegalChunkReranker
from payroll_copilot.application.services.legal_chunk_reranker import apply_rerank_fail_open
from payroll_copilot.infrastructure.ai.agents.approved_labor_law_search import YamlApprovedLaborLawSearch
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import get_legal_knowledge_store

logger = logging.getLogger(__name__)


class VersionAwareLegalRetriever:
    """Semantic retrieval over approved indexed chunks + metadata filters."""

    def __init__(
        self,
        *,
        model: ModelProvider | None,
        store: Any | None = None,
        vector_store: Any | None = None,
        reranker: LegalChunkReranker | None = None,
        rerank_enabled: bool = False,
        retrieval_top_k: int = 20,
        rerank_top_n: int = 5,
        rerank_timeout_ms: int = 15000,
    ) -> None:
        self._model = model
        self._store = store or get_legal_knowledge_store()
        self._vectors = vector_store
        if self._vectors is None:
            from payroll_copilot.infrastructure.rag.vector_store_factory import get_legal_vector_store

            self._vectors = get_legal_vector_store()
        # When disabled, reranker must remain unloaded (caller passes None).
        self._rerank_enabled = bool(rerank_enabled) and reranker is not None
        self._reranker = reranker if self._rerank_enabled else None
        self._retrieval_top_k = max(1, int(retrieval_top_k))
        self._rerank_top_n = max(1, int(rerank_top_n))
        self._rerank_timeout_ms = max(1, int(rerank_timeout_ms))

    async def retrieve(
        self,
        query: str,
        *,
        effective_date: date | None = None,
        scope: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Return hits and diagnostics. Never fabricates contexts."""
        final_n = max(1, int(top_k))
        diagnostics: dict[str, Any] = {
            "retrieval_mode": "vector",
            "effective_date_mode": "explicit" if effective_date else "current_default",
            "effective_date": effective_date.isoformat() if effective_date else None,
            "scope": scope or "general",
            "rerank_enabled": bool(self._rerank_enabled),
        }
        if self._model is None:
            diagnostics["retrieval_mode"] = "unavailable"
            diagnostics["reason"] = "embedding_provider_unavailable"
            diagnostics["retrieval_candidate_count"] = 0
            diagnostics["final_chunk_count"] = 0
            diagnostics["rerank_fallback"] = False
            diagnostics["order_changed"] = False
            return {"hits": [], "diagnostics": diagnostics}

        health = self._store.vector_health()
        chunk_count = health.chunk_count
        live_count: int | None = None
        if hasattr(self._vectors, "count"):
            try:
                live_count = int(self._vectors.count())
            except Exception:  # noqa: BLE001
                live_count = None
        # Live vector backend is authoritative when available — Dynamo/file health can
        # be stale after a volume recreate while metadata still says "ready".
        if live_count is not None:
            chunk_count = live_count
        if chunk_count <= 0 or (live_count is None and health.status == "empty"):
            diagnostics["retrieval_mode"] = "unavailable"
            diagnostics["reason"] = "vector_index_empty"
            diagnostics["retrieval_candidate_count"] = 0
            diagnostics["final_chunk_count"] = 0
            diagnostics["rerank_fallback"] = False
            diagnostics["order_changed"] = False
            return {"hits": [], "diagnostics": diagnostics}

        as_of = effective_date or date.today()
        if effective_date is None:
            diagnostics["note"] = (
                "No effective_date provided; using current calendar date against approved knowledge."
            )

        try:
            embeddings = await self._model.embed([query])
        except Exception as exc:  # noqa: BLE001
            diagnostics["retrieval_mode"] = "unavailable"
            diagnostics["reason"] = f"embed_failed:{type(exc).__name__}"
            diagnostics["retrieval_candidate_count"] = 0
            diagnostics["final_chunk_count"] = 0
            diagnostics["rerank_fallback"] = False
            diagnostics["order_changed"] = False
            return {"hits": [], "diagnostics": diagnostics}

        if not embeddings:
            diagnostics["retrieval_mode"] = "unavailable"
            diagnostics["reason"] = "empty_embedding"
            diagnostics["retrieval_candidate_count"] = 0
            diagnostics["final_chunk_count"] = 0
            diagnostics["rerank_fallback"] = False
            diagnostics["order_changed"] = False
            return {"hits": [], "diagnostics": diagnostics}

        # Disabled path: pool size == caller top_k (Phase 1 equivalence).
        # Enabled path: larger authorized candidate pool, then Top-N after rerank.
        if self._rerank_enabled:
            pool_k = max(self._retrieval_top_k, final_n)
            final_n = min(final_n, self._rerank_top_n)
        else:
            pool_k = final_n

        scored = self._vectors.search(
            embeddings[0],
            top_k=pool_k,
            effective_date=as_of,
            scope=scope,
            approved_only=True,
        )
        candidates: list[dict[str, Any]] = []
        for score, row in scored:
            candidates.append(
                {
                    "score": score,
                    "rule_id": row.get("rule_id"),
                    "rule_version": row.get("rule_version"),
                    "title": row.get("title") or row.get("rule_id"),
                    "section": row.get("section"),
                    "text": row.get("text") or "",
                    "valid_from": row.get("valid_from"),
                    "valid_to": row.get("valid_to"),
                    "scope": row.get("scope"),
                    "source_reference": row.get("source_reference"),
                    "authority_level": row.get("authority_level"),
                    "chunk_id": row.get("chunk_id"),
                    "approval_status": row.get("approval_status"),
                }
            )

        hits, rerank_diag = apply_rerank_fail_open(
            query=query,
            candidates=candidates,
            reranker=self._reranker,
            final_n=final_n,
        )
        diagnostics.update(rerank_diag)
        diagnostics["hit_count"] = len(hits)
        diagnostics["vector_pool_k"] = pool_k
        return {"hits": hits, "diagnostics": diagnostics}


class HybridApprovedLaborLawSearch(ApprovedLaborLawSearchPort):
    """Vector-first search with observable YAML fallback for the assistant tool surface."""

    def __init__(
        self,
        rules_path: str,
        *,
        retriever: VersionAwareLegalRetriever | None = None,
        yaml_fallback: YamlApprovedLaborLawSearch | None = None,
    ) -> None:
        self._rules_path = rules_path
        self._retriever = retriever
        self._yaml = yaml_fallback or YamlApprovedLaborLawSearch(rules_path)
        self.last_diagnostics: dict[str, Any] = {}
        self._effective_date: date | None = None
        self._scope: str | None = None

    def set_retrieval_context(self, *, effective_date: date | None = None, scope: str | None = None) -> None:
        self._effective_date = effective_date
        self._scope = scope

    def search(self, query: str, *, locale: str = "en", limit: int = 5) -> list[LaborLawSearchHit]:
        """Sync path — YAML only; prefer ``asearch`` inside the async assistant graph."""
        hits = self._yaml.search(query, locale=locale, limit=limit)
        self.last_diagnostics = {
            "retrieval_mode": "yaml_fallback",
            "reason": "sync_search_path",
        }
        return hits

    async def asearch(self, query: str, *, locale: str = "en", limit: int = 5) -> list[LaborLawSearchHit]:
        if self._retriever is None:
            hits = self._yaml.search(query, locale=locale, limit=limit)
            self.last_diagnostics = {
                "retrieval_mode": "yaml_fallback",
                "reason": "retriever_not_configured",
            }
            return hits
        try:
            result = await self._retriever.retrieve(
                query,
                effective_date=self._effective_date,
                scope=self._scope,
                top_k=limit,
            )
        except Exception:  # noqa: BLE001
            logger.exception("vector_retrieval_failed")
            hits = self._yaml.search(query, locale=locale, limit=limit)
            self.last_diagnostics = {
                "retrieval_mode": "yaml_fallback",
                "reason": "vector_exception",
            }
            return hits

        self.last_diagnostics = dict(result.get("diagnostics") or {})
        vector_hits = result.get("hits") or []
        if vector_hits:
            mapped: list[LaborLawSearchHit] = []
            for hit in vector_hits:
                mapped.append(
                    LaborLawSearchHit(
                        rule_key=str(hit.get("rule_id") or ""),
                        title=str(hit.get("title") or hit.get("rule_id") or "Legal rule"),
                        summary=str(hit.get("text") or "")[:1200],
                        legal_reference=str(hit.get("source_reference") or "") or None,
                        source_file=(
                            f"vector:{hit.get('rule_id')}@v{hit.get('rule_version')}"
                            f"|{hit.get('valid_from')}..{hit.get('valid_to') or 'current'}"
                        ),
                    )
                )
            self.last_diagnostics["retrieval_mode"] = "vector"
            return mapped

        hits = self._yaml.search(query, locale=locale, limit=limit)
        self.last_diagnostics = {
            **self.last_diagnostics,
            "retrieval_mode": "yaml_fallback",
            "reason": self.last_diagnostics.get("reason") or "no_vector_hits",
        }
        return hits
