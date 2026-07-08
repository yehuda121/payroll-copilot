"""Unit tests for guest extraction corrections."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest

from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectGuestExtractionUseCase,
    FieldCorrection,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction
from payroll_copilot.domain.enums import DocumentStatus, DocumentType


class _Docs:
    def __init__(self, document: Document) -> None:
        self.document = document

    async def get_by_id(self, document_id):  # noqa: ANN001
        return self.document if self.document.id == document_id else None

    async def save(self, document: Document) -> Document:
        self.document = document
        return document


class _Extractions:
    def __init__(self) -> None:
        self.saved: list[DocumentExtraction] = []

    async def get_latest_for_document(self, document_id):  # noqa: ANN001
        matches = [e for e in self.saved if e.document_id == document_id]
        return matches[-1] if matches else None

    async def get_by_id(self, extraction_id):  # noqa: ANN001
        return next((e for e in self.saved if e.id == extraction_id), None)

    async def save(self, extraction: DocumentExtraction) -> DocumentExtraction:
        self.saved.append(extraction)
        return extraction


@pytest.mark.asyncio
async def test_corrections_create_new_version_with_edited_flag() -> None:
    document_id = uuid4()
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="k",
        original_filename="p.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="a" * 64,
        status=DocumentStatus.PROCESSED,
        created_at=datetime.utcnow(),
    )
    extractions = _Extractions()
    original = DocumentExtraction(
        id=uuid4(),
        document_id=document_id,
        engine="paddleocr",
        raw_text="Base 10000",
        structured_data={
            "base_salary": {
                "value": 10000,
                "confidence": 0.7,
                "source_text": "10000",
                "status": "FOUND",
            },
            "gross_salary": {
                "value": 12000,
                "confidence": 0.8,
                "source_text": "12000",
                "status": "FOUND",
            },
        },
        overall_confidence=0.8,
        field_confidences={},
        extraction_version=1,
        created_at=datetime.utcnow(),
        ocr_result={"pages": []},
        parser_status="completed",
        ocr_status="completed",
    )
    await extractions.save(original)

    use_case = CorrectGuestExtractionUseCase(
        document_repository=_Docs(document),
        extraction_repository=extractions,
    )
    result = await use_case.execute(
        document_id=document_id,
        corrections=[FieldCorrection(key="base_salary", value=11000)],
    )

    assert result.extraction_version == 2
    assert result.extraction_id != original.id
    assert len(extractions.saved) == 2
    latest = extractions.saved[-1]
    assert latest.ocr_result == original.ocr_result
    assert latest.raw_text == original.raw_text
    edited = latest.structured_data["base_salary"]
    assert edited["value"] == 11000
    assert edited["edited_by_user"] is True
    assert edited["original_value"] == 10000
    assert edited["source_text"] == "10000"
    assert edited["confidence"] == 1.0
    assert latest.structured_data["gross_salary"]["value"] == 12000
