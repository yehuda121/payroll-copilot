"""Factory for legal vector backends (Chroma production, NumPy local/test)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from payroll_copilot.application.dto.legal_knowledge import IndexedChunkMeta
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import get_legal_knowledge_store
from payroll_copilot.infrastructure.rag.chroma_vector_store import ChromaLegalVectorStore
from payroll_copilot.infrastructure.rag.numpy_vector_store import NumpyLegalVectorStore


class LegalVectorStorePort(Protocol):
    BACKEND_NAME: str

    def upsert(
        self,
        chunks: list[IndexedChunkMeta],
        embeddings: list[list[float]],
        *,
        embedding_model: str,
    ) -> None: ...

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        effective_date=None,
        scope: str | None = None,
        approved_only: bool = True,
    ) -> list[tuple[float, dict]]: ...


_VECTOR: Any | None = None


def get_legal_vector_store() -> LegalVectorStorePort:
    global _VECTOR
    if _VECTOR is not None:
        return _VECTOR
    settings = get_settings()
    backend = (getattr(settings, "legal_vector_backend", None) or "chroma").strip().lower()
    store = get_legal_knowledge_store()
    if backend in {"numpy", "file", "local"}:
        _VECTOR = NumpyLegalVectorStore(store if hasattr(store, "save_vector_chunks") else None)
        # When using Dynamo store without file chunk methods, numpy needs a file sink.
        if not hasattr(store, "save_vector_chunks"):
            from payroll_copilot.infrastructure.persistence.legal_knowledge_store import (
                LegalKnowledgeStore,
            )

            root = getattr(settings, "legal_knowledge_data_path", None) or "data/legal_knowledge"
            path = Path(root)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[3] / path
            file_store = LegalKnowledgeStore(path)
            _VECTOR = NumpyLegalVectorStore(file_store)
        return _VECTOR

    persist = getattr(settings, "legal_vector_persist_path", None) or "data/chroma_legal"
    path = Path(persist)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[3] / path
    collection = getattr(settings, "legal_vector_collection", None) or "approved_legal_knowledge_v1"
    _VECTOR = ChromaLegalVectorStore(
        persist_path=path,
        collection_name=collection,
        health_sink=store,
    )
    return _VECTOR


def reset_legal_vector_store() -> None:
    global _VECTOR
    _VECTOR = None
