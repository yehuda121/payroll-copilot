"""Guest payslip extraction orchestration API (OCR + parser + persistence)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_audit_log_repository,
    get_document_extraction_repository,
    get_document_repository,
    get_employee_repository,
    get_validation_finding_repository,
    get_validation_run_repository,
    get_workspace_bootstrap,
)

from payroll_copilot.application.exceptions import (
    ConfirmationBlockedError,
    CorrectionNotAllowedError,
    DocumentNotFoundError,
    DocumentNotOwnedError,
    DocumentUploadRejectedError,
    DuplicatePayslipPeriodError,
    OcrError,
    PayslipParserError,
)
from payroll_copilot.application.use_cases.confirm_employee_extraction import (
    ConfirmEmployeeExtractionUseCase,
)
from payroll_copilot.application.services.document_upload_guardrail import (
    DocumentUploadGuardrailService,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    is_employee_visible_document,
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
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
)
from payroll_copilot.application.use_cases.employee_document_workspace import (
    EmployeeDocumentWorkspaceUseCase,
    ExtractEmployeeDocumentCommand,
)
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.presentation.api.dependencies import (
    get_correct_guest_extraction_use_case,
    get_employee_document_workspace_use_case,
    get_extract_guest_payslip_use_case,
)
from payroll_copilot.presentation.api.rate_limit_deps import (
    limit_accountant_upload,
    limit_employee_upload,
    limit_guest_extract_by_guest,
    limit_guest_extract_by_ip,
    limit_guest_upload_by_ip,
)
from payroll_copilot.presentation.api.upload_limits import read_upload_with_size_limit
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    BoundEmployeeContext,
    GuestPrincipal,
    bind_accountant_selected_employee,
    require_accountant,
    require_bound_employee,
    require_guest,
)

from payroll_copilot.presentation.api.routes.extraction_schemas import (
    ALLOWED_EXTRACTION_LANGUAGES,
    ConfirmEmployeeExtractionRequest,
    ConfirmGuestExtractionRequest,
    ConfirmGuestExtractionResponse,
    CorrectGuestExtractionRequest,
    EmployeeDocumentFormResponse,
    EmployeePayslipExtractionResponse,
    FieldCorrectionRequest,
    GuestPayslipExtractionResponse,
    GuestSupportingUploadResponse,
    SaveEmployeeDocumentFormRequest,
    comparison_response,
    employee_document_form_response,
    field_from_payload,
    field_response,
    parse_uuid,
)


router = APIRouter()
_upload_guardrail = DocumentUploadGuardrailService(get_settings())


async def _require_employee_visible_document(
    document_id: UUID,
    bound: BoundEmployeeContext,
) -> None:
    """Hide accountant-review drafts from employee principals, even by UUID."""
    if bound.principal.role != "employee":
        return
    document = await get_document_repository().get_by_id(document_id)
    if document is None or not is_employee_visible_document(document):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": "Document not found"},
        )

@router.post(
    "/guest/payslip-extract",
    response_model=GuestPayslipExtractionResponse,
    status_code=201,
)
async def extract_guest_payslip(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    _: None = Depends(limit_guest_extract_by_ip),
    __: None = Depends(limit_guest_extract_by_guest),
    ___: GuestPrincipal = Depends(require_guest),
    use_case: ExtractGuestPayslipUseCase = Depends(get_extract_guest_payslip_use_case),
) -> GuestPayslipExtractionResponse:
    """Upload a payslip, run OCR + AI parser, persist results, return fields.

    Does not run payroll validation / Rule Engine.
    """
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    normalized_language = language.strip().lower()
    if normalized_language not in ALLOWED_EXTRACTION_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_language",
                "message": "Invalid language: must be one of he, en, ar, auto",
            },
        )

    content = await read_upload_with_size_limit(file, max_size)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_document", "message": "Empty file"},
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
        fields=[field_response(field) for field in result.fields],
        error_message=result.error_message,
    )



@router.post(
    "/guest/supporting-upload",
    response_model=GuestSupportingUploadResponse,
    status_code=201,
)
async def upload_guest_supporting(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    payslip_document_id: str | None = Form(None),
    _: None = Depends(limit_guest_upload_by_ip),
    __: None = Depends(limit_guest_extract_by_guest),
    ___: GuestPrincipal = Depends(require_guest),
) -> GuestSupportingUploadResponse:
    """Store a guest supporting document (national ID / contract) ephemerally.

    Matches frontend ``uploadGuestSupporting``. Bytes stay in the process-local
    ephemeral store (same pipeline as payslip guest sessions) — no permanent write.
    """
    normalized_type = document_type.strip().lower()
    allowed = {
        DocumentType.NATIONAL_ID.value: DocumentType.NATIONAL_ID,
        DocumentType.CONTRACT.value: DocumentType.CONTRACT,
    }
    if normalized_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_document_type",
                "message": "document_type must be national_id or contract",
            },
        )

    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await read_upload_with_size_limit(file, max_size)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_document", "message": "Empty file"},
        )

    filename = file.filename or "supporting"
    mime_type = file.content_type or "application/octet-stream"
    upload_command = UploadDocumentCommand(
        content=content,
        original_filename=filename,
        mime_type=mime_type,
        document_type=allowed[normalized_type],
        document_language="auto",
    )
    try:
        _upload_guardrail.validate(upload_command)
    except DocumentUploadRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "upload_rejected", "message": exc.message},
        ) from exc

    payslip_id: UUID | None = None
    if payslip_document_id:
        payslip_id = parse_uuid(payslip_document_id, "payslip_document_id")

    from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store

    store = get_guest_ephemeral_store(ttl_hours=settings.guest_ephemeral_ttl_hours)
    if payslip_id is not None and store.get(payslip_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "payslip_session_not_found",
                "message": "Payslip guest session not found for payslip_document_id",
            },
        )

    doc = store.save_supporting(
        document_type=allowed[normalized_type],
        content=content,
        original_filename=filename,
        mime_type=mime_type,
        payslip_document_id=payslip_id,
    )
    return GuestSupportingUploadResponse(
        document_id=str(doc.document_id),
        document_type=normalized_type,
        status="uploaded",
    )


@router.post(
    "/guest/{document_id}/confirm",
    response_model=ConfirmGuestExtractionResponse,
)
async def confirm_guest_extraction(
    document_id: str,
    request: ConfirmGuestExtractionRequest | None = None,
    _: GuestPrincipal = Depends(require_guest),
    use_case: ExtractGuestPayslipUseCase = Depends(get_extract_guest_payslip_use_case),
) -> ConfirmGuestExtractionResponse:
    """Confirm reviewed guest extraction fields for ephemeral validation.

    Matches frontend ``confirmGuestExtraction``: optional ``entries`` snapshot freezes
    the Document Model, maps to canonical structured_data, and sets confirmation_status.
    Does not write permanent S3/DB (same rules as ``confirm_ephemeral_session``).
    """
    parsed_id = parse_uuid(document_id, "document_id")
    body = request or ConfirmGuestExtractionRequest()
    entries_payload: list[dict] | None = None
    if body.entries is not None:
        entries_payload = [entry.model_dump() for entry in body.entries]

    try:
        _document, extraction = use_case.confirm_ephemeral_session(
            parsed_id,
            dynamic_entries=entries_payload,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "document_not_found",
                "message": f"Guest extraction session not found for document {parsed_id}",
            },
        ) from exc

    return ConfirmGuestExtractionResponse(
        document_id=str(parsed_id),
        extraction_id=str(extraction.id),
        status=extraction.confirmation_status or "confirmed",
    )


@router.post(
    "/guest/{document_id}/corrections",
    response_model=GuestPayslipExtractionResponse,
    status_code=201,
)
async def correct_guest_extraction(
    document_id: str,
    request: CorrectGuestExtractionRequest,
    _: GuestPrincipal = Depends(require_guest),
    use_case: CorrectGuestExtractionUseCase = Depends(get_correct_guest_extraction_use_case),
) -> GuestPayslipExtractionResponse:
    """Persist user review edits as a new extraction version (does not run validation)."""
    parsed_id = parse_uuid(document_id, "document_id")
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
        fields=[field_from_payload(item["key"], item) for item in result.fields],
        warnings=result.warnings,
        error_message=None,
    )


@router.post(
    "/employee/document-extract",
    response_model=EmployeeDocumentFormResponse,
    status_code=201,
)
async def extract_employee_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    language: str = Form("auto"),
    _: None = Depends(limit_employee_upload),
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    use_case: EmployeeDocumentWorkspaceUseCase = Depends(
        get_employee_document_workspace_use_case
    ),
) -> EmployeeDocumentFormResponse:
    """Extract and atomically activate an Employee Documents digital form."""
    if document_type not in {
        DocumentType.NATIONAL_ID,
        DocumentType.ID_APPENDIX,
        DocumentType.CONTRACT,
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unsupported_document_type",
                "message": "Unsupported document type.",
            },
        )
    normalized_language = language.strip().lower()
    if normalized_language not in ALLOWED_EXTRACTION_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_language",
                "message": "Invalid document language.",
            },
        )
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await read_upload_with_size_limit(file, max_size)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_document", "message": "Empty file"},
        )
    command = UploadDocumentCommand(
        content=content,
        original_filename=file.filename or "document",
        mime_type=file.content_type or "application/octet-stream",
        document_type=document_type,
        document_language=normalized_language,
    )
    try:
        _upload_guardrail.validate(command)
        result = await use_case.extract_and_replace(
            ExtractEmployeeDocumentCommand(
                content=content,
                original_filename=command.original_filename,
                mime_type=command.mime_type,
                language=normalized_language,
                document_type=document_type,
                organization_id=bound.employee.organization_id,
                employee_id=bound.employee.id,
                user_id=bound.principal.user_id,
            )
        )
    except DocumentUploadRejectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "upload_rejected", "message": exc.message},
        ) from exc
    except (OcrError, PayslipParserError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return employee_document_form_response(result)


@router.get(
    "/employee/document/{document_id}",
    response_model=EmployeeDocumentFormResponse,
)
async def get_employee_document_form(
    document_id: str,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    use_case: EmployeeDocumentWorkspaceUseCase = Depends(
        get_employee_document_workspace_use_case
    ),
) -> EmployeeDocumentFormResponse:
    try:
        result = await use_case.get_form(
            document_id=parse_uuid(document_id, "document_id"),
            organization_id=bound.employee.organization_id,
            employee_id=bound.employee.id,
        )
    except (DocumentNotFoundError, DocumentNotOwnedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "document_form_not_found",
                "message": "Digital Form not found.",
            },
        ) from exc
    return employee_document_form_response(result)


@router.put(
    "/employee/document/{document_id}",
    response_model=EmployeeDocumentFormResponse,
)
async def save_employee_document_form(
    document_id: str,
    request: SaveEmployeeDocumentFormRequest,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    use_case: EmployeeDocumentWorkspaceUseCase = Depends(
        get_employee_document_workspace_use_case
    ),
) -> EmployeeDocumentFormResponse:
    try:
        result = await use_case.save_form(
            document_id=parse_uuid(document_id, "document_id"),
            organization_id=bound.employee.organization_id,
            employee_id=bound.employee.id,
            user_id=bound.principal.user_id,
            fields=[field.model_dump() for field in request.fields],
        )
    except (DocumentNotFoundError, DocumentNotOwnedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "document_form_not_found",
                "message": "Digital Form not found.",
            },
        ) from exc
    return employee_document_form_response(result)


@router.put(
    "/employee/document-type/{document_type}",
    response_model=EmployeeDocumentFormResponse,
)
async def save_employee_document_form_by_type(
    document_type: DocumentType,
    request: SaveEmployeeDocumentFormRequest,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    use_case: EmployeeDocumentWorkspaceUseCase = Depends(
        get_employee_document_workspace_use_case
    ),
) -> EmployeeDocumentFormResponse:
    """Save a fixed Digital Form, creating a form-only shell when needed."""
    if document_type not in {
        DocumentType.NATIONAL_ID,
        DocumentType.ID_APPENDIX,
    }:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unsupported_document_type",
                "message": "Manual Digital Forms are only supported for ID documents.",
            },
        )
    try:
        result = await use_case.save_form(
            document_id=None,
            document_type=document_type,
            organization_id=bound.employee.organization_id,
            employee_id=bound.employee.id,
            user_id=bound.principal.user_id,
            fields=[field.model_dump() for field in request.fields],
        )
    except (DocumentNotFoundError, DocumentNotOwnedError) as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "document_form_not_found",
                "message": "Digital Form not found.",
            },
        ) from tip_exc
    return employee_document_form_response(result)


@router.post(
    "/employee/payslip-extract",
    response_model=EmployeePayslipExtractionResponse,
    status_code=201,
)
async def extract_employee_payslip(
    file: UploadFile | None = File(None),
    document_id: str | None = Form(None),
    language: str = Form("auto"),
    period_year: int = Form(...),
    period_month: int = Form(...),
    confirm_new_version: bool = Form(False),
    _: None = Depends(limit_employee_upload),
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    guest_use_case: ExtractGuestPayslipUseCase = Depends(get_extract_guest_payslip_use_case),
) -> EmployeePayslipExtractionResponse:
    """Authenticated employee payslip extract. Provide ``file`` or existing ``document_id``."""
    if period_month < 1 or period_month > 12 or period_year < 2000 or period_year > 2100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_period", "message": "Invalid payroll period."},
        )
    settings = get_settings()
    max_size = settings.max_upload_size_mb * 1024 * 1024
    normalized_language = language.strip().lower()
    if normalized_language not in ALLOWED_EXTRACTION_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_language",
                "message": "Invalid language: must be one of he, en, ar, auto",
            },
        )

    source_document_id: UUID | None = None
    if document_id:
        source_document_id = parse_uuid(document_id, "document_id")
        existing_doc = await get_document_repository().get_by_id(source_document_id)
        if (
            existing_doc is None
            or existing_doc.employee_id != bound.employee.id
            or existing_doc.organization_id != bound.employee.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "document_not_found", "message": "Document not found"},
            )
        await _require_employee_visible_document(source_document_id, bound)
        from payroll_copilot.presentation.api.dependencies import get_object_storage

        try:
            content = await get_object_storage().download(existing_doc.storage_key)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "document_content_missing",
                    "message": "Stored file is unavailable.",
                },
            ) from exc
        filename = existing_doc.original_filename or "payslip"
        mime_type = existing_doc.mime_type or "application/octet-stream"
    else:
        if file is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "file_or_document_required",
                    "message": "Provide a file or document_id.",
                },
            )
        content = await read_upload_with_size_limit(file, max_size)
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "empty_document", "message": "Empty file"},
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
        documents=get_document_repository(),
        extractions=get_document_extraction_repository(),
        employees=get_employee_repository(),
        audit_logs=get_audit_log_repository(),
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
                source_document_id=source_document_id,
            )
        )
    except DuplicatePayslipPeriodError as tip_exc:
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": tip_exc.code, "message": tip_exc.message},
        ) from tip_exc

    identity, period = comparison_response(result.comparison)
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
        fields=[field_response(field) for field in result.extraction.fields],
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
) -> EmployeePayslipExtractionResponse:
    parsed_id = parse_uuid(document_id, "document_id")
    await _require_employee_visible_document(parsed_id, bound)
    if not request.corrections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "no_corrections", "message": "At least one field correction is required"},
        )
    use_case = CorrectEmployeeExtractionUseCase(
        guest_correct=guest_use_case,
        documents=get_document_repository(),
        extractions=get_document_extraction_repository(),
        audit_logs=get_audit_log_repository(),
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
    except DocumentNotFoundError as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": f"Document {tip_exc.document_id} not found"},
        ) from tip_exc
    except DocumentNotOwnedError as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "document_not_owned", "message": "Document is not owned by the authenticated employee."},
        ) from tip_exc
    except CorrectionNotAllowedError as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": tip_exc.code, "message": tip_exc.message},
        ) from tip_exc

    identity, period = comparison_response(result.comparison)
    return EmployeePayslipExtractionResponse(
        document_id=str(result.correction.document_id),
        extraction_id=str(result.correction.extraction_id),
        extraction_version=result.correction.extraction_version,
        ocr_status=result.correction.ocr_status,
        parser_status=result.correction.parser_status,
        language=result.correction.language,
        ocr_engine=result.correction.ocr_engine,
        parser_model=result.correction.parser_model,
        fields=[field_from_payload(item["key"], item) for item in result.correction.fields],
        warnings=result.correction.warnings,
        error_message=None,
        identity_check=identity,
        period_check=period,
        blocks_confirmation=result.comparison.blocks_confirmation,
        document_version=result.correction.extraction_version,
    )


@router.post("/employee/{document_id}/confirm")
async def confirm_employee_extraction(
    document_id: str,
    request: ConfirmEmployeeExtractionRequest,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> dict:
    """Persist employee confirmation of the latest extraction version."""
    parsed_id = parse_uuid(document_id, "document_id")
    await _require_employee_visible_document(parsed_id, bound)
    use_case = ConfirmEmployeeExtractionUseCase(
        documents=get_document_repository(),
        extractions=get_document_extraction_repository(),
        audit_logs=get_audit_log_repository(),
    )
    try:
        result = await use_case.execute(
            document_id=parsed_id,
            employee=bound.employee,
            user_id=bound.principal.user_id,
            national_id_encrypted=bound.national_id_encrypted,
            acknowledgement=request.acknowledgement,
        )
        return result
    except DocumentNotFoundError as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "document_not_found", "message": f"Document {tip_exc.document_id} not found"},
        ) from tip_exc
    except DocumentNotOwnedError as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "document_not_owned", "message": "Document is not owned by the authenticated employee."},
        ) from tip_exc
    except ConfirmationBlockedError as tip_exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": tip_exc.code, "message": tip_exc.message},
        ) from tip_exc


async def _accountant_selected_context(
    employee_number: str,
    principal: AuthPrincipal,
) -> BoundEmployeeContext:
    return await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )


@router.post(
    "/accountant/{employee_number}/document-extract",
    response_model=EmployeeDocumentFormResponse,
    status_code=201,
)
async def accountant_extract_employee_document(
    employee_number: str,
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    language: str = Form("auto"),
    _: None = Depends(limit_accountant_upload),
    principal: AuthPrincipal = Depends(require_accountant),
    use_case: EmployeeDocumentWorkspaceUseCase = Depends(
        get_employee_document_workspace_use_case
    ),
) -> EmployeeDocumentFormResponse:
    return await extract_employee_document(
        file=file,
        document_type=document_type,
        language=language,
        bound=await _accountant_selected_context(employee_number, principal),
        use_case=use_case,
    )


@router.get(
    "/accountant/{employee_number}/document/{document_id}",
    response_model=EmployeeDocumentFormResponse,
)
async def accountant_get_employee_document_form(
    employee_number: str,
    document_id: str,
    principal: AuthPrincipal = Depends(require_accountant),
    use_case: EmployeeDocumentWorkspaceUseCase = Depends(
        get_employee_document_workspace_use_case
    ),
) -> EmployeeDocumentFormResponse:
    return await get_employee_document_form(
        document_id=document_id,
        bound=await _accountant_selected_context(employee_number, principal),
        use_case=use_case,
    )


@router.put(
    "/accountant/{employee_number}/document/{document_id}",
    response_model=EmployeeDocumentFormResponse,
)
async def accountant_save_employee_document_form(
    employee_number: str,
    document_id: str,
    request: SaveEmployeeDocumentFormRequest,
    principal: AuthPrincipal = Depends(require_accountant),
    use_case: EmployeeDocumentWorkspaceUseCase = Depends(
        get_employee_document_workspace_use_case
    ),
) -> EmployeeDocumentFormResponse:
    return await save_employee_document_form(
        document_id=document_id,
        request=request,
        bound=await _accountant_selected_context(employee_number, principal),
        use_case=use_case,
    )


@router.put(
    "/accountant/{employee_number}/document-type/{document_type}",
    response_model=EmployeeDocumentFormResponse,
)
async def accountant_save_employee_document_form_by_type(
    employee_number: str,
    document_type: DocumentType,
    request: SaveEmployeeDocumentFormRequest,
    principal: AuthPrincipal = Depends(require_accountant),
    use_case: EmployeeDocumentWorkspaceUseCase = Depends(
        get_employee_document_workspace_use_case
    ),
) -> EmployeeDocumentFormResponse:
    return await save_employee_document_form_by_type(
        document_type=document_type,
        request=request,
        bound=await _accountant_selected_context(employee_number, principal),
        use_case=use_case,
    )


@router.post(
    "/accountant/{employee_number}/payslip-extract",
    response_model=EmployeePayslipExtractionResponse,
    status_code=201,
)
async def accountant_extract_employee_payslip(
    employee_number: str,
    file: UploadFile | None = File(None),
    document_id: str | None = Form(None),
    language: str = Form("auto"),
    period_year: int = Form(...),
    period_month: int = Form(...),
    confirm_new_version: bool = Form(False),
    _: None = Depends(limit_accountant_upload),
    principal: AuthPrincipal = Depends(require_accountant),
    guest_use_case: ExtractGuestPayslipUseCase = Depends(
        get_extract_guest_payslip_use_case
    ),
) -> EmployeePayslipExtractionResponse:
    return await extract_employee_payslip(
        file=file,
        document_id=document_id,
        language=language,
        period_year=period_year,
        period_month=period_month,
        confirm_new_version=confirm_new_version,
        bound=await _accountant_selected_context(employee_number, principal),
        guest_use_case=guest_use_case,
    )


@router.post(
    "/accountant/{employee_number}/{document_id}/corrections",
    response_model=EmployeePayslipExtractionResponse,
)
async def accountant_correct_employee_extraction(
    employee_number: str,
    document_id: str,
    request: CorrectGuestExtractionRequest,
    principal: AuthPrincipal = Depends(require_accountant),
    guest_use_case: CorrectGuestExtractionUseCase = Depends(
        get_correct_guest_extraction_use_case
    ),
) -> EmployeePayslipExtractionResponse:
    return await correct_employee_extraction(
        document_id=document_id,
        request=request,
        bound=await _accountant_selected_context(employee_number, principal),
        guest_use_case=guest_use_case,
    )


@router.post("/accountant/{employee_number}/{document_id}/confirm")
async def accountant_confirm_employee_extraction(
    employee_number: str,
    document_id: str,
    request: ConfirmEmployeeExtractionRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict:
    return await confirm_employee_extraction(
        document_id=document_id,
        request=request,
        bound=await _accountant_selected_context(employee_number, principal),
    )
