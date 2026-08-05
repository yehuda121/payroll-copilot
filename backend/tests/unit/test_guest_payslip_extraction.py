"""Unit tests for shared deterministic payslip extraction orchestration."""

from __future__ import annotations

from typing import Any

import fitz
import pytest

from payroll_copilot.application.services.deterministic_pdf import (
    DeterministicExtractionResult,
    DeterministicExtractionStatus,
    EXTRACTOR_VERSION,
    ENGINE_NAME,
    NormalizedExtractedField,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
    _fields_from_structured,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentType


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


class _OkDeterministic:
    def extract(self, content: bytes, *, document_type, filename=None, mime_type=None):  # noqa: ANN001
        _ = content, document_type, filename, mime_type
        fields = (
            NormalizedExtractedField(
                key="employee_name",
                value="Dana Levi",
                confidence=0.91,
                source_text="Employee Name: Dana Levi",
            ),
            NormalizedExtractedField(
                key="base_salary",
                value="12000",
                confidence=0.9,
                source_text="Base Salary: 12000",
            ),
        )
        return DeterministicExtractionResult(
            status=DeterministicExtractionStatus.COMPLETED,
            document_type=DocumentType.PAYSLIP.value,
            page_count=1,
            page_texts=("Employee Name: Dana Levi\nBase Salary: 12000",),
            raw_text="Employee Name: Dana Levi\nBase Salary: 12000",
            fields=fields,
            structured={
                "dynamic_entries": [],
                "extractor_meta": {"extractor_version": EXTRACTOR_VERSION},
            },
        )


class _RejectDeterministic:
    def extract(self, content: bytes, *, document_type, filename=None, mime_type=None):  # noqa: ANN001
        _ = content, document_type, filename, mime_type
        return DeterministicExtractionResult(
            status=DeterministicExtractionStatus.REJECTED,
            document_type=DocumentType.PAYSLIP.value,
            page_count=0,
            page_texts=(),
            raw_text="",
            fields=(),
            error_code="NOT_PDF",
            error_message="Only PDF files are supported for deterministic extraction.",
        )


class _EmptyDeterministic:
    def extract(self, content: bytes, *, document_type, filename=None, mime_type=None):  # noqa: ANN001
        _ = content, document_type, filename, mime_type
        return DeterministicExtractionResult(
            status=DeterministicExtractionStatus.FAILED,
            document_type=DocumentType.PAYSLIP.value,
            page_count=1,
            page_texts=("noise",),
            raw_text="noise",
            fields=(),
            error_code="NO_USABLE_FIELDS",
            error_message="No usable fields",
            structured={"extractor_meta": {"extractor_version": EXTRACTOR_VERSION}},
        )


def _use_case(*, deterministic: Any) -> ExtractGuestPayslipUseCase:
    return ExtractGuestPayslipUseCase(
        document_repository=_FakeDocs(),
        extraction_repository=_FakeExtractions(),
        object_storage=_FakeStorage(),
        organization_bootstrap=_FakeBootstrap(),
        deterministic_extractor=deterministic,
    )


def _tiny_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Employee Name: Dana Levi\nBase Salary: 12000")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.asyncio
async def test_orchestration_success_persists_document_model() -> None:
    use_case = _use_case(deterministic=_OkDeterministic())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=_tiny_pdf(),
            original_filename="slip.pdf",
            mime_type="application/pdf",
            language="en",
            ephemeral=False,
        )
    )
    assert result.ocr_status == "completed"
    assert result.parser_status == "completed"
    assert result.ocr_engine == ENGINE_NAME
    assert result.parser_model == EXTRACTOR_VERSION
    assert result.entries is not None
    assert any(e.key == "employee_name" and e.value == "Dana Levi" for e in result.entries)
    assert any(f.key == "employee_name" and f.value == "Dana Levi" for f in result.fields)
    saved = use_case._extractions.saved[-1]  # noqa: SLF001
    assert "dynamic_entries" in (saved.structured_data or {})


@pytest.mark.asyncio
async def test_orchestration_not_pdf_rejected() -> None:
    use_case = _use_case(deterministic=_RejectDeterministic())
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
async def test_empty_document_model_is_failed() -> None:
    use_case = _use_case(deterministic=_EmptyDeterministic())
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=_tiny_pdf(),
            original_filename="slip.pdf",
            mime_type="application/pdf",
            language="auto",
            ephemeral=False,
        )
    )
    assert result.parser_status == "failed"
    assert "NO_USABLE_FIELDS" in result.warnings


def test_fields_from_structured_prefers_dynamic_entries() -> None:
    """Digital-form SoT: dynamic_entries win over incomplete additional_fields."""
    structured = {
        "employee_name": {
            "value": "Top Level Name",
            "confidence": 0.9,
            "source_text": None,
            "status": "FOUND",
        },
        "pay_period": {
            "value": "2026-06",
            "confidence": 0.9,
            "status": "FOUND",
        },
        "dynamic_entries": [
            {
                "id": "1",
                "key": "employee_name",
                "value": "יהודה שמולביץ",
                "kind": "document_field",
                "source": "company_payslip_pdfplumber",
            },
            {
                "id": "2",
                "key": "pay_period",
                "value": "2026-06",
                "kind": "document_field",
                "source": "company_payslip_pdfplumber",
            },
            {
                "id": "3",
                "key": "national_id",
                "value": "31336678-3",
                "kind": "document_field",
                "source": "company_payslip_pdfplumber",
            },
        ],
        "additional_fields": {
            "national_id": {
                "value": "31336678-3",
                "confidence": 0.9,
                "status": "FOUND",
            },
        },
        "language": "he",
    }
    fields, _ = _fields_from_structured(structured)
    assert all(f.key != "dynamic_entries" for f in fields)
    by_key = {f.key: f.value for f in fields}
    assert by_key["employee_name"] == "יהודה שמולביץ"
    assert by_key["pay_period"] == "2026-06"
    assert by_key["national_id"] == "31336678-3"


def test_fields_from_structured_merges_toplevel_when_no_entries() -> None:
    structured = {
        "employee_name": {
            "value": "Dana",
            "confidence": 0.9,
            "status": "FOUND",
        },
        "pay_period": {
            "value": "2026-06",
            "confidence": 0.8,
            "status": "FOUND",
        },
        "additional_fields": {
            "national_id": {
                "value": "123456782",
                "confidence": 0.9,
                "status": "FOUND",
            },
        },
    }
    fields, confidences = _fields_from_structured(structured)
    by_key = {f.key: f.value for f in fields}
    assert by_key["employee_name"] == "Dana"
    assert by_key["pay_period"] == "2026-06"
    assert by_key["national_id"] == "123456782"
    assert confidences.get("employee_name") == 0.9
