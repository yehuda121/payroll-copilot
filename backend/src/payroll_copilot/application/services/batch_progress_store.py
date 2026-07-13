"""Cross-process batch job progress store for pipeline UX.

Backend processing never depends on an open browser. Progress is shared via
Redis so API and Celery workers see the same stage state. An in-memory store
remains available for unit tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol

PIPELINE_STAGES: tuple[tuple[str, str], ...] = (
    ("upload", "Upload PDF"),
    ("split", "Split payslips"),
    ("ocr", "OCR"),
    ("parser", "Parser"),
    ("identify", "Employee identification"),
    ("validation", "Validation"),
    ("report", "Batch report"),
)

_REDIS_KEY_PREFIX = "payroll:batch_progress:"
_REDIS_INDEX_KEY = "payroll:batch_progress:index"


@dataclass
class StageProgress:
    key: str
    label: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StageProgress:
        return cls(
            key=str(payload["key"]),
            label=str(payload["label"]),
            status=str(payload.get("status", "pending")),
            detail=payload.get("detail"),
        )


@dataclass
class BatchJobProgress:
    batch_job_id: str
    status: str = "queued"  # queued | running | completed | failed
    current_stage: str = "upload"
    total_slips: int = 0
    processed_slips: int = 0
    failed_slips: int = 0
    source_filename: str | None = None
    document_id: str | None = None
    error_message: str | None = None
    report_summary: dict[str, int] = field(default_factory=dict)
    stages: list[StageProgress] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not self.stages:
            self.stages = [
                StageProgress(key=key, label=label) for key, label in PIPELINE_STAGES
            ]

    @property
    def progress_percent(self) -> float:
        if not self.stages:
            return 0.0
        completed = sum(1 for stage in self.stages if stage.status == "completed")
        return round(100.0 * completed / len(self.stages), 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.batch_job_id,
            "batch_job_id": self.batch_job_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "total_slips": self.total_slips,
            "processed_slips": self.processed_slips,
            "failed_slips": self.failed_slips,
            "progress_percent": self.progress_percent,
            "source_filename": self.source_filename,
            "document_id": self.document_id,
            "error_message": self.error_message,
            "report_summary": self.report_summary,
            "stages": [stage.to_dict() for stage in self.stages],
            "updated_at": self.updated_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BatchJobProgress:
        stages = [StageProgress.from_dict(item) for item in payload.get("stages", [])]
        job = cls(
            batch_job_id=str(payload.get("batch_job_id") or payload.get("id")),
            status=str(payload.get("status", "queued")),
            current_stage=str(payload.get("current_stage", "upload")),
            total_slips=int(payload.get("total_slips", 0)),
            processed_slips=int(payload.get("processed_slips", 0)),
            failed_slips=int(payload.get("failed_slips", 0)),
            source_filename=payload.get("source_filename"),
            document_id=payload.get("document_id"),
            error_message=payload.get("error_message"),
            report_summary=dict(payload.get("report_summary") or {}),
            stages=stages,
            updated_at=str(payload.get("updated_at") or datetime.now(UTC).isoformat()),
            created_at=str(payload.get("created_at") or datetime.now(UTC).isoformat()),
        )
        return job


class BatchProgressStoreProtocol(Protocol):
    def create(
        self,
        batch_job_id: str,
        *,
        document_id: str | None = None,
        source_filename: str | None = None,
    ) -> BatchJobProgress: ...

    def get(self, batch_job_id: str) -> BatchJobProgress | None: ...

    def list_recent(self, *, limit: int = 50) -> list[BatchJobProgress]: ...

    def mark_stage(
        self,
        batch_job_id: str,
        stage_key: str,
        *,
        status: str,
        detail: str | None = None,
        job_status: str | None = None,
        total_slips: int | None = None,
        processed_slips: int | None = None,
        failed_slips: int | None = None,
        report_summary: dict[str, int] | None = None,
        error_message: str | None = None,
    ) -> BatchJobProgress | None: ...


class InMemoryBatchProgressStore:
    """Thread-safe process-local progress registry (tests / fallback)."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, BatchJobProgress] = {}

    def create(
        self,
        batch_job_id: str,
        *,
        document_id: str | None = None,
        source_filename: str | None = None,
    ) -> BatchJobProgress:
        job = BatchJobProgress(
            batch_job_id=batch_job_id,
            document_id=document_id,
            source_filename=source_filename,
        )
        job.stages[0].status = "completed"
        job.stages[0].detail = source_filename or "Uploaded"
        job.current_stage = "split"
        with self._lock:
            self._jobs[batch_job_id] = job
        return job

    def get(self, batch_job_id: str) -> BatchJobProgress | None:
        with self._lock:
            return self._jobs.get(batch_job_id)

    def list_recent(self, *, limit: int = 50) -> list[BatchJobProgress]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
            return jobs[:limit]

    def mark_stage(
        self,
        batch_job_id: str,
        stage_key: str,
        *,
        status: str,
        detail: str | None = None,
        job_status: str | None = None,
        total_slips: int | None = None,
        processed_slips: int | None = None,
        failed_slips: int | None = None,
        report_summary: dict[str, int] | None = None,
        error_message: str | None = None,
    ) -> BatchJobProgress | None:
        with self._lock:
            job = self._jobs.get(batch_job_id)
            if job is None:
                return None
            self._apply_stage_update(
                job,
                stage_key,
                status=status,
                detail=detail,
                job_status=job_status,
                total_slips=total_slips,
                processed_slips=processed_slips,
                failed_slips=failed_slips,
                report_summary=report_summary,
                error_message=error_message,
            )
            return job

    @staticmethod
    def _apply_stage_update(
        job: BatchJobProgress,
        stage_key: str,
        *,
        status: str,
        detail: str | None,
        job_status: str | None,
        total_slips: int | None,
        processed_slips: int | None,
        failed_slips: int | None,
        report_summary: dict[str, int] | None,
        error_message: str | None,
    ) -> None:
        for stage in job.stages:
            if stage.key == stage_key:
                stage.status = status
                if detail is not None:
                    stage.detail = detail
                break
        job.current_stage = stage_key
        if job_status:
            job.status = job_status
        if total_slips is not None:
            job.total_slips = total_slips
        if processed_slips is not None:
            job.processed_slips = processed_slips
        if failed_slips is not None:
            job.failed_slips = failed_slips
        if report_summary is not None:
            job.report_summary = report_summary
        if error_message is not None:
            job.error_message = error_message
        job.updated_at = datetime.now(UTC).isoformat()


# Backward-compatible alias for unit tests
BatchProgressStore = InMemoryBatchProgressStore


class RedisBatchProgressStore:
    """Redis-backed progress registry shared by API and Celery workers."""

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client

    def create(
        self,
        batch_job_id: str,
        *,
        document_id: str | None = None,
        source_filename: str | None = None,
    ) -> BatchJobProgress:
        job = BatchJobProgress(
            batch_job_id=batch_job_id,
            document_id=document_id,
            source_filename=source_filename,
        )
        job.stages[0].status = "completed"
        job.stages[0].detail = source_filename or "Uploaded"
        job.current_stage = "split"
        self._save(job)
        self._redis.zadd(_REDIS_INDEX_KEY, {batch_job_id: datetime.now(UTC).timestamp()})
        return job

    def get(self, batch_job_id: str) -> BatchJobProgress | None:
        raw = self._redis.get(f"{_REDIS_KEY_PREFIX}{batch_job_id}")
        if not raw:
            return None
        return BatchJobProgress.from_dict(json.loads(raw))

    def list_recent(self, *, limit: int = 50) -> list[BatchJobProgress]:
        ids = self._redis.zrevrange(_REDIS_INDEX_KEY, 0, max(0, limit - 1))
        jobs: list[BatchJobProgress] = []
        for batch_job_id in ids:
            key = batch_job_id.decode() if isinstance(batch_job_id, bytes) else str(batch_job_id)
            job = self.get(key)
            if job is not None:
                jobs.append(job)
        return jobs

    def mark_stage(
        self,
        batch_job_id: str,
        stage_key: str,
        *,
        status: str,
        detail: str | None = None,
        job_status: str | None = None,
        total_slips: int | None = None,
        processed_slips: int | None = None,
        failed_slips: int | None = None,
        report_summary: dict[str, int] | None = None,
        error_message: str | None = None,
    ) -> BatchJobProgress | None:
        job = self.get(batch_job_id)
        if job is None:
            return None
        InMemoryBatchProgressStore._apply_stage_update(
            job,
            stage_key,
            status=status,
            detail=detail,
            job_status=job_status,
            total_slips=total_slips,
            processed_slips=processed_slips,
            failed_slips=failed_slips,
            report_summary=report_summary,
            error_message=error_message,
        )
        self._save(job)
        return job

    def _save(self, job: BatchJobProgress) -> None:
        self._redis.set(
            f"{_REDIS_KEY_PREFIX}{job.batch_job_id}",
            json.dumps(job.to_dict()),
        )


_STORE: BatchProgressStoreProtocol | None = None


def get_batch_progress_store() -> BatchProgressStoreProtocol:
    global _STORE
    if _STORE is not None:
        return _STORE
    try:
        import redis

        from payroll_copilot.infrastructure.config.service_resolver import get_resolved_redis_url
        from payroll_copilot.infrastructure.config.settings import get_settings

        client = redis.Redis.from_url(get_resolved_redis_url(get_settings()), decode_responses=True)
        client.ping()
        _STORE = RedisBatchProgressStore(client)
    except Exception:  # noqa: BLE001 — fall back so API still boots without Redis
        _STORE = InMemoryBatchProgressStore()
    return _STORE


def reset_batch_progress_store_for_tests() -> None:
    """Test helper to clear the singleton."""
    global _STORE
    _STORE = None
