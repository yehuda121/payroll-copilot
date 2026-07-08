"""Unit tests for Document Lab service serialization."""

from __future__ import annotations

import pytest

from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage
from payroll_copilot.application.services.document_lab import (
    DocumentLabService,
    DocumentLabSource,
    serialize_document_lab_source,
)
from payroll_copilot.application.use_cases.ocr_extract import ExtractDocumentTextCommand


def test_serialize_document_lab_source_uses_asdict_for_slotted_dataclass() -> None:
    source = DocumentLabSource(
        filename="payslip.pdf",
        media_type="application/pdf",
        source_type="fixture",
        fixture_id="valid/payslip.pdf",
    )

    assert not hasattr(source, "__dict__")
    assert serialize_document_lab_source(source) == {
        "filename": "payslip.pdf",
        "media_type": "application/pdf",
        "source_type": "fixture",
        "fixture_id": "valid/payslip.pdf",
    }


class _RecordingOcrUseCase:
    def __init__(self) -> None:
        self.commands: list[ExtractDocumentTextCommand] = []

    async def execute(self, command: ExtractDocumentTextCommand) -> OCRResult:
        self.commands.append(command)
        page = OcrPage(
            page=1,
            language="auto",
            text="fixture text",
            confidence=0.9,
            lines=(OcrLine(text="fixture text", confidence=0.9),),
        )
        return OCRResult(
            pages=(page,),
            engine="fake-ocr",
            language_requested="auto",
            language_effective="auto",
            raw_text="fixture text",
            overall_confidence=0.9,
            fields=(),
            warnings=(),
        )


class _UnusedUseCase:
    async def execute(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("unexpected use case invocation")


@pytest.mark.asyncio
async def test_run_ocr_serializes_source_after_provider_returns() -> None:
    ocr_use_case = _RecordingOcrUseCase()
    service = DocumentLabService(
        ocr_use_case=ocr_use_case,  # type: ignore[arg-type]
        parse_use_case=_UnusedUseCase(),  # type: ignore[arg-type]
        extract_guest_use_case=_UnusedUseCase(),  # type: ignore[arg-type]
        validation_use_case=_UnusedUseCase(),  # type: ignore[arg-type]
    )
    source = DocumentLabSource(
        filename="payslip.pdf",
        media_type="application/pdf",
        source_type="upload",
    )

    result = await service.run_ocr(
        content=b"%PDF-1.4",
        filename="payslip.pdf",
        media_type="application/pdf",
        language="auto",
        source=source,
    )

    assert len(ocr_use_case.commands) == 1
    assert result["source"] == serialize_document_lab_source(source)
    assert result["ocr"]["engine"] == "fake-ocr"
    assert result["ocr"]["raw_text"] == "fixture text"
