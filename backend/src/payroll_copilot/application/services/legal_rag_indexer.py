"""Index approved legal knowledge into the vector store (never indexes pending proposals)."""

from __future__ import annotations

import hashlib
import logging
from datetime import date
from typing import Any

import yaml

from payroll_copilot.application.dto.legal_knowledge import IndexedChunkMeta
from payroll_copilot.application.ports import ModelProvider
from payroll_copilot.application.services.legal_rule_version_catalog import LegalRuleVersionCatalog
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import (
    LegalKnowledgeStore,
    get_legal_knowledge_store,
)
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader

logger = logging.getLogger(__name__)


class LegalRagIndexer:
    def __init__(
        self,
        *,
        rules_path: str,
        model: ModelProvider | None,
        store: Any | None = None,
        catalog: LegalRuleVersionCatalog | None = None,
        vector_store: Any | None = None,
        embedding_model_name: str = "configured_provider",
    ) -> None:
        self._rules_path = rules_path
        self._model = model
        self._store = store or get_legal_knowledge_store()
        self._catalog = catalog or LegalRuleVersionCatalog(rules_path)
        if vector_store is not None:
            self._vectors = vector_store
        else:
            from payroll_copilot.infrastructure.rag.vector_store_factory import get_legal_vector_store

            self._vectors = get_legal_vector_store()
        self._embedding_model_name = embedding_model_name

    async def rebuild_all(self) -> dict[str, Any]:
        self._catalog.ensure_seeded_from_yaml()
        versions = self._catalog.list_versions()
        # Index ACTIVE + SUPERSEDED approved snapshots (historical retrieval).
        approved = [v for v in versions if v.status in {"ACTIVE", "SUPERSEDED"}]
        chunks: list[IndexedChunkMeta] = []
        for version in approved:
            chunks.extend(self._chunk_version(version))
        return await self._embed_and_upsert(chunks)

    async def reindex_rule_version(self, rule_id: str, rule_version: str) -> dict[str, Any]:
        self._catalog.ensure_seeded_from_yaml()
        match = next(
            (
                v
                for v in self._catalog.list_versions(rule_id)
                if str(v.version) == str(rule_version)
            ),
            None,
        )
        if match is None:
            raise LookupError("rule_version_not_found")
        if hasattr(self._vectors, "delete_rule_version"):
            self._vectors.delete_rule_version(rule_id, str(rule_version))
        elif hasattr(self._store, "delete_rule_version_chunks"):
            self._store.delete_rule_version_chunks(rule_id, str(rule_version))
        chunks = self._chunk_version(match)
        return await self._embed_and_upsert(chunks)

    def _chunk_version(self, version: Any) -> list[IndexedChunkMeta]:
        text = self._load_snapshot_text(version)
        sections = self._legal_aware_chunks(text)
        out: list[IndexedChunkMeta] = []
        for idx, (section, body) in enumerate(sections):
            content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            chunk_id = f"{version.rule_id}::v{version.version}::{section}::{idx}"
            out.append(
                IndexedChunkMeta(
                    chunk_id=chunk_id,
                    rule_id=version.rule_id,
                    rule_version=str(version.version),
                    title=version.rule_id,
                    section=section,
                    valid_from=date.fromisoformat(version.valid_from),
                    valid_to=date.fromisoformat(version.valid_to) if version.valid_to else None,
                    scope=version.scope or "general",
                    source_id=None,
                    source_reference=version.source_file,
                    authority_level="OFFICIAL",
                    content_hash=content_hash,
                    language="he",
                    approval_status="approved",
                    text=body,
                )
            )
        return out

    def _load_snapshot_text(self, version: Any) -> str:
        from pathlib import Path

        if version.snapshot_path:
            path = Path(self._rules_path) / version.snapshot_path
            if path.exists():
                return path.read_text(encoding="utf-8")
        # Fallback: current YAML rule body
        loader = YamlLegalRulesLoader(self._rules_path)
        for rule in loader.load_merged_rules().rules.values():
            if rule.rule_id == version.rule_id:
                return yaml.safe_dump(
                    {
                        "id": rule.rule_id,
                        "description": rule.description,
                        "parameters": rule.parameters,
                        "legal_reference": rule.legal_reference,
                    },
                    allow_unicode=True,
                )
        return f"rule_id: {version.rule_id}\n"

    @staticmethod
    def _legal_aware_chunks(text: str) -> list[tuple[str, str]]:
        """Prefer semantic sections when YAML-like structure is present."""
        try:
            data = yaml.safe_load(text)
        except Exception:  # noqa: BLE001
            data = None
        sections: list[tuple[str, str]] = []
        if isinstance(data, dict):
            if data.get("description"):
                sections.append(("definition", yaml.safe_dump({"description": data["description"]}, allow_unicode=True)))
            if data.get("parameters"):
                sections.append(("calculation", yaml.safe_dump({"parameters": data["parameters"]}, allow_unicode=True)))
            if data.get("legal_reference"):
                sections.append(("source", yaml.safe_dump({"legal_reference": data["legal_reference"]}, allow_unicode=True)))
            if data.get("id"):
                sections.append(("identity", f"id: {data['id']}"))
            if sections:
                return sections
        # Deterministic fallback chunking
        chunk_size = 800
        overlap = 100
        cleaned = text.strip()
        if not cleaned:
            return [("body", "")]
        parts: list[tuple[str, str]] = []
        start = 0
        idx = 0
        while start < len(cleaned):
            end = min(len(cleaned), start + chunk_size)
            parts.append((f"body_{idx}", cleaned[start:end]))
            if end >= len(cleaned):
                break
            start = max(end - overlap, start + 1)
            idx += 1
        return parts

    async def _embed_and_upsert(self, chunks: list[IndexedChunkMeta]) -> dict[str, Any]:
        if not chunks:
            return {"chunk_count": 0, "status": "empty"}
        if self._model is None:
            self._store.set_vector_error("No embedding model provider configured")
            raise RuntimeError("embedding_provider_unavailable")
        texts = [c.text for c in chunks]
        try:
            embeddings = await self._model.embed(texts)
        except Exception as exc:  # noqa: BLE001
            self._store.set_vector_error(str(exc))
            raise
        if len(embeddings) != len(chunks):
            raise RuntimeError("embedding_count_mismatch")
        self._vectors.upsert(chunks, embeddings, embedding_model=self._embedding_model_name)
        health = self._store.vector_health()
        return {
            "chunk_count": health.chunk_count,
            "indexed_rules": health.indexed_rules,
            "indexed_versions": health.indexed_versions,
            "backend": health.backend,
            "embedding_model": health.embedding_model,
            "status": health.status,
        }
