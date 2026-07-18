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
class BatchExtractedItem:
    """Incrementally published per-slip result for accountant batch UX."""

    id: str
    slip_index: int
    status: str = "processing"
    employee_number: str | None = None
    employee_name: str | None = None
    document_id: str | None = None
    national_id_masked: str | None = None
    payroll_year: int | None = None
    payroll_month: int | None = None
    warnings: int = 0
    critical_issues: int = 0
    processing_stage: str = "queued"
    validation_run_id: str | None = None
    review_status: str = "pending_review"
    publication_status: str = "draft"
    error_message: str | None = None
    resolution_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "slip_index": self.slip_index,
            "status": self.status,
            "employee_number": self.employee_number,
            "employee_name": self.employee_name,
            "document_id": self.document_id,
            "national_id_masked": self.national_id_masked,
            "payroll_year": self.payroll_year,
            "payroll_month": self.payroll_month,
            "warnings": self.warnings,
            "critical_issues": self.critical_issues,
            "processing_stage": self.processing_stage,
            "validation_run_id": self.validation_run_id,
            "review_status": self.review_status,
            "publication_status": self.publication_status,
            "error_message": self.error_message,
            "resolution_status": self.resolution_status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BatchExtractedItem:
        return cls(
            id=str(payload["id"]),
            slip_index=int(payload.get("slip_index", 0)),
            status=str(payload.get("status", "processing")),
            employee_number=payload.get("employee_number"),
            employee_name=payload.get("employee_name"),
            document_id=payload.get("document_id"),
            national_id_masked=payload.get("national_id_masked"),
            payroll_year=payload.get("payroll_year"),
            payroll_month=payload.get("payroll_month"),
            warnings=int(payload.get("warnings", 0)),
            critical_issues=int(payload.get("critical_issues", 0)),
            processing_stage=str(payload.get("processing_stage", "queued")),
            validation_run_id=payload.get("validation_run_id"),
            review_status=str(payload.get("review_status", "pending_review")),
            publication_status=str(payload.get("publication_status", "draft")),
            error_message=payload.get("error_message"),
            resolution_status=payload.get("resolution_status"),
        )


@dataclass
class BatchJobProgress:
    batch_job_id: str
    organization_id: str | None = None
    created_by_user_id: str | None = None
    status: str = "queued"  # queued | running | completed | failed
    current_stage: str = "upload"
    total_slips: int = 0
    processed_slips: int = 0
    failed_slips: int = 0
    source_filename: str | None = None
    document_id: str | None = None
    error_message: str | None = None
    report_summary: dict[str, int] = field(default_factory=dict)
    items: list[BatchExtractedItem] = field(default_factory=list)
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
        if self.total_slips > 0:
            return round(
                100.0 * min(self.processed_slips, self.total_slips) / self.total_slips,
                1,
            )
        if not self.stages:
            return 0.0
        completed = sum(1 for stage in self.stages if stage.status == "completed")
        return round(100.0 * completed / len(self.stages), 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.batch_job_id,
            "batch_job_id": self.batch_job_id,
            "organization_id": self.organization_id,
            "created_by_user_id": self.created_by_user_id,
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
            "items": [item.to_dict() for item in self.items],
            "stages": [stage.to_dict() for stage in self.stages],
            "updated_at": self.updated_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BatchJobProgress:
        stages = [StageProgress.from_dict(item) for item in payload.get("stages", [])]
        job = cls(
            batch_job_id=str(payload.get("batch_job_id") or payload.get("id")),
            organization_id=(
                str(payload["organization_id"])
                if payload.get("organization_id") is not None
                else None
            ),
            created_by_user_id=payload.get("created_by_user_id"),
            status=str(payload.get("status", "queued")),
            current_stage=str(payload.get("current_stage", "upload")),
            total_slips=int(payload.get("total_slips", 0)),
            processed_slips=int(payload.get("processed_slips", 0)),
            failed_slips=int(payload.get("failed_slips", 0)),
            source_filename=payload.get("source_filename"),
            document_id=payload.get("document_id"),
            error_message=payload.get("error_message"),
            report_summary=dict(payload.get("report_summary") or {}),
            items=[
                BatchExtractedItem.from_dict(item)
                for item in payload.get("items", [])
            ],
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
        organization_id: str | None = None,
        created_by_user_id: str | None = None,
        document_id: str | None = None,
        source_filename: str | None = None,
    ) -> BatchJobProgress: ...

    def get(self, batch_job_id: str) -> BatchJobProgress | None: ...

    def list_recent(
        self,
        *,
        limit: int = 50,
        organization_id: str | None = None,
    ) -> list[BatchJobProgress]: ...

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

    def upsert_item(
        self,
        batch_job_id: str,
        item: BatchExtractedItem,
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
        organization_id: str | None = None,
        created_by_user_id: str | None = None,
        document_id: str | None = None,
        source_filename: str | None = None,
    ) -> BatchJobProgress:
        job = BatchJobProgress(
            batch_job_id=batch_job_id,
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
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

    def list_recent(
        self,
        *,
        limit: int = 50,
        organization_id: str | None = None,
    ) -> list[BatchJobProgress]:
        with self._lock:
            jobs = [
                job
                for job in self._jobs.values()
                if organization_id is None or job.organization_id == organization_id
            ]
            jobs.sort(key=lambda item: item.created_at, reverse=True)
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

    def upsert_item(
        self,
        batch_job_id: str,
        item: BatchExtractedItem,
    ) -> BatchJobProgress | None:
        with self._lock:
            job = self._jobs.get(batch_job_id)
            if job is None:
                return None
            self._apply_item_update(job, item)
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

    @staticmethod
    def _apply_item_update(
        job: BatchJobProgress,
        item: BatchExtractedItem,
    ) -> None:
        index = next(
            (idx for idx, existing in enumerate(job.items) if existing.id == item.id),
            None,
        )
        if index is None:
            job.items.append(item)
            job.items.sort(key=lambda row: row.slip_index)
        else:
            job.items[index] = item
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
        organization_id: str | None = None,
        created_by_user_id: str | None = None,
        document_id: str | None = None,
        source_filename: str | None = None,
    ) -> BatchJobProgress:
        job = BatchJobProgress(
            batch_job_id=batch_job_id,
            organization_id=organization_id,
            created_by_user_id=created_by_user_id,
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

    def list_recent(
        self,
        *,
        limit: int = 50,
        organization_id: str | None = None,
    ) -> list[BatchJobProgress]:
        # Fetch a bounded superset because the Redis index is shared by tenants.
        scan_limit = max(limit, min(500, limit * 10))
        ids = self._redis.zrevrange(_REDIS_INDEX_KEY, 0, max(0, scan_limit - 1))
        jobs: list[BatchJobProgress] = []
        for batch_job_id in ids:
            key = batch_job_id.decode() if isinstance(batch_job_id, bytes) else str(batch_job_id)
            job = self.get(key)
            if job is not None and (
                organization_id is None or job.organization_id == organization_id
            ):
                jobs.append(job)
                if len(jobs) >= limit:
                    break
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

    def upsert_item(
        self,
        batch_job_id: str,
        item: BatchExtractedItem,
    ) -> BatchJobProgress | None:
        job = self.get(batch_job_id)
        if job is None:
            return None
        InMemoryBatchProgressStore._apply_item_update(job, item)
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
