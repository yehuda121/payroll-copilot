"""Guest extraction must not present empty Document Model as a successful review."""

from __future__ import annotations

from typing import Any

import pytest

from payroll_copilot.application.ports.ocr import OCRResult, OcrPage
from payroll_copilot.application.services.dynamic_document import DynamicDocumentEntry
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
    _count_usable_fields,
    _fields_from_structured,
)
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase
from payroll_copilot.domain.entities import Document, DocumentExtraction


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


class _EmptyDocumentExtractor:
    async def extract(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
    ) -> tuple[list[DynamicDocumentEntry], str, list[str]]:
        _ = ocr_text, language, pages_text
        return ([], "fake", [])


def _use_case(*, ocr, extractor) -> ExtractGuestPayslipUseCase:  # noqa: ANN001
    return ExtractGuestPayslipUseCase(
        document_repository=_FakeDocs(),
        extraction_repository=_FakeExtractions(),
        object_storage=_FakeStorage(),
        organization_bootstrap=_FakeBootstrap(),
        ocr_use_case=ExtractDocumentTextUseCase(ocr, timeout_seconds=5),
        document_extractor=extractor,
    )


@pytest.mark.asyncio
async def test_all_empty_document_model_is_failed_not_reviewable() -> None:
    use_case = _use_case(ocr=_OkOcr(), extractor=_EmptyDocumentExtractor())
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
    assert "dynamic_extractor_no_usable_entries" in result.warnings
    assert _count_usable_fields(result.fields) == 0


def test_count_usable_fields_ignores_missing() -> None:
    structured = {
        "employee_name": {"value": "Dana", "status": "FOUND", "confidence": 0.9},
        "base_salary": {"value": None, "status": "MISSING", "confidence": None},
    }
    fields, _ = _fields_from_structured(structured)
    assert _count_usable_fields(fields) == 1
