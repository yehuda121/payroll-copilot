"""Single source of truth: PDF bytes → typed deterministic extraction result."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.company_payslip_extraction.adapter import (
    DEFAULT_COMPANY_KEY,
    extract_payslip_document,
)
from payroll_copilot.application.services.deterministic_pdf.parsers.contract import (
    parse_contract_text,
)
from payroll_copilot.application.services.deterministic_pdf.parsers.id_appendix import (
    parse_id_appendix_text,
)
from payroll_copilot.application.services.deterministic_pdf.parsers.national_id import (
    parse_national_id_text,
)
from payroll_copilot.application.services.deterministic_pdf.pdf_text_extractor import (
    extract_pdf_text_layer,
)
from payroll_copilot.application.services.deterministic_pdf.types import (
    DeterministicExtractionErrorCode,
    DeterministicExtractionResult,
    DeterministicExtractionStatus,
    EXTRACTOR_VERSION,
    ENGINE_NAME,
    NormalizedExtractedField,
)
from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    new_entry,
)
from payroll_copilot.application.services.employee_document_form_schemas import (
    empty_fixed_structured,
    fixed_keys_for,
)
from payroll_copilot.domain.enums import DocumentType

_SUPPORTED = frozenset(
    {
        DocumentType.PAYSLIP.value,
        DocumentType.NATIONAL_ID.value,
        DocumentType.ID_APPENDIX.value,
        DocumentType.CONTRACT.value,
        DocumentType.BULK_PAYSLIP_PDF.value,
    }
)

_PAYSLIP_TYPES = frozenset(
    {
        DocumentType.PAYSLIP.value,
        DocumentType.BULK_PAYSLIP_PDF.value,
    }
)


def _normalize_document_type(document_type: DocumentType | str) -> str:
    if isinstance(document_type, DocumentType):
        return document_type.value
    return str(document_type).strip().lower()


def _parse_non_payslip_fields(
    document_type: str,
    raw_text: str,
    page_texts: tuple[str, ...],
) -> list[NormalizedExtractedField]:
    if document_type == DocumentType.NATIONAL_ID.value:
        return parse_national_id_text(raw_text, page_texts=page_texts)
    if document_type == DocumentType.ID_APPENDIX.value:
        return parse_id_appendix_text(raw_text, page_texts=page_texts)
    if document_type == DocumentType.CONTRACT.value:
        return parse_contract_text(raw_text, page_texts=page_texts)
    return []


def fields_to_dynamic_entries(
    fields: list[NormalizedExtractedField] | tuple[NormalizedExtractedField, ...],
) -> list[DynamicDocumentEntry]:
    entries: list[DynamicDocumentEntry] = []
    for item in fields:
        entries.append(
            new_entry(
                key=item.key,
                value=item.value,
                confidence=item.confidence,
                page=item.page,
                source="deterministic_pdf",
                source_text=item.source_text,
                kind="canonical",
            )
        )
    return entries


def fields_to_fixed_structured(
    document_type: DocumentType | str,
    fields: list[NormalizedExtractedField] | tuple[NormalizedExtractedField, ...],
) -> dict[str, Any]:
    """Map normalized fields into the fixed Digital Form structured_data shape."""
    structured = empty_fixed_structured(document_type)
    keys = fixed_keys_for(document_type)
    if keys is None:
        return structured
    additional = structured.setdefault("additional_fields", {})
    by_key = {item.key: item for item in fields}
    for key in keys:
        item = by_key.get(key)
        if item is None or item.value in (None, ""):
            continue
        additional[key] = {
            "value": item.value,
            "confidence": item.confidence,
            "source_text": item.source_text,
            "status": "FOUND",
            "edited_by_user": False,
            "original_value": item.value,
        }
    return structured


def extract_document_from_pdf(
    content: bytes,
    *,
    document_type: DocumentType | str,
    filename: str | None = None,
    mime_type: str | None = None,
    company_key: str = DEFAULT_COMPANY_KEY,
) -> DeterministicExtractionResult:
    """Global deterministic PDF extraction entrypoint (no OpenAI / LLM / OCR / agents).

    Payslips use the company-aware pdfplumber extractor. Other document types keep
    the shared PyMuPDF text-layer + type-specific parsers.
    """
    dtype = _normalize_document_type(document_type)
    if dtype not in _SUPPORTED:
        return DeterministicExtractionResult(
            status=DeterministicExtractionStatus.REJECTED,
            document_type=dtype,
            page_count=0,
            page_texts=(),
            raw_text="",
            fields=(),
            warnings=(),
            error_code=DeterministicExtractionErrorCode.UNSUPPORTED_DOCUMENT_TYPE.value,
            error_message=f"Unsupported document type for deterministic PDF extraction: {dtype}",
            structured={},
        )

    # Shared PDF gate (not-pdf / encrypted / empty / malformed) for all types.
    text_result = extract_pdf_text_layer(
        content, filename=filename, mime_type=mime_type
    )
    if not text_result.ok:
        status = (
            DeterministicExtractionStatus.OCR_REQUIRED
            if text_result.error_code == DeterministicExtractionErrorCode.OCR_REQUIRED.value
            else DeterministicExtractionStatus.REJECTED
            if text_result.error_code
            in {
                DeterministicExtractionErrorCode.NOT_PDF.value,
                DeterministicExtractionErrorCode.ENCRYPTED_PDF.value,
                DeterministicExtractionErrorCode.EMPTY_PDF.value,
                DeterministicExtractionErrorCode.MALFORMED_PDF.value,
            }
            else DeterministicExtractionStatus.FAILED
        )
        warnings: list[str] = []
        if text_result.quality_reason:
            warnings.append(f"text_quality:{text_result.quality_reason}")
        return DeterministicExtractionResult(
            status=status,
            document_type=dtype,
            page_count=text_result.page_count,
            page_texts=text_result.page_texts,
            raw_text=text_result.raw_text,
            fields=(),
            warnings=tuple(warnings),
            error_code=text_result.error_code,
            error_message=text_result.error_message,
            structured={},
        )

    if dtype in _PAYSLIP_TYPES:
        result = extract_payslip_document(
            content,
            company_key=company_key,
            document_type=dtype,
            filename=filename,
            mime_type=mime_type,
        )
        if not result.page_texts and text_result.page_texts:
            return DeterministicExtractionResult(
                status=result.status,
                document_type=result.document_type,
                page_count=text_result.page_count or result.page_count,
                page_texts=text_result.page_texts,
                raw_text=result.raw_text or text_result.raw_text,
                fields=result.fields,
                warnings=result.warnings,
                error_code=result.error_code,
                error_message=result.error_message,
                extractor_version=result.extractor_version,
                engine=result.engine,
                structured=result.structured,
            )
        return result

    fields = _parse_non_payslip_fields(dtype, text_result.raw_text, text_result.page_texts)
    if not fields:
        return DeterministicExtractionResult(
            status=DeterministicExtractionStatus.FAILED,
            document_type=dtype,
            page_count=text_result.page_count,
            page_texts=text_result.page_texts,
            raw_text=text_result.raw_text,
            fields=(),
            warnings=("no_fields_matched",),
            error_code=DeterministicExtractionErrorCode.NO_USABLE_FIELDS.value,
            error_message="No usable fields could be extracted from the PDF text layer.",
            structured={
                "extractor_meta": {
                    "extractor_version": EXTRACTOR_VERSION,
                    "engine": ENGINE_NAME,
                }
            },
        )

    structured: dict[str, Any]
    if fixed_keys_for(dtype) is not None:
        structured = fields_to_fixed_structured(dtype, fields)
    else:
        entries = fields_to_dynamic_entries(fields)
        structured = {
            "dynamic_entries": [entry.to_dict() for entry in entries],
        }
    structured["extractor_meta"] = {
        "extractor_version": EXTRACTOR_VERSION,
        "engine": ENGINE_NAME,
        "field_count": len(fields),
    }

    return DeterministicExtractionResult(
        status=DeterministicExtractionStatus.COMPLETED,
        document_type=dtype,
        page_count=text_result.page_count,
        page_texts=text_result.page_texts,
        raw_text=text_result.raw_text,
        fields=tuple(fields),
        warnings=(),
        error_code=None,
        error_message=None,
        structured=structured,
    )


class DeterministicPdfDocumentExtractor:
    """Injectable facade used by upload / batch / workspace / API callers."""

    def extract(
        self,
        content: bytes,
        *,
        document_type: DocumentType | str,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> DeterministicExtractionResult:
        return extract_document_from_pdf(
            content,
            document_type=document_type,
            filename=filename,
            mime_type=mime_type,
        )
