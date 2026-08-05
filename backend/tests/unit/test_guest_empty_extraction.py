"""Guest extraction must not present empty Document Model as a successful review."""

from __future__ import annotations

import pytest

from payroll_copilot.application.services.deterministic_pdf.types import (
    DeterministicExtractionErrorCode,
    DeterministicExtractionResult,
    DeterministicExtractionStatus,
    EXTRACTOR_VERSION,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
    _count_usable_fields,
    _fields_from_structured,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentType


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


class _EmptyDeterministic:
    def extract(self, content: bytes, *, document_type, filename=None, mime_type=None):  # noqa: ANN001
        _ = content, document_type, filename, mime_type
        return DeterministicExtractionResult(
            status=DeterministicExtractionStatus.FAILED,
            document_type=DocumentType.PAYSLIP.value,
            page_count=1,
            page_texts=("text layer present but no fields",),
            raw_text="text layer present but no fields",
            fields=(),
            warnings=("no_fields_matched",),
            error_code=DeterministicExtractionErrorCode.NO_USABLE_FIELDS.value,
            error_message="No usable fields",
            structured={
                "dynamic_entries": [],
                "extractor_meta": {"extractor_version": EXTRACTOR_VERSION},
            },
        )


@pytest.mark.asyncio
async def test_all_empty_document_model_is_failed_not_reviewable() -> None:
    use_case = ExtractGuestPayslipUseCase(
        document_repository=_FakeDocs(),
        extraction_repository=_FakeExtractions(),
        object_storage=_FakeStorage(),
        organization_bootstrap=_FakeBootstrap(),
        deterministic_extractor=_EmptyDeterministic(),
    )
    result = await use_case.execute(
        GuestPayslipExtractionCommand(
            content=b"%PDF-1.4 fake",
            original_filename="slip.pdf",
            mime_type="application/pdf",
            language="auto",
            ephemeral=False,
        )
    )
    # Gate may reject malformed PDF before extractor; either way must not be reviewable.
    assert result.parser_status in {"failed", "skipped"}
    assert result.error_message
    assert _count_usable_fields(result.fields) == 0


def test_count_usable_fields_ignores_missing() -> None:
    structured = {
        "additional_fields": {
            "employee_name": {"value": "Dana", "status": "FOUND", "confidence": 0.9},
            "base_salary": {"value": None, "status": "MISSING", "confidence": None},
        }
    }
    fields, _ = _fields_from_structured(structured)
    assert _count_usable_fields(fields) == 1
