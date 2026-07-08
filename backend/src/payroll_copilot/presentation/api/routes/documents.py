"""Document upload and management routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from kombu.exceptions import OperationalError as KombuOperationalError
from pydantic import BaseModel
from redis.exceptions import RedisError

from payroll_copilot.application.exceptions import DocumentUploadRejectedError
from payroll_copilot.application.services.document_upload_guardrail import (
    DocumentUploadGuardrailService,
)
from payroll_copilot.application.use_cases.documents import (
    GetDocumentUseCase,
    UploadDocumentCommand,
    UploadDocumentUseCase,
)
from payroll_copilot.domain.entities import Document
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.presentation.api.dependencies import (
    get_get_document_use_case,
    get_upload_document_use_case,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_upload_guardrail = DocumentUploadGuardrailService(get_settings())

# Connection-level failures that mean the broker/result store is unreachable.
# getaddrinfo/connection-refused surface as OSError (socket.gaierror is a subclass).
_ENQUEUE_CONNECTION_ERRORS = (KombuOperationalError, RedisError, OSError)


_ALLOWED_DOCUMENT_LANGUAGES = frozenset({"he", "en", "ar", "auto"})


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: str
    processing_job_id: str | None = None
    background_status: str = "queued"
    document_language: str = "auto"
    ocr_language_status: str = "not_connected"


class DocumentResponse(BaseModel):
    document_id: str
    document_type: str
    status: str
    original_filename: str
    file_size_bytes: int
    document_language: str = "auto"
    ocr_language_status: str = "not_connected"


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}: must be a valid UUID",
        ) from exc


def _document_language(document: Document) -> str:
    value = document.metadata.get("document_language", "auto")
    return value if isinstance(value, str) else "auto"


def _to_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        document_id=str(document.id),
        document_type=document.document_type.value,
        status=document.status.value,
        original_filename=document.original_filename,
        file_size_bytes=document.file_size_bytes,
        document_language=_document_language(document),
        ocr_language_status="not_connected",
    )


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    employee_id: str | None = Form(None),
    period_year: int | None = Form(None),
    period_month: int | None = Form(None),
    document_language: str = Form("auto"),
    upload_use_case: UploadDocumentUseCase = Depends(get_upload_document_use_case),
) -> DocumentUploadResponse:
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    if document_type == DocumentType.BULK_PAYSLIP_PDF:
        max_size = settings.max_bulk_pdf_size_mb * 1024 * 1024

    normalized_language = document_language.strip().lower()
    if normalized_language not in _ALLOWED_DOCUMENT_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid document_language: must be one of he, en, ar, auto",
        )

    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {max_size // (1024*1024)}MB",
        )

    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    parsed_employee_id = (
        _parse_uuid(employee_id, "employee_id") if employee_id is not None else None
    )

    upload_command = UploadDocumentCommand(
        content=content,
        original_filename=file.filename or "upload",
        mime_type=file.content_type or "application/octet-stream",
        document_type=document_type,
        employee_id=parsed_employee_id,
        period_year=period_year,
        period_month=period_month,
        uploaded_by_user_id=None,
        document_language=normalized_language,
    )

    try:
        _upload_guardrail.validate(upload_command)
    except DocumentUploadRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        ) from exc

    document = await upload_use_case.execute(upload_command)

    # The document is already persisted. Enqueuing background processing is
    # best-effort: if the Celery broker (Redis) is unavailable, the upload must
    # still succeed. We never roll back a persisted document over a queue failure.
    from payroll_copilot.infrastructure.tasks.celery_app import (
        import_employee_excel,
        process_document_ocr,
    )

    job_id: str | None = None
    background_status = "queued"
    try:
        if document_type == DocumentType.EMPLOYEE_EXCEL:
            result = import_employee_excel.delay(str(document.id), "")
        else:
            result = process_document_ocr.delay(str(document.id))
        job_id = result.id
    except _ENQUEUE_CONNECTION_ERRORS:
        background_status = "not_queued"
        logger.warning(
            "Document %s persisted, but background processing could not be enqueued "
            "(Celery/Redis unavailable). Returning success with background_status='not_queued'.",
            document.id,
            exc_info=True,
        )

    return DocumentUploadResponse(
        document_id=str(document.id),
        status=document.status.value,
        processing_job_id=job_id,
        background_status=background_status,
        document_language=normalized_language,
        ocr_language_status="not_connected",
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    get_use_case: GetDocumentUseCase = Depends(get_get_document_use_case),
) -> DocumentResponse:
    parsed_id = _parse_uuid(document_id, "document_id")
    document = await get_use_case.execute(parsed_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    return _to_response(document)
