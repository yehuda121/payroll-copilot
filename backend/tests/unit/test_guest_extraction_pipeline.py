"""Guest extraction pipeline: embedded text, OCR routing, parser, ephemeral storage."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import pytest

from payroll_copilot.application.exceptions import PayslipParserSemanticError
from payroll_copilot.application.ports.ocr import OCRResult, OcrPage
from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    PayslipParseResult,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.dynamic_document import new_entry
from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store
from payroll_copilot.application.services.parser_evidence import validate_extracted_field_evidence
from payroll_copilot.application.services.parser_semantic import (
    expand_simplified_field,
    normalize_payslip_parser_payload,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
    _count_usable_fields,
    _fields_from_structured,
)
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextUseCase
from payroll_copilot.application.use_cases.parse_payslip import (
    ParsePayslipFromOcrCommand,
    ParsePayslipFromOcrUseCase,
)
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import coerce_partial_structured_payslip
from payroll_copilot.infrastructure.ocr.pdf_text import (
    assess_embedded_text_quality,
    extract_embedded_pdf_text,
)
from payroll_copilot.infrastructure.ocr.tesseract_provider import TesseractOCRProvider


def _make_text_pdf(text: str, *, pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_blank_pdf(*, pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.parametrize(
    "text",
    [
        "Employee Name Dana Levi\nBase salary 12000\nNet salary 9500",
        "שם עובד: דנה לוי\nשכר ברוטו: 12000\nשכר נטו: 9500",
    ],
)
def test_text_pdf_embedded_quality_usable(text: str) -> None:
    pdf = _make_text_pdf(text)
    pages, _ = extract_embedded_pdf_text(pdf)
    quality = assess_embedded_text_quality(pages)
    assert quality.usable


def test_english_text_pdf_quality_usable() -> None:
    pdf = _make_text_pdf("Employee ID 12345\nGross Salary 15000\nNet Pay 11000")
    pages, _ = extract_embedded_pdf_text(pdf)
    assert assess_embedded_text_quality(pages).usable


def test_short_valid_embedded_text_usable() -> None:
    pdf = _make_text_pdf("Pay period 06/2026\nNet 5000")
    pages, _ = extract_embedded_pdf_text(pdf)
    assert assess_embedded_text_quality(pages).usable


def test_garbled_embedded_text_not_usable() -> None:
    pdf = _make_text_pdf("\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd")
    pages, _ = extract_embedded_pdf_text(pdf)
    assert not assess_embedded_text_quality(pages).usable


@pytest.mark.asyncio
async def test_embedded_pdf_skips_tesseract(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TesseractOCRProvider()
    pdf = _make_text_pdf("Employee Name Dana Levi\nGross Salary 12000\nNet salary 9500")
    rasterize = MagicMock(side_effect=AssertionError("rasterize should not run"))
    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.rasterize_pdf_to_png_pages",
        rasterize,
    )
    result = await provider.extract(
        content=pdf,
        media_type="application/pdf",
        filename="slip.pdf",
        language="auto",
    )
    assert "pdf_text" in result.engine
    rasterize.assert_not_called()


@pytest.mark.asyncio
async def test_blank_pdf_invokes_rasterize(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TesseractOCRProvider()
    pdf = _make_blank_pdf()
    called = {"count": 0}

    def _fake_rasterize(content: bytes, **kwargs: Any) -> list[bytes]:
        called["count"] += 1
        return [b"fakepng"]

    async def _fake_extract_image(*args: Any, **kwargs: Any) -> tuple[OcrPage, str | None]:
        return (
            OcrPage(page=1, language="he", text="OCR text fallback", confidence=0.8, lines=()),
            None,
        )

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.ocr.tesseract_provider.rasterize_pdf_to_png_pages",
        _fake_rasterize,
    )
    monkeypatch.setattr(provider, "_extract_image_sync", _fake_extract_image)
    result = await provider.extract(
        content=pdf,
        media_type="application/pdf",
        filename="blank.pdf",
        language="auto",
    )
    assert called["count"] == 1
    assert result.engine == "tesseract"


def test_semantic_alias_worker_number_maps() -> None:
    payload = {
        "worker_number": {"value": "12345", "source_text": "12345", "confidence": 0.9},
    }
    normalized, warnings = normalize_payslip_parser_payload(payload)
    assert "parser_field_alias_normalized" in warnings
    assert normalized["employee_number"]["value"] == "12345"


def test_missing_evidence_ids_do_not_erase_embedded_text_values() -> None:
    field = ExtractedField(
        value=12000,
        confidence=0.9,
        source_text="12000",
        status=FieldExtractionStatus.FOUND,
        evidence_ids=[],
    )
    validated = validate_extracted_field_evidence(
        field,
        evidence_index={},
        ocr_text="Base salary 12000",
        require_evidence_ids=False,
    )
    assert validated.value == 12000


def test_partial_ai_output_preserves_valid_fields() -> None:
    payload = {
        "employee_name": {"value": "Dana", "source_text": "Dana", "confidence": 0.9},
        "base_salary": {"$ref": "#/$defs/Bad"},
        "employee_id": {"value": None, "source_text": None, "confidence": None},
    }
    payload, _ = normalize_payslip_parser_payload(payload)
    parsed = coerce_partial_structured_payslip(payload)
    assert parsed.employee_name.value == "Dana"
    assert parsed.base_salary.status == FieldExtractionStatus.MISSING


def test_simplified_field_expansion() -> None:
    expanded = expand_simplified_field({"value": "Dana", "source_text": "Dana", "confidence": 0.8})
    assert expanded["status"] == "FOUND"


class _FakeDocs:
    def __init__(self) -> None:
        self.saved = []

    async def save(self, document):  # noqa: ANN001
        self.saved.append(document)
        return document


class _FakeExtractions:
    def __init__(self) -> None:
        self.saved = []

    async def get_latest_for_document(self, document_id):  # noqa: ANN001
        return None

    async def save(self, extraction):  # noqa: ANN001
        self.saved.append(extraction)
        return extraction


class _FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[str] = []

    async def upload(self, key: str, content: bytes, content_type: str) -> None:
        self.uploads.append(key)


class _FakeBootstrap:
    async def ensure_demo_organization(self, organization_id) -> None:  # noqa: ANN001
        return None


class _OkOcr:
    async def extract(self, **kwargs: Any) -> OCRResult:
        return OCRResult(
            pages=(OcrPage(page=1, language="he", text="Base salary 12000", confidence=None),),
            engine="tesseract+pdf_text",
            language_requested="auto",
            language_effective="heb+eng",
            raw_text="Base salary 12000",
            overall_confidence=None,
            fields=(),
            warnings=("pdf_embedded_text_used",),
        )


class _OkDocumentExtractor:
    async def extract(
        self,
        *,
        ocr_text: str,
        language: str = "auto",
        pages_text: list[str] | None = None,
    ):
        _ = ocr_text, language, pages_text
        return (
            [
                new_entry(
                    key="Base salary",
                    value=12000,
                    confidence=0.9,
                    source_text="12000",
                )
            ],
            "fake-doc-model",
            [],
        )


@pytest.mark.asyncio
async def test_guest_ephemeral_not_persisted_to_db() -> None:
    from payroll_copilot.application.services.guest_ephemeral_store import (
        reset_guest_ephemeral_store_for_tests,
    )

    reset_guest_ephemeral_store_for_tests()
    docs = _FakeDocs()
    storage = _FakeStorage()
    use_case = ExtractGuestPayslipUseCase(
        document_repository=docs,
        extraction_repository=_FakeExtractions(),
        object_storage=storage,
        organization_bootstrap=_FakeBootstrap(),
        ocr_use_case=ExtractDocumentTextUseCase(_OkOcr(), timeout_seconds=5),
        document_extractor=_OkDocumentExtractor(),
    )
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"pdf",
            original_filename="slip.pdf",
            mime_type="application/pdf",
            language="auto",
            ephemeral=True,
        )
    )
    assert docs.saved == []
    assert storage.uploads == []
    assert get_guest_ephemeral_store().get(result.document_id) is not None


@pytest.mark.asyncio
async def test_guest_confirm_freezes_without_permanent_write() -> None:
    from payroll_copilot.application.services.guest_ephemeral_store import (
        reset_guest_ephemeral_store_for_tests,
    )

    reset_guest_ephemeral_store_for_tests()
    docs = _FakeDocs()
    extractions = _FakeExtractions()
    storage = _FakeStorage()
    use_case = ExtractGuestPayslipUseCase(
        document_repository=docs,
        extraction_repository=extractions,
        object_storage=storage,
        organization_bootstrap=_FakeBootstrap(),
        ocr_use_case=ExtractDocumentTextUseCase(_OkOcr(), timeout_seconds=5),
        document_extractor=_OkDocumentExtractor(),
    )
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"pdf",
            original_filename="slip.pdf",
            mime_type="application/pdf",
            language="auto",
            ephemeral=True,
        )
    )
    document, extraction = use_case.confirm_ephemeral_session(result.document_id)
    session = get_guest_ephemeral_store().get(result.document_id)
    assert session is not None
    assert session.confirmation_status == "confirmed"
    assert document.id == result.document_id
    assert extraction.confirmation_status == "confirmed"
    assert docs.saved == []
    assert extractions.saved == []
    assert storage.uploads == []
    assert "dynamic_entries" in (extraction.structured_data or {})
    assert extraction.structured_data.get("base_salary", {}).get("value") == 12000


@pytest.mark.asyncio
async def test_parser_retry_failure_raises_not_empty_success() -> None:
    parser = AsyncMock(side_effect=PayslipParserSemanticError("bad", category="x", warning_code="y"))
    use_case = ParsePayslipFromOcrUseCase(parser, timeout_seconds=5, total_budget_seconds=10)
    with pytest.raises(PayslipParserSemanticError):
        await use_case.execute(ParsePayslipFromOcrCommand(raw_text="salary 100", language="en"))
    assert parser.await_count == 2


@pytest.mark.asyncio
async def test_cancellation_before_ocr() -> None:
    use_case = ExtractGuestPayslipUseCase(
        document_repository=_FakeDocs(),
        extraction_repository=_FakeExtractions(),
        object_storage=_FakeStorage(),
        organization_bootstrap=_FakeBootstrap(),
        ocr_use_case=ExtractDocumentTextUseCase(_OkOcr(), timeout_seconds=5),
        document_extractor=_OkDocumentExtractor(),
    )
    from payroll_copilot.application.exceptions import ExtractionCancelledError

    with pytest.raises(ExtractionCancelledError):
        await use_case.execute(
            GuestPayslipExtractionCommand(
                content=b"pdf",
                original_filename="slip.pdf",
                mime_type="application/pdf",
                ephemeral=True,
                cancel_check=lambda: True,
            )
        )
