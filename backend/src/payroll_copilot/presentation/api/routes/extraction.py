"""Guest payslip extraction orchestration API (OCR + parser + persistence)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from payroll_copilot.application.exceptions import (
    ConfirmationBlockedError,
    CorrectionNotAllowedError,
    DocumentNotFoundError,
    DocumentNotOwnedError,
    DocumentUploadRejectedError,
    DuplicatePayslipPeriodError,
    OcrError,
)
from payroll_copilot.application.use_cases.confirm_employee_extraction import (
    ConfirmEmployeeExtractionUseCase,
)
from payroll_copilot.application.services.document_upload_guardrail import (
    DocumentUploadGuardrailService,
)
from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectGuestExtractionUseCase,
    FieldCorrection,
)
from payroll_copilot.application.use_cases.correct_employee_extraction import (
    CorrectEmployeeExtractionUseCase,
)
from payroll_copilot.application.use_cases.documents import UploadDocumentCommand
from payroll_copilot.application.use_cases.extract_employee_payslip import (
    EmployeePayslipExtractionCommand,
    ExtractEmployeePayslipUseCase,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractedFieldView,
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
)
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.database import get_db_session
from payroll_copilot.infrastructure.persistence.repositories.audit_log_repository import (
    SqlAlchemyAuditLogRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.document_extraction_repository import (
    SqlAlchemyDocumentExtractionRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.employee_repository import (
    SqlAlchemyEmployeeRepository,
)
from payroll_copilot.presentation.api.dependencies import (
    get_correct_guest_extraction_use_case,
    get_extract_guest_payslip_use_case,
)
from payroll_copilot.presentation.api.security import BoundEmployeeContext, require_bound_employee
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
_upload_guardrail = DocumentUploadGuardrailService(get_settings())

_ALLOWED_LANGUAGES = frozenset({"he", "en", "ar", "auto"})


class ExtractedFieldResponse(BaseModel):
    key: str
    value: object | None = None
    confidence: float | None = None
    source_text: str | None = None
    status: str
    edited_by_user: bool = False
    original_value: object | None = None


class GuestPayslipExtractionResponse(BaseModel):
    document_id: str
    extraction_id: str
    extraction_version: int | None = None
    ocr_status: str
    parser_status: str
    language: str
    ocr_engine: str | None = None
    parser_model: str | None = None
    warnings: list[str] = Field(default_factory=list)
    fields: list[ExtractedFieldResponse] = Field(default_factory=list)
    error_message: str | None = None


class ComparisonFieldResponse(BaseModel):
    key: str
    status: str
    extracted_display: str | None = None
    expected_display: str | None = None
    severity: str
    blocks_confirmation: bool = False
    explanation_code: str | None = None


class IdentityCheckResponse(BaseModel):
    overall: str
    blocks_confirmation: bool
    fields: list[ComparisonFieldResponse] = Field(default_factory=list)


class PeriodCheckResponse(BaseModel):
    status: str
    blocks_confirmation: bool
    selected_year: int
    selected_month: int
    extracted_year: int | None = None
    extracted_month: int | None = None
    explanation_code: str | None = None


class EmployeePayslipExtractionResponse(GuestPayslipExtractionResponse):
    identity_check: IdentityCheckResponse
    period_check: PeriodCheckResponse
    blocks_confirmation: bool = False
    document_version: int | None = None


class FieldCorrectionRequest(BaseModel):
    key: str
    value: object | None = None
    clear: bool = False


class CorrectGuestExtractionRequest(BaseModel):
    corrections: list[FieldCorrectionRequest] = Field(default_factory=list)


def _field_response(field: ExtractedFieldView) -> ExtractedFieldResponse:
    return ExtractedFieldResponse(
        key=field.key,
        value=field.value,
        confidence=field.confidence,
        source_text=field.source_text,
        status=field.status,
        edited_by_user=getattr(field, "edited_by_user", False),
        original_value=getattr(field, "original_value", None),
    )


def _field_from_payload(key: str, payload: object) -> ExtractedFieldResponse:
    if not isinstance(payload, dict):
        return ExtractedFieldResponse(key=key, value=payload, status="MISSING")
    status = str(payload.get("status") or "MISSING").upper()
    conf = payload.get("confidence")
    confidence: float | None
    try:
        confidence = float(conf) if conf is not None and conf != "" else None
        if confidence is not None and (confidence < 0 or confidence > 1):
            confidence = None
    except (TypeError, ValueError):
        confidence = None
    if status == "MISSING":
        confidence = None
    return ExtractedFieldResponse(
        key=key,
        value=payload.get("value"),
        confidence=confidence,
        source_text=payload.get("source_text"),
        status=status,
        edited_by_user=bool(payload.get("edited_by_user", False)),
        original_value=payload.get("original_value"),
    )


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}: must be a valid UUID",
        ) from exc


@router.post(
    "/guest/payslip-extract",
    response_model=GuestPayslipExtractionResponse,
    status_code=201,
)
async def extract_guest_payslip(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    use_case: ExtractGuestPayslipUseCase = Depends(get_extract_guest_payslip_use_case),
) -> GuestPayslipExtractionResponse:
    """Upload a payslip, run OCR + AI parser, persist results, return fields.

    Does not run payroll validation / Rule Engine.
    """
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    normalized_language = language.strip().lower()
    if normalized_language not in _ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_language",
                "message": "Invalid language: must be one of he, en, ar, auto",
            },
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_document", "message": "Empty file"},
        )
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "file_too_large",
                "message": f"File exceeds maximum size of {settings.max_upload_size_mb}MB",
            },
        )

    filename = file.filename or "payslip"
    mime_type = file.content_type or "application/octet-stream"
    upload_command = UploadDocumentCommand(
        content=content,
        original_filename=filename,
        mime_type=mime_type,
        document_type=DocumentType.PAYSLIP,
        document_language=normalized_language,
    )
    try:
        _upload_guardrail.validate(upload_command)
    except DocumentUploadRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "upload_rejected", "message": exc.message},
        ) from exc

    try:
        result = await use_case.execute(
            GuestPayslipExtractionCommand(
                content=content,
                original_filename=filename,
                mime_type=mime_type,
                language=normalized_language,
            )
        )
    except OcrError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return GuestPayslipExtractionResponse(
        document_id=str(result.document_id),
        extraction_id=str(result.extraction_id),
        ocr_status=result.ocr_status,
        parser_status=result.parser_status,
        language=result.language,
        ocr_engine=result.ocr_engine,
        parser_model=result.parser_model,
        warnings=result.warnings,
        fields=[_field_response(field) for field in result.fields],
        error_message=result.error_message,
    )


@router.post(
    "/guest/{document_id}/corrections",
    response_model=GuestPayslipExtractionResponse,
    status_code=201,
)
async def correct_guest_extraction(
    document_id: str,
    request: CorrectGuestExtractionRequest,
    use_case: CorrectGuestExtractionUseCase = Depends(get_correct_guest_extraction_use_case),
) -> GuestPayslipExtractionResponse:
    """Persist user review edits as a new extraction version (does not run validation)."""
    parsed_id = _parse_uuid(document_id, "document_id")
    if not request.corrections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "no_corrections", "message": "At least one field correction is required"},
        )
    try:
        result = await use_case.execute(
            document_id=parsed_id,
            corrections=[
                FieldCorrection(key=item.key, value=item.value, clear=item.clear)
                for item in request.corrections
            ],
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {exc.document_id} not found",
        ) from exc

    return GuestPayslipExtractionResponse(
        document_id=str(result.document_id),
        extraction_id=str(result.extraction_id),
        extraction_version=result.extraction_version,
        ocr_status=result.ocr_status,
        parser_status=result.parser_status,
        language=result.language,
        ocr_engine=result.ocr_engine,
        parser_model=result.parser_model,
        fields=[_field_from_payload(item["key"], item) for item in result.fields],
        warnings=result.warnings,
        error_message=None,
    )


def _comparison_response(comparison) -> tuple[IdentityCheckResponse, PeriodCheckResponse]:
    identity = IdentityCheckResponse(
        overall=comparison.identity_check.overall,
        blocks_confirmation=comparison.identity_check.blocks_confirmation,
        fields=[
            ComparisonFieldResponse(**field)
            for field in comparison.identity_check.to_dict()["fields"]
        ],
    )
    period = PeriodCheckResponse(**comparison.period_check.to_dict())
    return identity, period


@router.post(
    "/employee/payslip-extract",
    response_model=EmployeePayslipExtractionResponse,
    status_code=201,
)
async def extract_employee_payslip(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    period_year: int = Form(...),
    period_month: int = Form(...),
    confirm_new_version: bool = Form(False),
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    guest_use_case: ExtractGuestPayslipUseCase = Depends(get_extract_guest_payslip_use_case),
    session: AsyncSession = Depends(get_db_session),
) -> EmployeePayslipExtractionResponse:
    """Authenticated employee payslip extract with server-side identity/period compare."""
    if period_month < 1 or period_month > 12 or period_year < 2000 or period_year > 2100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_period", "message": "Invalid payroll period."},
        )
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    normalized_language = language.strip().lower()
    if normalized_language not in _ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_language",
                "message": "Invalid language: must be one of he, en, ar, auto",
            },
        )
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_document", "message": "Empty file"},
        )
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "file_too_large",
                "message": f"File exceeds maximum size of {settings.max_upload_size_mb}MB",
            },
        )
    filename = file.filename or "payslip"
    mime_type = file.content_type or "application/octet-stream"
    upload_command = UploadDocumentCommand(
        content=content,
        original_filename=filename,
        mime_type=mime_type,
        document_type=DocumentType.PAYSLIP,
        document_language=normalized_language,
    )
    try:
        _upload_guardrail.validate(upload_command)
    except DocumentUploadRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "upload_rejected", "message": exc.message},
        ) from exc

    use_case = ExtractEmployeePayslipUseCase(
        guest_extract=guest_use_case,
        documents=SqlAlchemyDocumentRepository(session),
        extractions=SqlAlchemyDocumentExtractionRepository(session),
        employees=SqlAlchemyEmployeeRepository(session),
        audit_logs=SqlAlchemyAuditLogRepository(session),
    )
    try:
        result = await use_case.execute(
            EmployeePayslipExtractionCommand(
                content=content,
                original_filename=filename,
                mime_type=mime_type,
                language=normalized_language,
                period_year=period_year,
                period_month=period_month,
                employee=bound.employee,
                user_id=bound.principal.user_id,
                national_id_encrypted=bound.national_id_encrypted,
                confirm_new_version=confirm_new_version,
            )
        )
        await session.commit()
    except DuplicatePayslipPeriodError as tip_exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": tip_exc.code,
                "message": str(tip_exc),
                "existing_document_id": str(tip_exc.existing_document_id),
                "existing_version": tip_exc.existing_version,
                "uploaded_at": tip_exc.uploaded_at,
            },
        ) from tip_exc
    except OcrError as tip_exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": tip_exc.code, "message": tip_exc.message},
        ) from tip_exc

    identity, period = _comparison_response(result.comparison)
    return EmployeePayslipExtractionResponse(
        document_id=str(result.extraction.document_id),
        extraction_id=str(result.extraction.extraction_id),
        extraction_version=result.document_version,
        ocr_status=result.extraction.ocr_status,
        parser_status=result.extraction.parser_status,
        language=result.extraction.language,
        ocr_engine=result.extraction.ocr_engine,
        parser_model=result.extraction.parser_model,
        warnings=result.extraction.warnings,
        fields=[_field_response(field) for field in result.extraction.fields],
        error_message=result.extraction.error_message,
        identity_check=identity,
        period_check=period,
        blocks_confirmation=result.comparison.blocks_confirmation,
        document_version=result.document_version,
    )



@router.post(
    "/employee/{document_id}/corrections",
    response_model=EmployeePayslipExtractionResponse,
    status_code=201,
)
async def correct_employee_extraction(
    document_id: str,
    request: CorrectGuestExtractionRequest,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    guest_use_case: CorrectGuestExtractionUseCase = Depends(get_correct_guest_extraction_use_case),
    session: AsyncSession = Depends(get_db_session),
) -> EmployeePayslipExtractionResponse:
    parsed_id = _parse_uuid(document_id, "document_id")
    if not request.corrections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "no_corrections", "message": "At least one field correction is required"},
        )
    use_case = CorrectEmployeeExtractionUseCase(
        guest_correct=guest_use_case,
        documents=SqlAlchemyDocumentRepository(session),
        extractions=SqlAlchemyDocumentExtractionRepository(session),
        audit_logs=SqlAlchemyAuditLogRepository(session),
    )
    try:
        result = await use_case.execute(
            document_id=parsed_id,
            corrections=[
                FieldCorrection(key=item.key, value=item.value, clear=item.clear)
                for item in request.corrections
            ],
            employee=bound.employee,
            user_id=bound.principal.user_id,
            national_id_encrypted=bound.national_id_encrypted,
        )
        await session.commit()
    except DocumentNotFoundError as tip_exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": f"Document {tip_exc.document_id} not found"},
        ) from tip_exc
    except DocumentNotOwnedError as tip_exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "document_not_owned", "message": "Document is not owned by the authenticated employee."},
        ) from tip_exc
    except CorrectionNotAllowedError as tip_exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": tip_exc.code, "message": tip_exc.message},
        ) from tip_exc

    identity, period = _comparison_response(result.comparison)
    return EmployeePayslipExtractionResponse(
        document_id=str(result.correction.document_id),
        extraction_id=str(result.correction.extraction_id),
        extraction_version=result.correction.extraction_version,
        ocr_status=result.correction.ocr_status,
        parser_status=result.correction.parser_status,
        language=result.correction.language,
        ocr_engine=result.correction.ocr_engine,
        parser_model=result.correction.parser_model,
        fields=[_field_from_payload(item["key"], item) for item in result.correction.fields],
        warnings=result.correction.warnings,
        error_message=None,
        identity_check=identity,
        period_check=period,
        blocks_confirmation=result.comparison.blocks_confirmation,
        document_version=result.correction.extraction_version,
    )


class ConfirmEmployeeExtractionRequest(BaseModel):
    acknowledgement: bool = False


@router.post("/employee/{document_id}/confirm")
async def confirm_employee_extraction(
    document_id: str,
    request: ConfirmEmployeeExtractionRequest,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Persist employee confirmation of the latest extraction version."""
    parsed_id = _parse_uuid(document_id, "document_id")
    use_case = ConfirmEmployeeExtractionUseCase(
        documents=SqlAlchemyDocumentRepository(session),
        extractions=SqlAlchemyDocumentExtractionRepository(session),
        audit_logs=SqlAlchemyAuditLogRepository(session),
    )
    try:
        result = await use_case.execute(
            document_id=parsed_id,
            employee=bound.employee,
            user_id=bound.principal.user_id,
            national_id_encrypted=bound.national_id_encrypted,
            acknowledgement=request.acknowledgement,
        )
        await session.commit()
        return result
    except DocumentNotFoundError as tip_exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": f"Document {tip_exc.document_id} not found"},
        ) from tip_exc
    except DocumentNotOwnedError as tip_exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "document_not_owned", "message": "Document is not owned by the authenticated employee."},
        ) from tip_exc
    except ConfirmationBlockedError as tip_exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": tip_exc.code, "message": tip_exc.message},
        ) from tip_exc
