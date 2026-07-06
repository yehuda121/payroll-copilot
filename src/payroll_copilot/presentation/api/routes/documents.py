"""Document upload and management routes."""

from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage

router = APIRouter()


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: str
    processing_job_id: str | None = None


class DocumentResponse(BaseModel):
    document_id: str
    document_type: str
    status: str
    original_filename: str
    file_size_bytes: int


def _get_storage() -> S3ObjectStorage:
    settings = get_settings()
    return S3ObjectStorage(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        use_ssl=settings.s3_use_ssl,
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    employee_id: str | None = Form(None),
    period_year: int | None = Form(None),
    period_month: int | None = Form(None),
) -> DocumentUploadResponse:
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if document_type == DocumentType.BULK_PAYSLIP_PDF:
        max_size = settings.max_bulk_pdf_size_mb * 1024 * 1024

    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {max_size // (1024*1024)}MB",
        )

    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    document_id = str(uuid4())
    checksum = hashlib.sha256(content).hexdigest()
    storage_key = f"documents/{document_id}/{file.filename or 'upload'}"

    storage = _get_storage()
    await storage.upload(storage_key, content, file.content_type or "application/octet-stream")

    from payroll_copilot.infrastructure.tasks.celery_app import (
        import_employee_excel,
        process_document_ocr,
    )

    job_id = None
    if document_type == DocumentType.EMPLOYEE_EXCEL:
        result = import_employee_excel.delay(document_id, "")
        job_id = result.id
    else:
        result = process_document_ocr.delay(document_id)
        job_id = result.id

    return DocumentUploadResponse(
        document_id=document_id,
        status="uploaded",
        processing_job_id=job_id,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str) -> DocumentResponse:
    return DocumentResponse(
        document_id=document_id,
        document_type="payslip",
        status="uploaded",
        original_filename="",
        file_size_bytes=0,
    )
