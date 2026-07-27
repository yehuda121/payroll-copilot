"""Persistent ChromaDB vector store for approved legal knowledge (INDEX only)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from payroll_copilot.application.dto.legal_knowledge import IndexedChunkMeta, VectorIndexHealth
from payroll_copilot.infrastructure.rag.numpy_vector_store import cosine_similarity

logger = logging.getLogger(__name__)


class ChromaLegalVectorStore:
    """Persistent Chroma collection with metadata for temporal/scope filters."""

    BACKEND_NAME = "chromadb_persistent"

    def __init__(
        self,
        *,
        persist_path: str | Path,
        collection_name: str = "approved_legal_knowledge_v1",
        health_sink: Any | None = None,
    ) -> None:
        self._persist_path = Path(persist_path)
        self._persist_path.mkdir(parents=True, exist_ok=True)
        self._collection_name = collection_name
        self._health_sink = health_sink
        self._client = None
        self._collection = None

    def _ensure(self):
        if self._collection is not None:
            return self._collection
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._client = chromadb.PersistentClient(
            path=str(self._persist_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return self._collection

    def upsert(
        self,
        chunks: list[IndexedChunkMeta],
        embeddings: list[list[float]],
        *,
        embedding_model: str,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks/embeddings length mismatch")
        collection = self._ensure()
        ids = [c.chunk_id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas = [_meta_dict(c) for c in chunks]
        # Idempotent upsert by stable chunk_id
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        self._write_health(embedding_model=embedding_model)

    def delete_rule_version(self, rule_id: str, rule_version: str) -> None:
        collection = self._ensure()
        # Chroma where filter
        try:
            collection.delete(
                where={
                    "$and": [
                        {"rule_id": rule_id},
                        {"rule_version": str(rule_version)},
                    ]
                }
            )
        except Exception:  # noqa: BLE001
            logger.exception("chroma_delete_rule_version_failed")

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        effective_date: date | None = None,
        scope: str | None = None,
        approved_only: bool = True,
    ) -> list[tuple[float, dict[str, Any]]]:
        collection = self._ensure()
        # Over-fetch then filter temporally in application code for correct date windows.
        fetch_n = max(top_k * 8, 20)
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(fetch_n, max(collection.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        scored: list[tuple[float, dict[str, Any]]] = []
        for i, chunk_id in enumerate(ids):
            meta = dict(metas[i] or {})
            if approved_only and str(meta.get("approval_status") or "") != "approved":
                continue
            row_scope = str(meta.get("scope") or "general")
            if scope:
                if scope == "general" and row_scope != "general":
                    continue
                if scope != "general" and row_scope not in {scope, "general"}:
                    continue
            if effective_date is not None:
                vf_raw = meta.get("valid_from")
                vt_raw = meta.get("valid_to")
                try:
                    vf = date.fromisoformat(str(vf_raw)[:10]) if vf_raw and str(vf_raw) != "none" else date.min
                except ValueError:
                    vf = date.min
                try:
                    vt = (
                        date.fromisoformat(str(vt_raw)[:10])
                        if vt_raw and str(vt_raw) not in {"", "none", "null"}
                        else None
                    )
                except ValueError:
                    vt = None
                if not (vf <= effective_date and (vt is None or vt >= effective_date)):
                    continue
            # Chroma cosine distance: lower is better; convert to similarity-ish score
            distance = float(dists[i]) if i < len(dists) else 1.0
            score = 1.0 - distance
            row = {
                **meta,
                "chunk_id": chunk_id,
                "text": docs[i] if i < len(docs) else "",
                "embedding": None,
            }
            scored.append((score, row))
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[: max(1, top_k)]

    def count(self) -> int:
        return int(self._ensure().count())

    def _write_health(self, *, embedding_model: str) -> None:
        collection = self._ensure()
        # Approximate unique rules/versions from a sample get — full scan avoided for large corpora;
        # for legal corpus size this is acceptable via count + metadata probe.
        count = collection.count()
        health = VectorIndexHealth(
            backend=self.BACKEND_NAME,
            embedding_model=embedding_model,
            indexed_rules=0,
            indexed_versions=0,
            chunk_count=count,
            last_indexed_at=datetime.now(timezone.utc),
            last_error=None,
            status="ready" if count else "empty",
        )
        if count > 0:
            probe = collection.get(include=["metadatas"], limit=min(count, 5000))
            metas = probe.get("metadatas") or []
            rules = {str(m.get("rule_id")) for m in metas if m and m.get("rule_id")}
            versions = {
                f"{m.get('rule_id')}@{m.get('rule_version')}"
                for m in metas
                if m and m.get("rule_id")
            }
            health.indexed_rules = len(rules)
            health.indexed_versions = len(versions)
        if self._health_sink is not None and hasattr(self._health_sink, "set_vector_health"):
            self._health_sink.set_vector_health(health)


def _meta_dict(chunk: IndexedChunkMeta) -> dict[str, Any]:
    # Chroma metadata values must be str|int|float|bool
    return {
        "rule_id": chunk.rule_id,
        "rule_version": str(chunk.rule_version),
        "title": chunk.title or chunk.rule_id,
        "section": chunk.section or "",
        "valid_from": chunk.valid_from.isoformat() if chunk.valid_from else "none",
        "valid_to": chunk.valid_to.isoformat() if chunk.valid_to else "none",
        "scope": chunk.scope or "general",
        "source_id": chunk.source_id or "",
        "source_reference": chunk.source_reference or "",
        "authority_level": chunk.authority_level or "OFFICIAL",
        "content_hash": chunk.content_hash or "",
        "language": chunk.language or "he",
        "approval_status": chunk.approval_status or "approved",
    }


# Keep cosine helper imported for unit tests that compare backends.
__all__ = ["ChromaLegalVectorStore", "cosine_similarity"]
