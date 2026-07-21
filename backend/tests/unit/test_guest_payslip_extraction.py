"""Unit tests for shared Document Model payslip extraction (fakes — no OCR/LLM)."""

from __future__ import annotations

from typing import Any

import pytest

from payroll_copilot.application.exceptions import OcrProviderError, PayslipParserJsonError
from payroll_copilot.application.ports.ocr import OCRResult, OcrPage
from payroll_copilot.application.services.dynamic_document import DynamicDocumentEntry, new_entry
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
    _fields_from_structured,
)
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase
from payroll_copilot.domain.entities import Document, DocumentExtraction


class _FakeStorage:
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        return key


class _FakeBootstrap:
    async def ensure_demo_organization(self, organization_id) -> None:  # noqa: ANN001
        return None


class _FakeDocs:
    def __init__(self) -> None:
        self.saved: list[Document] = []

    async def get_by_id(self, document_id):  # noqa: ANN001
        return next((d for d in self.saved if d.id == document_id), None)

    async def save(self, document: Document) -> Document:
        self.saved = [d for d in self.saved if d.id != document.id]
        self.saved.append(document)
        return document


class _FakeExtractions:
    def __init__(self) -> None:
        self.saved: list[DocumentExtraction] = []

    async def get_by_id(self, extraction_id):  # noqa: ANN001
        return next((e for e in self.saved if e.id == extraction_id), None)

    async def get_latest_for_document(self, document_id):  # noqa: ANN001
        matches = [e for e in self.saved if e.document_id == document_id]
        return matches[-1] if matches else None

    async def save(self, extraction: DocumentExtraction) -> DocumentExtraction:
        self.saved.append(extraction)
        return extraction


class _OkOcr:
    async def extract(self, **kwargs: Any) -> OCRResult:
        return OCRResult(
            pages=(
                OcrPage(
                    page=1,
                    language="en",
                    text="Employee: Dana Levi\nBase salary 12000",
                    confidence=0.9,
                    lines=(),
                ),
            ),
            engine="paddleocr",
            language_requested="en",
            language_effective="en",
            raw_text="Employee: Dana Levi\nBase salary 12000",
            overall_confidence=0.9,
            fields=(),
            warnings=(),
        )


class _FailOcr:
    async def extract(self, **kwargs: Any) -> OCRResult:
        raise OcrProviderError("OCR broke")


class _OkDocumentExtractor:
    async def extract(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
    ) -> tuple[list[DynamicDocumentEntry], str, list[str]]:
        _ = ocr_text, language, pages_text
        return (
            [
                new_entry(
                    key="Employee name",
                    value="Dana Levi",
                    confidence=0.91,
                    source_text="Employee: Dana Levi",
                ),
                new_entry(
                    key="Base salary",
                    value=12000,
                    confidence=None,
                    source_text="Base salary 12000",
                ),
            ],
            "fake-doc-model",
            [],
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
        return ([], "fake-doc-model", [])


class _FailDocumentExtractor:
    async def extract(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
    ) -> tuple[list[DynamicDocumentEntry], str, list[str]]:
        _ = ocr_text, language, pages_text
        raise PayslipParserJsonError("bad json")


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
async def test_orchestration_success_persists_document_model() -> None:
    use_case = _use_case(ocr=_OkOcr(), extractor=_OkDocumentExtractor())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"fake-png-bytes",
            original_filename="slip.png",
            mime_type="image/png",
            language="en",
            ephemeral=False,
        )
    )
    assert result.ocr_status == "completed"
    assert result.parser_status == "completed"
    assert result.ocr_engine == "paddleocr"
    assert result.parser_model == "fake-doc-model"
    assert result.entries is not None
    assert any(e.key == "Employee name" and e.value == "Dana Levi" for e in result.entries)
    assert any(e.key == "Base salary" for e in result.entries)
    # Durable path projects canonical fields for matching/validation.
    assert any(f.key == "employee_name" and f.value == "Dana Levi" for f in result.fields)
    saved = use_case._extractions.saved[-1]  # noqa: SLF001
    assert "dynamic_entries" in (saved.structured_data or {})
    assert len(saved.structured_data["dynamic_entries"]) >= 2


@pytest.mark.asyncio
async def test_orchestration_ocr_failure() -> None:
    use_case = _use_case(ocr=_FailOcr(), extractor=_OkDocumentExtractor())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"x",
            original_filename="slip.png",
            mime_type="image/png",
            language="en",
            ephemeral=False,
        )
    )
    assert result.ocr_status == "failed"
    assert result.parser_status == "skipped"
    assert result.error_message


@pytest.mark.asyncio
async def test_orchestration_extractor_failure_still_persists() -> None:
    use_case = _use_case(ocr=_OkOcr(), extractor=_FailDocumentExtractor())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"x",
            original_filename="slip.png",
            mime_type="image/png",
            language="en",
            ephemeral=False,
        )
    )
    assert result.ocr_status == "completed"
    assert result.parser_status == "failed"
    assert result.extraction_id is not None


@pytest.mark.asyncio
async def test_empty_document_model_is_failed() -> None:
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
    assert result.parser_status == "failed"
    assert "dynamic_extractor_no_usable_entries" in result.warnings


def test_fields_from_structured_skips_dynamic_entries() -> None:
    structured = {
        "employee_name": {
            "value": None,
            "confidence": 0.9,
            "source_text": None,
            "status": "MISSING",
        },
        "base_salary": {
            "value": 100,
            "confidence": None,
            "source_text": "100",
            "status": "FOUND",
        },
        "dynamic_entries": [{"id": "1", "key": "x", "value": 1}],
        "additional_fields": {},
        "parser_notes": None,
        "language": "en",
    }
    fields, confidences = _fields_from_structured(structured)
    assert all(f.key != "dynamic_entries" for f in fields)
    missing = next(f for f in fields if f.key == "employee_name")
    assert missing.status == "MISSING"
    assert "employee_name" not in confidences
    found = next(f for f in fields if f.key == "base_salary")
    assert found.confidence is None
