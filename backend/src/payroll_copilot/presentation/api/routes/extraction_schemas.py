"""API request/response schemas and pure mappers for extraction routes.

Kept separate from the FastAPI route handlers so the oversized extraction router
stays focused on HTTP orchestration. Contracts are unchanged.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from payroll_copilot.application.use_cases.extract_guest_payslip import ExtractedFieldView

ALLOWED_EXTRACTION_LANGUAGES = frozenset({"he", "en", "ar", "auto"})


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


class EmployeeDocumentFormFieldRequest(BaseModel):
    key: str
    value: object | None = None
    source_text: str | None = None
    original_value: object | None = None


class SaveEmployeeDocumentFormRequest(BaseModel):
    fields: list[EmployeeDocumentFormFieldRequest] = Field(default_factory=list)


class EmployeeDocumentFormResponse(BaseModel):
    document_id: str
    extraction_id: str
    extraction_version: int
    document_type: str
    original_filename: str
    uploaded_at: str | None = None
    status: str
    fields: list[ExtractedFieldResponse] = Field(default_factory=list)


class DynamicDocumentEntryRequest(BaseModel):
    """Document-first review row from the guest landing UI (optional on confirm)."""

    id: str = ""
    key: str = ""
    value: object | None = None
    confidence: float | None = None
    page: int | None = None
    source: str = "ocr"
    source_text: str | None = None
    section: str | None = None
    kind: str | None = None
    table_id: str | None = None
    row_index: int | None = None
    column: str | None = None


class ConfirmGuestExtractionRequest(BaseModel):
    """Guest confirm body — matches frontend `confirmGuestExtraction` contract."""

    entries: list[DynamicDocumentEntryRequest] | None = None


class ConfirmGuestExtractionResponse(BaseModel):
    document_id: str
    extraction_id: str
    status: str


class GuestSupportingUploadResponse(BaseModel):
    document_id: str
    document_type: str
    status: str


class ConfirmEmployeeExtractionRequest(BaseModel):
    acknowledgement: bool = False


def field_response(field: ExtractedFieldView) -> ExtractedFieldResponse:
    return ExtractedFieldResponse(
        key=field.key,
        value=field.value,
        confidence=field.confidence,
        source_text=field.source_text,
        status=field.status,
        edited_by_user=getattr(field, "edited_by_user", False),
        original_value=getattr(field, "original_value", None),
    )


def field_from_payload(key: str, payload: object) -> ExtractedFieldResponse:
    if not isinstance(payload, dict):
        return ExtractedFieldResponse(key=key, value=payload, status="MISSING")
    status_value = str(payload.get("status") or "MISSING").upper()
    conf = payload.get("confidence")
    confidence: float | None
    try:
        confidence = float(conf) if conf is not None and conf != "" else None
        if confidence is not None and (confidence < 0 or confidence > 1):
            confidence = None
    except (TypeError, ValueError):
        confidence = None
    if status_value == "MISSING":
        confidence = None
    return ExtractedFieldResponse(
        key=key,
        value=payload.get("value"),
        confidence=confidence,
        source_text=payload.get("source_text"),
        status=status_value,
        edited_by_user=bool(payload.get("edited_by_user", False)),
        original_value=payload.get("original_value"),
    )


def parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}: must be a valid UUID",
        ) from exc


def comparison_response(comparison) -> tuple[IdentityCheckResponse, PeriodCheckResponse]:
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


def employee_document_form_response(result) -> EmployeeDocumentFormResponse:
    fields = []
    for field in result.fields:
        fields.append(
            ExtractedFieldResponse(
                key=str(field.get("key") or ""),
                value=field.get("effective_value"),
                confidence=field.get("confidence"),
                source_text=field.get("source_text"),
                status=str(field.get("extraction_status") or "MISSING"),
                edited_by_user=bool(field.get("edited_by_employee")),
                original_value=field.get("extracted_value"),
            )
        )
    document = result.document
    extraction = result.extraction
    return EmployeeDocumentFormResponse(
        document_id=str(document.id),
        extraction_id=str(extraction.id),
        extraction_version=extraction.extraction_version,
        document_type=document.document_type.value,
        original_filename=document.original_filename,
        uploaded_at=document.created_at.isoformat() if document.created_at else None,
        status=document.status.value,
        fields=fields,
    )
