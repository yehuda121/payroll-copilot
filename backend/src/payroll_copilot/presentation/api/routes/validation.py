"""Validation routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.exceptions import DocumentNotFoundError
from payroll_copilot.application.use_cases.persisted_validation import (
    GetValidationRunUseCase,
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.validation.guest_extraction_context_builder import (
    ExtractionRequiredError,
)
from payroll_copilot.infrastructure.ai.agents.validation_report_store import cache_validation_report
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.i18n import finding_explanation, finding_message, resolve_locale
from payroll_copilot.presentation.api.dependencies import (
    get_run_persisted_validation_use_case,
    get_validation_run_use_case,
)

router = APIRouter()


class ValidationRunRequest(BaseModel):
    document_id: str
    employee_id: str | None = None
    include_historical: bool = True
    include_contract_rag: bool = True
    supporting_document_ids: list[str] = Field(default_factory=list)
    locale: str | None = Field(default=None, pattern="^(he|en|ar)$")


class ValidationScopeItemResponse(BaseModel):
    key: str
    label: str
    status: str
    reason: str | None = None


class UploadedDocumentResponse(BaseModel):
    document_type: str
    document_id: str
    uploaded: bool
    original_filename: str | None = None


class FindingResponse(BaseModel):
    id: str
    code: str
    rule_id: str
    severity: str
    message_key: str
    message: str
    explanation: str
    expected_value: str | None
    actual_value: str | None
    confidence: float
    legal_reference: str | None = None


class ValidationRunResponse(BaseModel):
    id: str
    document_id: str
    status: str
    locale: str
    overall_result: str | None = None
    overall_confidence: float | None = None
    rules_evaluated: int = 0
    rules_failed: int = 0
    checks_passed_count: int = 0
    validation_confidence: float | None = None
    confidence_explanation: str | None = None
    validation_scope: list[ValidationScopeItemResponse] = Field(default_factory=list)
    uploaded_documents: list[UploadedDocumentResponse] = Field(default_factory=list)
    extraction_connected: bool = False
    findings: list[FindingResponse] = Field(default_factory=list)


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}: must be a valid UUID",
        ) from exc


def _to_response(record: ValidationRunRecord, *, locale: str) -> ValidationRunResponse:
    enrichment = record.enrichment
    validation_scope: list[ValidationScopeItemResponse] = []
    uploaded_documents: list[UploadedDocumentResponse] = []
    validation_confidence: float | None = None
    confidence_explanation: str | None = None
    checks_passed_count = max(record.rules_evaluated - record.rules_failed, 0)
    extraction_connected = False

    if enrichment is not None:
        validation_scope = [
            ValidationScopeItemResponse(
                key=item.key,
                label=item.label,
                status=item.status,
                reason=item.reason,
            )
            for item in enrichment.validation_scope
        ]
        uploaded_documents = [
            UploadedDocumentResponse(
                document_type=item.document_type,
                document_id=item.document_id,
                uploaded=item.uploaded,
                original_filename=item.original_filename,
            )
            for item in enrichment.uploaded_documents
        ]
        validation_confidence = float(enrichment.validation_confidence)
        confidence_explanation = enrichment.confidence_explanation
        checks_passed_count = enrichment.checks_passed_count
        extraction_connected = enrichment.extraction_connected

    response = ValidationRunResponse(
        id=str(record.id),
        document_id=str(record.document_id),
        status=record.status.value,
        locale=locale,
        overall_result=record.overall_result.value if record.overall_result else None,
        overall_confidence=float(record.overall_confidence) if record.overall_confidence else None,
        rules_evaluated=record.rules_evaluated,
        rules_failed=record.rules_failed,
        checks_passed_count=checks_passed_count,
        validation_confidence=validation_confidence,
        confidence_explanation=confidence_explanation,
        validation_scope=validation_scope,
        uploaded_documents=uploaded_documents,
        extraction_connected=extraction_connected,
        findings=[
            FindingResponse(
                id=str(finding.id),
                code=finding.message_key,
                rule_id=finding.rule_id,
                severity=finding.severity.value,
                message_key=finding.message_key,
                message=finding_message(finding.message_key, locale),
                explanation=finding_explanation(finding.message_key, locale),
                expected_value=finding.expected_value,
                actual_value=finding.actual_value,
                confidence=float(finding.confidence),
                legal_reference=finding.legal_reference,
            )
            for finding in record.findings
        ],
    )

    cache_validation_report(
        response.id,
        {
            "status": response.status,
            "overall_result": response.overall_result,
            "findings": [finding.model_dump() for finding in response.findings],
        },
    )
    return response


@router.post("/run", response_model=ValidationRunResponse, status_code=202)
async def run_validation(
    request: ValidationRunRequest,
    use_case: RunPersistedValidationUseCase = Depends(get_run_persisted_validation_use_case),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> ValidationRunResponse:
    """Trigger deterministic validation for a payslip document."""
    settings = get_settings()
    locale = resolve_locale(
        explicit=request.locale,
        accept_language=accept_language,
        default=settings.default_locale,
    )
    document_id = _parse_uuid(request.document_id, "document_id")
    employee_id = (
        _parse_uuid(request.employee_id, "employee_id") if request.employee_id is not None else None
    )
    supporting_document_ids = tuple(
        _parse_uuid(value, "supporting_document_id") for value in request.supporting_document_ids
    )

    try:
        record = await use_case.execute(
            RunPersistedValidationCommand(
                document_id=document_id,
                employee_id=employee_id,
                include_historical=request.include_historical,
                include_contract_rag=request.include_contract_rag,
                supporting_document_ids=supporting_document_ids,
                locale=locale,
            )
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {exc.document_id} not found",
        ) from exc
    except ExtractionRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "extraction_required", "message": exc.message},
        ) from exc
    return _to_response(record, locale=locale)


@router.get("/runs/{validation_run_id}", response_model=ValidationRunResponse)
async def get_validation_run(
    validation_run_id: str,
    use_case: GetValidationRunUseCase = Depends(get_validation_run_use_case),
    locale: str | None = None,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> ValidationRunResponse:
    settings = get_settings()
    resolved = resolve_locale(
        explicit=locale,
        accept_language=accept_language,
        default=settings.default_locale,
    )
    run_id = _parse_uuid(validation_run_id, "validation_run_id")
    record = await use_case.execute(run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Validation run {validation_run_id} not found",
        )
    return _to_response(record, locale=resolved)
