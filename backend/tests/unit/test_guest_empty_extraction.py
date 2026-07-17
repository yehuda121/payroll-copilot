"""Guest extraction must not present all-empty fields as a successful review."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from payroll_copilot.application.exceptions import OcrProviderError
from payroll_copilot.application.ports.ocr import OCRResult, OcrPage
from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    PayslipParseResult,
    StructuredPayslipParse,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
    _count_usable_fields,
    _fields_from_structured,
)
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase
from payroll_copilot.application.use_cases.parse_payslip import ParsePayslipFromOcrUseCase
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType


class _FakeDocs:
    def __init__(self) -> None:
        self.saved: list[Document] = []

    async def save(self, document: Document) -> Document:
        self.saved.append(document)
        return document

    async def get_by_id(self, document_id):  # noqa: ANN001
        return next((d for d in self.saved if d.id == document_id), None)


class _FakeExtractions:
    async def get_latest_for_document(self, document_id):  # noqa: ANN001
        return None

    async def save(self, extraction: DocumentExtraction) -> DocumentExtraction:
        return extraction


class _FakeStorage:
    async def upload(self, key: str, content: bytes, content_type: str) -> None:
        return None


class _FakeBootstrap:
    async def ensure_demo_organization(self, organization_id) -> None:  # noqa: ANN001
        return None


class _OkOcr:
    async def extract(self, **kwargs: Any) -> OCRResult:
        return OCRResult(
            pages=(OcrPage(page=1, language="he", text="Base salary 12000", confidence=0.9),),
            engine="tesseract",
            language_requested="auto",
            language_effective="heb+eng",
            raw_text="Base salary 12000",
            overall_confidence=0.9,
            fields=(),
            warnings=(),
        )


class _EmptyParser:
    async def parse(self, **kwargs: Any) -> PayslipParseResult:
        return PayslipParseResult(
            model="unknown",
            language="auto",
            fields=StructuredPayslipParse(language="auto"),
            raw_model_response=None,
            warnings=["parser_semantic_retry_failed"],
            retry_used=True,
        )


def _use_case(*, ocr, parser) -> ExtractGuestPayslipUseCase:  # noqa: ANN001
    return ExtractGuestPayslipUseCase(
        document_repository=_FakeDocs(),
        extraction_repository=_FakeExtractions(),
        object_storage=_FakeStorage(),
        organization_bootstrap=_FakeBootstrap(),
        ocr_use_case=ExtractDocumentTextUseCase(ocr, timeout_seconds=5),
        parse_use_case=ParsePayslipFromOcrUseCase(parser, timeout_seconds=5),
    )


@pytest.mark.asyncio
async def test_all_empty_parser_result_is_failed_not_reviewable() -> None:
    use_case = _use_case(ocr=_OkOcr(), parser=_EmptyParser())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"fake",
            original_filename="slip.pdf",
            mime_type="application/pdf",
            language="auto",
            ephemeral=False,
        )
    )
    assert result.ocr_status == "completed"
    assert result.parser_status == "failed"
    assert result.error_message
    assert "parser_no_usable_fields" in result.warnings
    assert _count_usable_fields(result.fields) == 0


def test_count_usable_fields_ignores_missing() -> None:
    structured = {
        "employee_name": {"value": "Dana", "status": "FOUND", "confidence": 0.9},
        "base_salary": {"value": None, "status": "MISSING", "confidence": None},
    }
    fields, _ = _fields_from_structured(structured)
    assert _count_usable_fields(fields) == 1
