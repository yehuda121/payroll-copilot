"""Unit tests for guest payslip extraction orchestration (fakes — no OCR/Ollama)."""

from __future__ import annotations

from typing import Any

import pytest

from payroll_copilot.application.exceptions import OcrProviderError, PayslipParserJsonError
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
    _fields_from_structured,
)
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase
from payroll_copilot.application.use_cases.parse_payslip import ParsePayslipFromOcrUseCase
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


class _OkParser:
    async def parse(self, **kwargs: Any) -> PayslipParseResult:
        fields = StructuredPayslipParse(
            employee_name=ExtractedField(
                value="Dana Levi",
                confidence=0.91,
                source_text="Employee: Dana Levi",
                status=FieldExtractionStatus.FOUND,
                evidence_ids=["p1_l1"],
                source_page=1,
                parser_method="layout_llm",
            ),
            base_salary=ExtractedField(
                value=12000,
                confidence=None,
                source_text="Base salary 12000",
                status=FieldExtractionStatus.FOUND,
                evidence_ids=["p1_l1"],
                source_page=1,
                parser_method="layout_llm",
            ),
        )
        return PayslipParseResult(
            model="fake-llm",
            language="en",
            fields=fields,
            raw_model_response="{}",
            warnings=[],
            retry_used=False,
        )


class _FailParser:
    async def parse(self, **kwargs: Any) -> PayslipParseResult:
        raise PayslipParserJsonError("bad json")


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
async def test_orchestration_success_persists_fields() -> None:
    use_case = _use_case(ocr=_OkOcr(), parser=_OkParser())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"fake-png-bytes",
            original_filename="slip.png",
            mime_type="image/png",
            language="en",
        )
    )
    assert result.ocr_status == "completed"
    assert result.parser_status == "completed"
    assert result.ocr_engine == "paddleocr"
    assert result.parser_model == "fake-llm"
    assert any(f.key == "employee_name" and f.value == "Dana Levi" for f in result.fields)
    null_conf = next(f for f in result.fields if f.key == "base_salary")
    assert null_conf.confidence is None


@pytest.mark.asyncio
async def test_orchestration_ocr_failure() -> None:
    use_case = _use_case(ocr=_FailOcr(), parser=_OkParser())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"x",
            original_filename="slip.png",
            mime_type="image/png",
            language="en",
        )
    )
    assert result.ocr_status == "failed"
    assert result.parser_status == "skipped"
    assert result.error_message


@pytest.mark.asyncio
async def test_orchestration_parser_failure_still_persists() -> None:
    use_case = _use_case(ocr=_OkOcr(), parser=_FailParser())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"x",
            original_filename="slip.png",
            mime_type="image/png",
            language="en",
        )
    )
    assert result.ocr_status == "completed"
    assert result.parser_status == "failed"
    assert result.extraction_id is not None


def test_fields_from_structured_missing_and_null_confidence() -> None:
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
        "additional_fields": {},
        "parser_notes": None,
        "language": "en",
    }
    fields, confidences = _fields_from_structured(structured)
    missing = next(f for f in fields if f.key == "employee_name")
    assert missing.status == "MISSING"
    assert "employee_name" not in confidences
    found = next(f for f in fields if f.key == "base_salary")
    assert found.confidence is None
