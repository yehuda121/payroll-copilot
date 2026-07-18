"""Document upload and management routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
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
from payroll_copilot.application.services.employee_document_lifecycle import (
    is_employee_visible_document,
)
from payroll_copilot.domain.entities import Document
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.domain.value_objects import PayPeriod
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence import dynamodb as dynamo_persistence
from payroll_copilot.presentation.api.dependencies import (
    get_get_document_use_case,
    get_object_storage,
    get_upload_document_use_case,
)
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    BoundEmployeeContext,
    bind_accountant_selected_employee,
    get_auth_principal,
    require_accountant,
    require_bound_employee,
)
from payroll_copilot.infrastructure.storage.s3_storage import S3ObjectStorage

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


@router.post("/employee/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_employee_owned_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    period_year: int | None = Form(None),
    period_month: int | None = Form(None),
    document_language: str = Form("auto"),
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    upload_use_case: UploadDocumentUseCase = Depends(get_upload_document_use_case),
) -> DocumentUploadResponse:
    """Authenticated employee document upload — ownership forced from principal."""
    allowed = {
        DocumentType.ATTENDANCE,
        DocumentType.CONTRACT,
        DocumentType.NATIONAL_ID,
        DocumentType.ID_APPENDIX,
        DocumentType.PAYSLIP,
    }
    if document_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unsupported_employee_document_type",
                "message": "Unsupported employee document type.",
            },
        )
    persistent = document_type in {
        DocumentType.CONTRACT,
        DocumentType.NATIONAL_ID,
        DocumentType.ID_APPENDIX,
    }
    if not persistent:
        if (
            period_year is None
            or period_month is None
            or period_month < 1
            or period_month > 12
            or period_year < 2000
            or period_year > 2100
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_period", "message": "Invalid payroll period."},
            )
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    normalized_language = document_language.strip().lower()
    if normalized_language not in _ALLOWED_DOCUMENT_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid document_language: must be one of he, en, ar, auto",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb}MB",
        )
    upload_command = UploadDocumentCommand(
        content=content,
        original_filename=file.filename or "upload",
        mime_type=file.content_type or "application/octet-stream",
        document_type=document_type,
        employee_id=bound.employee.id,
        organization_id=bound.employee.organization_id,
        period_year=None if persistent else period_year,
        period_month=None if persistent else period_month,
        uploaded_by_user_id=bound.principal.user_id,
        document_language=normalized_language,
    )
    try:
        _upload_guardrail.validate(upload_command)
    except DocumentUploadRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "upload_rejected", "message": exc.message},
        ) from exc

    document = await upload_use_case.execute(upload_command)
    if document_type == DocumentType.PAYSLIP:
        meta = dict(document.metadata or {})
        meta["lifecycle_status"] = "uploaded_awaiting_extraction"
        meta["selected_period_year"] = period_year
        meta["selected_period_month"] = period_month
        document.metadata = meta
        await dynamo_persistence.get_document_repository().save(document)
    return DocumentUploadResponse(
        document_id=str(document.id),
        status=document.status.value,
        processing_job_id=None,
        background_status="not_queued",
        document_language=normalized_language,
        ocr_language_status="not_connected",
    )


class ResolvePeriodBody(BaseModel):
    action: str  # keep | move | cancel


@router.delete("/employee/{document_id}")
async def delete_employee_owned_document(
    document_id: str,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    storage: S3ObjectStorage = Depends(get_object_storage),
) -> dict:
    """Permanently delete an employee-owned document and its extractions."""
    parsed_id = _parse_uuid(document_id, "document_id")
    documents = dynamo_persistence.get_document_repository()
    document = await documents.get_by_id(parsed_id)
    if (
        document is None
        or document.employee_id != bound.employee.id
        or document.organization_id != bound.employee.organization_id
        or (
            bound.principal.role == "employee"
            and not is_employee_visible_document(document)
        )
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        await storage.delete(document.storage_key)
    except Exception:
        logger.warning("Failed to delete storage object for document %s", document_id, exc_info=True)
    await dynamo_persistence.get_document_extraction_repository().delete_for_document_ids([parsed_id])
    await documents.delete_by_ids([parsed_id])
    return {"document_id": str(parsed_id), "deleted": True}


@router.post("/employee/{document_id}/resolve-period")
async def resolve_employee_payslip_period(
    document_id: str,
    body: ResolvePeriodBody,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> dict:
    """Explicitly resolve a selected-vs-extracted period mismatch."""
    parsed_id = _parse_uuid(document_id, "document_id")
    documents = dynamo_persistence.get_document_repository()
    document = await documents.get_by_id(parsed_id)
    if (
        document is None
        or document.employee_id != bound.employee.id
        or document.organization_id != bound.employee.organization_id
        or (
            bound.principal.role == "employee"
            and not is_employee_visible_document(document)
        )
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    action = body.action.strip().lower()
    meta = dict(document.metadata or {})
    extracted_year = meta.get("extracted_period_year")
    extracted_month = meta.get("extracted_period_month")
    if action == "cancel":
        return {"document_id": str(document.id), "action": "cancel", "resolved": False}
    if action == "keep":
        from payroll_copilot.application.services.employee_workspace_snapshot import (
            patch_period_resolution_keep,
        )

        document.metadata = patch_period_resolution_keep(meta)
        await documents.save(document)
        return {"document_id": str(document.id), "action": "keep", "resolved": True}
    if action == "move":
        if extracted_year is None or extracted_month is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "period_unknown", "message": "Extracted period is unavailable."},
            )
        year = int(extracted_year)
        month = int(extracted_month)
        document.period = PayPeriod(year=year, month=month)
        meta["selected_period_year"] = year
        meta["selected_period_month"] = month
        meta["period_resolution"] = "moved_to_extracted"
        period = dict(meta.get("period_check") or {})
        if period:
            period["status"] = "match"
            period["blocks_confirmation"] = False
            period["selected_year"] = year
            period["selected_month"] = month
            period["extracted_year"] = year
            period["extracted_month"] = month
            period["explanation_code"] = "period_match"
            meta["period_check"] = period
        identity = meta.get("identity_check") if isinstance(meta.get("identity_check"), dict) else {}
        meta["blocks_confirmation"] = bool(identity.get("blocks_confirmation"))
        document.metadata = meta
        await documents.save(document)
        return {
            "document_id": str(document.id),
            "action": "move",
            "resolved": True,
            "period_year": year,
            "period_month": month,
        }
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "invalid_action", "message": "action must be keep, move, or cancel."},
    )


@router.get("/employee/{document_id}/content")
async def download_employee_document_content(
    document_id: str,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    storage: S3ObjectStorage = Depends(get_object_storage),
) -> Response:
    """Stream an employee-owned document for the Original Document tab."""
    parsed_id = _parse_uuid(document_id, "document_id")
    document = await dynamo_persistence.get_document_repository().get_by_id(parsed_id)
    if (
        document is None
        or document.employee_id != bound.employee.id
        or document.organization_id != bound.employee.organization_id
        or (
            bound.principal.role == "employee"
            and not is_employee_visible_document(document)
        )
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        content = await storage.download(document.storage_key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document content is unavailable.",
        ) from exc
    return Response(
        content=content,
        media_type=document.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{document.original_filename or "document"}"'
        },
    )


async def _accountant_document_context(
    employee_number: str,
    principal: AuthPrincipal,
) -> BoundEmployeeContext:
    return await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )


@router.post(
    "/accountant/{employee_number}/upload",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_accountant_selected_document(
    employee_number: str,
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    period_year: int | None = Form(None),
    period_month: int | None = Form(None),
    document_language: str = Form("auto"),
    principal: AuthPrincipal = Depends(require_accountant),
    upload_use_case: UploadDocumentUseCase = Depends(get_upload_document_use_case),
) -> DocumentUploadResponse:
    return await upload_employee_owned_document(
        file=file,
        document_type=document_type,
        period_year=period_year,
        period_month=period_month,
        document_language=document_language,
        bound=await _accountant_document_context(employee_number, principal),
        upload_use_case=upload_use_case,
    )


@router.delete("/accountant/{employee_number}/{document_id}")
async def delete_accountant_selected_document(
    employee_number: str,
    document_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
    storage: S3ObjectStorage = Depends(get_object_storage),
) -> dict:
    return await delete_employee_owned_document(
        document_id=document_id,
        bound=await _accountant_document_context(employee_number, principal),
        storage=storage,
    )


@router.post("/accountant/{employee_number}/{document_id}/resolve-period")
async def resolve_accountant_selected_payslip_period(
    employee_number: str,
    document_id: str,
    body: ResolvePeriodBody,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict:
    return await resolve_employee_payslip_period(
        document_id=document_id,
        body=body,
        bound=await _accountant_document_context(employee_number, principal),
    )


@router.get("/accountant/{employee_number}/{document_id}/content")
async def download_accountant_selected_document_content(
    employee_number: str,
    document_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
    storage: S3ObjectStorage = Depends(get_object_storage),
) -> Response:
    return await download_employee_document_content(
        document_id=document_id,
        bound=await _accountant_document_context(employee_number, principal),
        storage=storage,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    get_use_case: GetDocumentUseCase = Depends(get_get_document_use_case),
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> DocumentResponse:
    parsed_id = _parse_uuid(document_id, "document_id")
    document = await get_use_case.execute(parsed_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    if principal.organization_id != document.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    if principal.role == "employee" and (
        principal.employee_id != document.employee_id
        or not is_employee_visible_document(document)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    return _to_response(document)
