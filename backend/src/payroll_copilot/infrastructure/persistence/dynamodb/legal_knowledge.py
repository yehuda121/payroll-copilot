"""DynamoDB-backed legal knowledge repository (system partition LEGAL#SYSTEM).

Access patterns (no tenant leakage — system-wide legal knowledge only):
  PK=LEGAL#SYSTEM SK=SYNCRUN#{iso}#{run_id}
  PK=LEGAL#SYSTEM SK=RUNID#{run_id}
  PK=LEGAL#SYSTEM SK=PROPOSAL#{iso}#{id}
  PK=LEGAL#SYSTEM SK=PROPID#{id}
  PK=LEGAL#SYSTEM SK=SRCSTATE#{source_id}
  PK=LEGAL#SYSTEM SK=SNAP#{snapshot_id}
  PK=LEGAL#SYSTEM SK=DISCOVERY#{item_key}
  PK=LEGAL#SYSTEM SK=EVALRUN#{iso}#{run_id}
  PK=LEGAL#SYSTEM SK=EVALID#{run_id}
  PK=LEGAL#SYSTEM SK=EVALCASE#{run_id}#{case_id}
  PK=LEGAL#SYSTEM SK=EVALLOCK
  PK=LEGAL#SYSTEM SK=VECTORHEALTH
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from botocore.exceptions import ClientError

from payroll_copilot.application.dto.legal_knowledge import (
    EvaluationCaseResult,
    EvaluationRun,
    LegalChangeProposal,
    LegalSyncRun,
    ProposalStatus,
    VectorIndexHealth,
)
from payroll_copilot.infrastructure.persistence.dynamodb.client import DynamoTable

logger = logging.getLogger(__name__)

LEGAL_PK = "LEGAL#SYSTEM"
_MAX_SNAPSHOT_CHARS = 200_000


def _run_sync(coro):
    """Run async Dynamo helpers from sync service methods safely."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class DynamoLegalKnowledgeRepository:
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def save_sync_run(self, run: LegalSyncRun) -> LegalSyncRun:
        return _run_sync(self._save_sync_run(run))

    async def _save_sync_run(self, run: LegalSyncRun) -> LegalSyncRun:
        payload = json.dumps(run.model_dump(mode="json"), default=str)
        started = (
            run.started_at.isoformat()
            if isinstance(run.started_at, datetime)
            else str(run.started_at)
        )
        sk = f"SYNCRUN#{started}#{run.run_id}"
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": sk,
                "entity_type": "legal_sync_run",
                "run_id": run.run_id,
                "payload_json": payload,
            }
        )
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": f"RUNID#{run.run_id}",
                "entity_type": "legal_sync_run_id",
                "payload_json": payload,
            }
        )
        return run

    def list_sync_runs(self, *, limit: int = 50) -> list[LegalSyncRun]:
        return _run_sync(self._list_sync_runs(limit))

    async def _list_sync_runs(self, limit: int) -> list[LegalSyncRun]:
        items = await self._table.query_eq_pk(
            LEGAL_PK, sk_begins_with="SYNCRUN#", scan_index_forward=False
        )
        out: list[LegalSyncRun] = []
        for item in items[:limit]:
            raw = item.get("payload_json")
            if raw:
                out.append(LegalSyncRun.model_validate(json.loads(str(raw))))
        return out

    def get_sync_run(self, run_id: str) -> LegalSyncRun | None:
        return _run_sync(self._get_sync_run(run_id))

    async def _get_sync_run(self, run_id: str) -> LegalSyncRun | None:
        item = await self._table.get_item({"PK": LEGAL_PK, "SK": f"RUNID#{run_id}"})
        if not item or not item.get("payload_json"):
            return None
        return LegalSyncRun.model_validate(json.loads(str(item["payload_json"])))

    def save_proposal(self, proposal: LegalChangeProposal) -> LegalChangeProposal:
        return _run_sync(self._save_proposal(proposal))

    async def _save_proposal(self, proposal: LegalChangeProposal) -> LegalChangeProposal:
        payload = json.dumps(proposal.model_dump(mode="json"), default=str)
        created = (
            proposal.created_at.isoformat()
            if isinstance(proposal.created_at, datetime)
            else str(proposal.created_at)
        )
        sk = f"PROPOSAL#{created}#{proposal.proposal_id}"
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": sk,
                "entity_type": "legal_change_proposal",
                "proposal_id": proposal.proposal_id,
                "status": proposal.status.value,
                "source_id": proposal.source_id,
                "payload_json": payload,
            }
        )
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": f"PROPID#{proposal.proposal_id}",
                "entity_type": "legal_change_proposal_id",
                "payload_json": payload,
            }
        )
        return proposal

    def list_proposals(
        self, *, status: ProposalStatus | None = None, limit: int = 100
    ) -> list[LegalChangeProposal]:
        return _run_sync(self._list_proposals(status, limit))

    async def _list_proposals(
        self, status: ProposalStatus | None, limit: int
    ) -> list[LegalChangeProposal]:
        items = await self._table.query_eq_pk(
            LEGAL_PK, sk_begins_with="PROPOSAL#", scan_index_forward=False
        )
        out: list[LegalChangeProposal] = []
        for item in items:
            raw = item.get("payload_json")
            if not raw:
                continue
            proposal = LegalChangeProposal.model_validate(json.loads(str(raw)))
            if status and proposal.status != status:
                continue
            out.append(proposal)
            if len(out) >= limit:
                break
        return out

    def get_proposal(self, proposal_id: str) -> LegalChangeProposal | None:
        return _run_sync(self._get_proposal(proposal_id))

    async def _get_proposal(self, proposal_id: str) -> LegalChangeProposal | None:
        item = await self._table.get_item({"PK": LEGAL_PK, "SK": f"PROPID#{proposal_id}"})
        if not item or not item.get("payload_json"):
            return None
        return LegalChangeProposal.model_validate(json.loads(str(item["payload_json"])))

    def save_snapshot(self, *, source_id: str, content: str, content_hash: str) -> str:
        return _run_sync(
            self._save_snapshot(source_id=source_id, content=content, content_hash=content_hash)
        )

    async def _save_snapshot(self, *, source_id: str, content: str, content_hash: str) -> str:
        snap_id = f"{source_id}__{content_hash[:16]}__{uuid4().hex[:8]}"
        truncated = content[:_MAX_SNAPSHOT_CHARS]
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": f"SNAP#{snap_id}",
                "entity_type": "legal_source_snapshot",
                "source_id": source_id,
                "content_hash": content_hash,
                "content": truncated,
                "truncated": len(content) > _MAX_SNAPSHOT_CHARS,
            }
        )
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": f"SRCSTATE#{source_id}",
                "entity_type": "legal_source_state",
                "source_id": source_id,
                "last_content_hash": content_hash,
                "last_snapshot_id": snap_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return snap_id

    def get_source_state(self, source_id: str) -> dict:
        return _run_sync(self._get_source_state(source_id))

    async def _get_source_state(self, source_id: str) -> dict:
        item = await self._table.get_item({"PK": LEGAL_PK, "SK": f"SRCSTATE#{source_id}"})
        if not item:
            return {}
        return {
            "last_content_hash": item.get("last_content_hash"),
            "last_snapshot_id": item.get("last_snapshot_id"),
            "updated_at": item.get("updated_at"),
        }

    def read_snapshot(self, snapshot_id: str) -> str | None:
        return _run_sync(self._read_snapshot(snapshot_id))

    async def _read_snapshot(self, snapshot_id: str) -> str | None:
        item = await self._table.get_item({"PK": LEGAL_PK, "SK": f"SNAP#{snapshot_id}"})
        if not item:
            return None
        return str(item.get("content") or "")

    def remember_discovery_item(self, item_key: str, content_hash: str) -> None:
        _run_sync(self._remember_discovery(item_key, content_hash))

    async def _remember_discovery(self, item_key: str, content_hash: str) -> None:
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": f"DISCOVERY#{item_key}",
                "entity_type": "legal_discovery_seen",
                "content_hash": content_hash,
                "seen_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def discovery_seen(self, item_key: str, content_hash: str) -> bool:
        return _run_sync(self._discovery_seen(item_key, content_hash))

    async def _discovery_seen(self, item_key: str, content_hash: str) -> bool:
        item = await self._table.get_item({"PK": LEGAL_PK, "SK": f"DISCOVERY#{item_key}"})
        return bool(item and item.get("content_hash") == content_hash)

    def save_evaluation_run(self, run: EvaluationRun) -> EvaluationRun:
        return _run_sync(self._save_eval_run(run))

    async def _save_eval_run(self, run: EvaluationRun) -> EvaluationRun:
        payload = json.dumps(run.model_dump(mode="json"), default=str)
        started = (
            run.started_at.isoformat()
            if isinstance(run.started_at, datetime)
            else str(run.started_at)
        )
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": f"EVALRUN#{started}#{run.run_id}",
                "entity_type": "rag_evaluation_run",
                "run_id": run.run_id,
                "status": run.status,
                "payload_json": payload,
            }
        )
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": f"EVALID#{run.run_id}",
                "entity_type": "rag_evaluation_run_id",
                "payload_json": payload,
            }
        )
        return run

    def list_evaluation_runs(self, *, limit: int = 50) -> list[EvaluationRun]:
        return _run_sync(self._list_eval_runs(limit))

    async def _list_eval_runs(self, limit: int) -> list[EvaluationRun]:
        items = await self._table.query_eq_pk(
            LEGAL_PK, sk_begins_with="EVALRUN#", scan_index_forward=False
        )
        out: list[EvaluationRun] = []
        for item in items[:limit]:
            raw = item.get("payload_json")
            if raw:
                out.append(EvaluationRun.model_validate(json.loads(str(raw))))
        return out

    def get_evaluation_run(self, run_id: str) -> EvaluationRun | None:
        return _run_sync(self._get_eval_run(run_id))

    async def _get_eval_run(self, run_id: str) -> EvaluationRun | None:
        item = await self._table.get_item({"PK": LEGAL_PK, "SK": f"EVALID#{run_id}"})
        if not item or not item.get("payload_json"):
            return None
        return EvaluationRun.model_validate(json.loads(str(item["payload_json"])))

    def save_evaluation_cases(self, run_id: str, cases: list[EvaluationCaseResult]) -> None:
        _run_sync(self._save_eval_cases(run_id, cases))

    async def _save_eval_cases(self, run_id: str, cases: list[EvaluationCaseResult]) -> None:
        for case in cases:
            await self._table.put_item(
                {
                    "PK": LEGAL_PK,
                    "SK": f"EVALCASE#{run_id}#{case.case_id}",
                    "entity_type": "rag_evaluation_case",
                    "run_id": run_id,
                    "case_id": case.case_id,
                    "payload_json": json.dumps(case.model_dump(mode="json"), default=str),
                }
            )

    def list_evaluation_cases(self, run_id: str) -> list[EvaluationCaseResult]:
        return _run_sync(self._list_eval_cases(run_id))

    async def _list_eval_cases(self, run_id: str) -> list[EvaluationCaseResult]:
        items = await self._table.query_eq_pk(
            LEGAL_PK, sk_begins_with=f"EVALCASE#{run_id}#", scan_index_forward=True
        )
        out: list[EvaluationCaseResult] = []
        for item in items:
            raw = item.get("payload_json")
            if raw:
                out.append(EvaluationCaseResult.model_validate(json.loads(str(raw))))
        return out

    def get_active_eval_lock(self) -> str | None:
        return _run_sync(self._get_eval_lock())

    async def _get_eval_lock(self) -> str | None:
        item = await self._table.get_item({"PK": LEGAL_PK, "SK": "EVALLOCK"})
        return str(item["run_id"]) if item and item.get("run_id") else None

    def acquire_eval_lock(self, run_id: str) -> bool:
        return _run_sync(self._acquire_eval_lock(run_id))

    async def _acquire_eval_lock(self, run_id: str) -> bool:
        try:
            await self._table.put_item(
                {
                    "PK": LEGAL_PK,
                    "SK": "EVALLOCK",
                    "entity_type": "rag_evaluation_lock",
                    "run_id": run_id,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
                condition_expression="attribute_not_exists(run_id)",
            )
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                return False
            logger.warning("eval_lock_client_error", extra={"code": code})
            return False
        except Exception:  # noqa: BLE001
            existing = await self._get_eval_lock()
            return existing is None

    def release_eval_lock(self) -> None:
        _run_sync(self._release_eval_lock())

    async def _release_eval_lock(self) -> None:
        await self._table.delete_item({"PK": LEGAL_PK, "SK": "EVALLOCK"})

    def vector_health(self) -> VectorIndexHealth:
        return _run_sync(self._vector_health())

    async def _vector_health(self) -> VectorIndexHealth:
        item = await self._table.get_item({"PK": LEGAL_PK, "SK": "VECTORHEALTH"})
        if not item or not item.get("payload_json"):
            return VectorIndexHealth(backend="unknown", status="empty")
        return VectorIndexHealth.model_validate(json.loads(str(item["payload_json"])))

    def set_vector_error(self, message: str) -> None:
        health = self.vector_health()
        health.last_error = message
        health.status = "error"
        self.set_vector_health(health)

    def set_vector_health(self, health: VectorIndexHealth) -> None:
        _run_sync(self._set_vector_health(health))

    async def _set_vector_health(self, health: VectorIndexHealth) -> None:
        await self._table.put_item(
            {
                "PK": LEGAL_PK,
                "SK": "VECTORHEALTH",
                "entity_type": "legal_vector_health",
                "payload_json": json.dumps(health.model_dump(mode="json"), default=str),
            }
        )
