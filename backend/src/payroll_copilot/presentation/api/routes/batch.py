"""Batch payslip processing routes with stage-level progress."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, File, UploadFile, status
from pydantic import BaseModel, Field

from payroll_copilot.application.services.batch_progress_store import get_batch_progress_store
from payroll_copilot.infrastructure.tasks.celery_app import process_bulk_payslip_pdf

router = APIRouter()


class BatchJobResponse(BaseModel):
    batch_job_id: str
    status: str


class StageProgressResponse(BaseModel):
    key: str
    label: str
    status: str
    detail: str | None = None


class BatchJobStatusResponse(BaseModel):
    id: str
    batch_job_id: str | None = None
    status: str
    current_stage: str = "upload"
    total_slips: int = 0
    processed_slips: int = 0
    failed_slips: int = 0
    progress_percent: float = 0.0
    source_filename: str | None = None
    error_message: str | None = None
    report_summary: dict[str, int] = Field(default_factory=dict)
    stages: list[StageProgressResponse] = Field(default_factory=list)
    updated_at: str | None = None
    created_at: str | None = None


class BatchReportItem(BaseModel):
    employee_number: str
    employee_name: str
    department: str
    overall_result: str
    critical_issues: int
    warnings: int
    recommendations: int
    confidence: float
    validation_run_id: str


class BatchReportResponse(BaseModel):
    summary: dict[str, int]
    items: list[BatchReportItem] = Field(default_factory=list)


@router.post("/payslips", response_model=BatchJobResponse, status_code=202)
async def upload_bulk_payslips(file: UploadFile = File(...)) -> BatchJobResponse:
    batch_job_id = str(uuid4())
    document_id = str(uuid4())

    content = await file.read()
    from payroll_copilot.infrastructure.config.settings import get_settings
    from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage

    settings = get_settings()
    storage = S3ObjectStorage(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )
    await storage.upload(f"documents/{document_id}", content, "application/pdf")

    store = get_batch_progress_store()
    store.create(
        batch_job_id,
        document_id=document_id,
        source_filename=file.filename,
    )
    store.mark_stage(
        batch_job_id,
        "split",
        status="running",
        job_status="running",
        detail="Queued for background split",
    )

    process_bulk_payslip_pdf.delay(batch_job_id, document_id)

    return BatchJobResponse(batch_job_id=batch_job_id, status="queued")


@router.get("/jobs", response_model=list[BatchJobStatusResponse])
async def list_batch_jobs() -> list[BatchJobStatusResponse]:
    store = get_batch_progress_store()
    return [BatchJobStatusResponse(**job.to_dict()) for job in store.list_recent()]


@router.get("/jobs/{batch_job_id}", response_model=BatchJobStatusResponse)
async def get_batch_job_status(batch_job_id: str) -> BatchJobStatusResponse:
    store = get_batch_progress_store()
    job = store.get(batch_job_id)
    if job is None:
        return BatchJobStatusResponse(
            id=batch_job_id,
            batch_job_id=batch_job_id,
            status="unknown",
            current_stage="upload",
            stages=[],
        )
    return BatchJobStatusResponse(**job.to_dict())


@router.get("/jobs/{batch_job_id}/report", response_model=BatchReportResponse)
async def get_batch_report(batch_job_id: str) -> BatchReportResponse:
    store = get_batch_progress_store()
    job = store.get(batch_job_id)
    summary = job.report_summary if job else {"total": 0, "passed": 0, "warnings": 0, "critical": 0}
    if not summary:
        summary = {"total": 0, "passed": 0, "warnings": 0, "critical": 0}
    return BatchReportResponse(summary=summary, items=[])
