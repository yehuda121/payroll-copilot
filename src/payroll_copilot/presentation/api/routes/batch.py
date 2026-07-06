"""Batch payslip processing routes."""

from uuid import uuid4

from fastapi import APIRouter, File, UploadFile, status
from pydantic import BaseModel, Field

from payroll_copilot.infrastructure.tasks.celery_app import process_bulk_payslip_pdf

router = APIRouter()


class BatchJobResponse(BaseModel):
    batch_job_id: str
    status: str


class BatchJobStatusResponse(BaseModel):
    id: str
    status: str
    total_slips: int = 0
    processed_slips: int = 0
    failed_slips: int = 0
    progress_percent: float = 0.0


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

    task = process_bulk_payslip_pdf.delay(batch_job_id, document_id)

    return BatchJobResponse(batch_job_id=batch_job_id, status="queued")


@router.get("/jobs/{batch_job_id}", response_model=BatchJobStatusResponse)
async def get_batch_job_status(batch_job_id: str) -> BatchJobStatusResponse:
    return BatchJobStatusResponse(
        id=batch_job_id,
        status="queued",
        total_slips=0,
        processed_slips=0,
        progress_percent=0.0,
    )


@router.get("/jobs/{batch_job_id}/report", response_model=BatchReportResponse)
async def get_batch_report(batch_job_id: str) -> BatchReportResponse:
    return BatchReportResponse(
        summary={"total": 0, "passed": 0, "warnings": 0, "critical": 0},
        items=[],
    )
