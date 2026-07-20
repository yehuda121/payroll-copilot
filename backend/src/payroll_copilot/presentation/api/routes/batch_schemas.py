"""Batch API request/response schemas (presentation only).

Extracted from the batch router so orchestration stays in ``batch.py`` while
Pydantic contracts live in a focused module. Contracts are unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BatchJobResponse(BaseModel):
    batch_job_id: str
    status: str


class StageProgressResponse(BaseModel):
    key: str
    label: str
    status: str
    detail: str | None = None


class BatchExtractedItemResponse(BaseModel):
    id: str
    slip_index: int
    status: str
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
    items: list[BatchExtractedItemResponse] = Field(default_factory=list)
    updated_at: str | None = None
    created_at: str | None = None


class BatchReportResponse(BaseModel):
    summary: dict[str, int]
    items: list[BatchExtractedItemResponse] = Field(default_factory=list)


class BatchItemResolutionRequest(BaseModel):
    action: str = Field(pattern="^(ignore|edit_national_id|attach_employee)$")
    national_id: str | None = Field(default=None, min_length=5, max_length=32)
    employee_number: str | None = Field(default=None, min_length=1, max_length=50)


class BatchPublishResponse(BaseModel):
    document_id: str
    employee_number: str
    payroll_year: int
    payroll_month: int
    published_at: str
    validation_run_id: str
    publication_status: str = "published"


class BatchReviewCorrection(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    value: object | None = None
    clear: bool = False


class BatchReviewCorrectionRequest(BaseModel):
    corrections: list[BatchReviewCorrection] = Field(default_factory=list)


class BatchItemReviewResponse(BaseModel):
    item: BatchExtractedItemResponse
    document_id: str
    original_filename: str
    uploaded_at: str | None = None
    fields: list[dict] = Field(default_factory=list)
    extraction_id: str | None = None
    extraction_version: int | None = None
    validation_history: list[dict] = Field(default_factory=list)
    explainability_enabled: bool = False
