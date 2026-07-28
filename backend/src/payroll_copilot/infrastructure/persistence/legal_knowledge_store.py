"""In-memory + filesystem legal knowledge store (proposals, sync runs, snapshots, vector meta).

DynamoDB remains available via optional adapter; this store is the default durable
local/dev projection and is production-usable for small legal corpora. Vector chunk
embeddings live here as an INDEX only — YAML/catalog remain legal SoT.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from payroll_copilot.application.dto.legal_knowledge import (
    EvaluationCaseResult,
    EvaluationRun,
    IndexedChunkMeta,
    LegalChangeProposal,
    LegalSyncRun,
    ProposalStatus,
    VectorIndexHealth,
)


class LegalKnowledgeStore:
    """Thread-safe JSONL/JSON file store under data/legal_knowledge."""

    def __init__(self, root: Path | str | None = None) -> None:
        if root is None:
            from payroll_copilot.infrastructure.rag.data_paths import resolve_runtime_data_path

            root = resolve_runtime_data_path("data/legal_knowledge")
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        (self._root / "snapshots").mkdir(exist_ok=True)
        (self._root / "vectors").mkdir(exist_ok=True)

    # ── Sync runs ──────────────────────────────────────────────────────────
    def save_sync_run(self, run: LegalSyncRun) -> LegalSyncRun:
        with self._lock:
            path = self._root / "sync_runs.json"
            runs = self._read_list(path)
            payload = run.model_dump(mode="json")
            replaced = False
            for i, item in enumerate(runs):
                if item.get("run_id") == run.run_id:
                    runs[i] = payload
                    replaced = True
                    break
            if not replaced:
                runs.insert(0, payload)
            self._write_list(path, runs[:200])
            return run

    def list_sync_runs(self, *, limit: int = 50) -> list[LegalSyncRun]:
        with self._lock:
            runs = self._read_list(self._root / "sync_runs.json")
            return [LegalSyncRun.model_validate(r) for r in runs[:limit]]

    def get_sync_run(self, run_id: str) -> LegalSyncRun | None:
        for run in self.list_sync_runs(limit=200):
            if run.run_id == run_id:
                return run
        return None

    # ── Proposals ──────────────────────────────────────────────────────────
    def save_proposal(self, proposal: LegalChangeProposal) -> LegalChangeProposal:
        with self._lock:
            path = self._root / "proposals.json"
            items = self._read_list(path)
            payload = proposal.model_dump(mode="json")
            replaced = False
            for i, item in enumerate(items):
                if item.get("proposal_id") == proposal.proposal_id:
                    items[i] = payload
                    replaced = True
                    break
            if not replaced:
                items.insert(0, payload)
            self._write_list(path, items[:500])
            return proposal

    def list_proposals(self, *, status: ProposalStatus | None = None, limit: int = 100) -> list[LegalChangeProposal]:
        with self._lock:
            items = self._read_list(self._root / "proposals.json")
            proposals = [LegalChangeProposal.model_validate(i) for i in items]
            if status:
                proposals = [p for p in proposals if p.status == status]
            return proposals[:limit]

    def get_proposal(self, proposal_id: str) -> LegalChangeProposal | None:
        for p in self.list_proposals(limit=500):
            if p.proposal_id == proposal_id:
                return p
        return None

    # ── Snapshots / source state ───────────────────────────────────────────
    def save_snapshot(self, *, source_id: str, content: str, content_hash: str) -> str:
        with self._lock:
            snap_id = f"{source_id}__{content_hash[:16]}__{uuid4().hex[:8]}"
            path = self._root / "snapshots" / f"{snap_id}.txt"
            path.write_text(content, encoding="utf-8")
            meta_path = self._root / "source_state.json"
            state = self._read_dict(meta_path)
            state[source_id] = {
                "last_content_hash": content_hash,
                "last_snapshot_id": snap_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._write_dict(meta_path, state)
            return snap_id

    def get_source_state(self, source_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._read_dict(self._root / "source_state.json").get(source_id) or {})

    def read_snapshot(self, snapshot_id: str) -> str | None:
        path = self._root / "snapshots" / f"{snapshot_id}.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def remember_discovery_item(self, item_key: str, content_hash: str) -> None:
        with self._lock:
            path = self._root / "discovery_seen.json"
            seen = self._read_dict(path)
            seen[item_key] = {"content_hash": content_hash, "seen_at": datetime.now(timezone.utc).isoformat()}
            self._write_dict(path, seen)

    def discovery_seen(self, item_key: str, content_hash: str) -> bool:
        with self._lock:
            seen = self._read_dict(self._root / "discovery_seen.json").get(item_key)
            return bool(seen and seen.get("content_hash") == content_hash)

    # ── Vector index ───────────────────────────────────────────────────────
    def save_vector_chunks(
        self,
        chunks: list[IndexedChunkMeta],
        embeddings: list[list[float]],
        *,
        embedding_model: str,
        backend: str,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks/embeddings length mismatch")
        with self._lock:
            path = self._root / "vectors" / "chunks.json"
            existing = self._read_list(path)
            by_id = {str(c.get("chunk_id")): c for c in existing}
            for meta, emb in zip(chunks, embeddings, strict=True):
                by_id[meta.chunk_id] = {
                    **meta.model_dump(mode="json"),
                    "embedding": emb,
                }
            self._write_list(path, list(by_id.values()))
            health = {
                "backend": backend,
                "embedding_model": embedding_model,
                "indexed_rules": len({c.rule_id for c in chunks} | {str(x.get("rule_id")) for x in by_id.values()}),
                "indexed_versions": len(
                    {f"{c.rule_id}@{c.rule_version}" for c in chunks}
                    | {f"{x.get('rule_id')}@{x.get('rule_version')}" for x in by_id.values()}
                ),
                "chunk_count": len(by_id),
                "last_indexed_at": datetime.now(timezone.utc).isoformat(),
                "last_error": None,
                "status": "ready" if by_id else "empty",
            }
            # recount precisely from by_id
            health["indexed_rules"] = len({str(x.get("rule_id")) for x in by_id.values()})
            health["indexed_versions"] = len(
                {f"{x.get('rule_id')}@{x.get('rule_version')}" for x in by_id.values()}
            )
            self._write_dict(self._root / "vectors" / "health.json", health)

    def load_vector_chunks(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_list(self._root / "vectors" / "chunks.json")

    def delete_rule_version_chunks(self, rule_id: str, rule_version: str) -> None:
        with self._lock:
            path = self._root / "vectors" / "chunks.json"
            items = [
                c
                for c in self._read_list(path)
                if not (c.get("rule_id") == rule_id and str(c.get("rule_version")) == str(rule_version))
            ]
            self._write_list(path, items)

    def vector_health(self) -> VectorIndexHealth:
        with self._lock:
            raw = self._read_dict(self._root / "vectors" / "health.json")
            if not raw:
                return VectorIndexHealth(backend="numpy_cosine_file", status="empty")
            return VectorIndexHealth.model_validate(raw)

    def set_vector_error(self, message: str) -> None:
        with self._lock:
            health = self._read_dict(self._root / "vectors" / "health.json")
            health["last_error"] = message
            health["status"] = "error"
            self._write_dict(self._root / "vectors" / "health.json", health)

    def set_vector_health(self, health: VectorIndexHealth) -> None:
        with self._lock:
            self._write_dict(
                self._root / "vectors" / "health.json",
                health.model_dump(mode="json"),
            )

    # ── RAG evaluation ─────────────────────────────────────────────────────
    def save_evaluation_run(self, run: EvaluationRun) -> EvaluationRun:
        with self._lock:
            path = self._root / "eval_runs.json"
            items = self._read_list(path)
            payload = run.model_dump(mode="json")
            for i, item in enumerate(items):
                if item.get("run_id") == run.run_id:
                    items[i] = payload
                    break
            else:
                items.insert(0, payload)
            self._write_list(path, items[:100])
            return run

    def list_evaluation_runs(self, *, limit: int = 50) -> list[EvaluationRun]:
        with self._lock:
            return [EvaluationRun.model_validate(r) for r in self._read_list(self._root / "eval_runs.json")[:limit]]

    def get_evaluation_run(self, run_id: str) -> EvaluationRun | None:
        for run in self.list_evaluation_runs(limit=100):
            if run.run_id == run_id:
                return run
        return None

    def save_evaluation_cases(self, run_id: str, cases: list[EvaluationCaseResult]) -> None:
        with self._lock:
            path = self._root / "eval_cases" / f"{run_id}.json"
            path.parent.mkdir(exist_ok=True)
            path.write_text(
                json.dumps([c.model_dump(mode="json") for c in cases], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def list_evaluation_cases(self, run_id: str) -> list[EvaluationCaseResult]:
        with self._lock:
            path = self._root / "eval_cases" / f"{run_id}.json"
            if not path.exists():
                return []
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [EvaluationCaseResult.model_validate(c) for c in raw]

    def get_active_eval_lock(self) -> str | None:
        with self._lock:
            lock = self._read_dict(self._root / "eval_lock.json")
            return lock.get("run_id")

    def acquire_eval_lock(self, run_id: str) -> bool:
        with self._lock:
            path = self._root / "eval_lock.json"
            lock = self._read_dict(path)
            if lock.get("run_id"):
                return False
            self._write_dict(path, {"run_id": run_id, "started_at": datetime.now(timezone.utc).isoformat()})
            return True

    def release_eval_lock(self) -> None:
        with self._lock:
            path = self._root / "eval_lock.json"
            if path.exists():
                path.unlink()

    # ── helpers ────────────────────────────────────────────────────────────
    def _read_list(self, path: Path) -> list[Any]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_list(self, path: Path, items: list[Any]) -> None:
        path.write_text(json.dumps(items, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    def _read_dict(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_dict(self, path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


_STORE = None


def get_legal_knowledge_store():
    """Production default: DynamoDB. Explicit LEGAL_KNOWLEDGE_STORE=file for local/tests."""
    global _STORE
    if _STORE is not None:
        return _STORE
    from payroll_copilot.infrastructure.config.settings import get_settings

    settings = get_settings()
    backend = (getattr(settings, "legal_knowledge_store", None) or "dynamodb").strip().lower()
    if backend in {"file", "filesystem", "local"}:
        root = getattr(settings, "legal_knowledge_data_path", None) or "data/legal_knowledge"
        from payroll_copilot.infrastructure.rag.data_paths import resolve_runtime_data_path

        _STORE = LegalKnowledgeStore(resolve_runtime_data_path(root))
        return _STORE

    # Production / default — DynamoDB. Failures must be observable (no silent file fallback).
    from payroll_copilot.infrastructure.persistence.dynamodb.client import get_dynamo_table
    from payroll_copilot.infrastructure.persistence.dynamodb.legal_knowledge import (
        DynamoLegalKnowledgeRepository,
    )

    _STORE = DynamoLegalKnowledgeRepository(get_dynamo_table())
    return _STORE


def reset_legal_knowledge_store() -> None:
    global _STORE
    _STORE = None
