"""Phase 1 layout preservation — snapshot generation and feature flag."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import fitz

from payroll_copilot.application.ports.layout import LayoutBuildRequest, LayoutSnapshotConfig
from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage, OcrWord
from payroll_copilot.application.use_cases.extract_guest_payslip import _build_layout_snapshot
from payroll_copilot.domain.entities import DocumentExtraction
from payroll_copilot.infrastructure.layout.hybrid_layout_provider import HybridLayoutProvider
from payroll_copilot.infrastructure.layout.ocr_layout_snapshot import layout_snapshot_from_ocr
from payroll_copilot.infrastructure.layout.pdf_native_layout import extract_native_pdf_layout
from payroll_copilot.infrastructure.persistence.dynamodb.extractions import (
    DynamoDocumentExtractionRepository,
)
from uuid import uuid4
from datetime import datetime, timezone


def _make_text_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _ocr_with_geometry() -> OCRResult:
    word = OcrWord(
        text="Net",
        confidence=0.95,
        bbox=(10.0, 20.0, 30.0, 12.0),
        block_number=1,
        paragraph_number=0,
        line_number=2,
        word_number=0,
    )
    word2 = OcrWord(
        text="9500",
        confidence=0.93,
        bbox=(50.0, 20.0, 40.0, 12.0),
        block_number=1,
        paragraph_number=0,
        line_number=2,
        word_number=1,
    )
    line = OcrLine(
        text="Net 9500",
        confidence=0.94,
        bbox=(10.0, 20.0, 80.0, 12.0),
        words=(word, word2),
    )
    page = OcrPage(
        page=1,
        language="he",
        text="Net 9500",
        confidence=0.94,
        lines=(line,),
        words=(word, word2),
    )
    return OCRResult(
        pages=(page,),
        engine="tesseract",
        language_requested="he",
        language_effective="he",
        raw_text="Net 9500",
        overall_confidence=0.94,
        warnings=(),
    )


def test_flag_off_provider_returns_empty_snapshot() -> None:
    provider = HybridLayoutProvider(LayoutSnapshotConfig(enabled=False))
    pdf = _make_text_pdf("Gross Salary 15230")
    snapshot = provider.build(
        LayoutBuildRequest(
            content=pdf,
            media_type="application/pdf",
            ocr_result=_ocr_with_geometry(),
            filename="slip.pdf",
        )
    )
    assert snapshot == {}


def test_flag_on_native_pdf_preserves_bboxes_and_reading_order() -> None:
    provider = HybridLayoutProvider(LayoutSnapshotConfig(enabled=True))
    pdf = _make_text_pdf("Gross Salary 15230\nNet Salary 11842")
    snapshot = provider.build(
        LayoutBuildRequest(
            content=pdf,
            media_type="application/pdf",
            ocr_result=_ocr_with_geometry(),
            filename="slip.pdf",
        )
    )
    assert snapshot["source"] == "pdf_native"
    assert snapshot["coordinate_format"] == "xywh"
    assert snapshot["coordinate_space"] == "pdf_points"
    assert snapshot["schema_version"] == 1
    assert snapshot["page_count"] >= 1
    page = snapshot["pages"][0]
    assert page["width"] and page["height"]
    assert page["lines"]
    assert any(
        isinstance(line.get("bbox"), list) and line["bbox"][2] > 0 and line["bbox"][3] > 0
        for line in page["lines"]
    )
    assert page["words"]
    reading = [word["reading_index"] for word in page["words"]]
    assert reading == sorted(reading)


def test_ocr_projection_preserves_existing_geometry() -> None:
    snapshot = layout_snapshot_from_ocr(_ocr_with_geometry())
    assert snapshot["source"] == "ocr_result"
    page = snapshot["pages"][0]
    assert len(page["lines"]) == 1
    assert page["lines"][0]["bbox"] == [10.0, 20.0, 80.0, 12.0]
    assert len(page["words"]) == 2
    assert page["words"][0]["text"] == "Net"
    assert page["blocks"]


def test_native_pdf_extract_returns_none_for_blank() -> None:
    doc = fitz.open()
    doc.new_page()
    blank = doc.tobytes()
    doc.close()
    assert extract_native_pdf_layout(blank) is None


def test_build_layout_snapshot_respects_settings_flag() -> None:
    ocr = _ocr_with_geometry()
    pdf = _make_text_pdf("Identity Number 123456789")

    with patch(
        "payroll_copilot.application.use_cases.extract_guest_payslip.get_settings",
        return_value=SimpleNamespace(layout_snapshot_enabled=False),
    ):
        assert _build_layout_snapshot(
            content=pdf,
            mime_type="application/pdf",
            filename="a.pdf",
            ocr_result=ocr,
        ) == {}

    with patch(
        "payroll_copilot.application.use_cases.extract_guest_payslip.get_settings",
        return_value=SimpleNamespace(
            layout_snapshot_enabled=True,
            layout_snapshot_include_words=True,
            layout_snapshot_max_pages=20,
            layout_snapshot_max_words=8000,
            layout_snapshot_max_lines=2000,
        ),
    ):
        snapshot = _build_layout_snapshot(
            content=pdf,
            mime_type="application/pdf",
            filename="a.pdf",
            ocr_result=ocr,
        )
        assert snapshot.get("provider") == "hybrid_layout_v1"
        assert snapshot.get("pages")


def test_dynamo_mapper_round_trips_layout_snapshot() -> None:
    repo = DynamoDocumentExtractionRepository(table=None)  # type: ignore[arg-type]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    extraction = DocumentExtraction(
        id=uuid4(),
        document_id=uuid4(),
        engine="tesseract",
        raw_text="x",
        structured_data={"net_salary": {"value": 1, "status": "FOUND"}},
        layout_snapshot={"schema_version": 1, "pages": [{"page": 1, "lines": []}]},
        created_at=now,
        updated_at=now,
    )
    item = repo._to_item(extraction)
    assert "layout_snapshot" in item
    restored = repo._to_entity(item)
    assert restored.layout_snapshot["schema_version"] == 1
    assert restored.structured_data["net_salary"]["value"] == 1


def test_legacy_dynamo_item_without_layout_snapshot_defaults_empty() -> None:
    repo = DynamoDocumentExtractionRepository(table=None)  # type: ignore[arg-type]
    item = {
        "id": str(uuid4()),
        "document_id": str(uuid4()),
        "engine": "tesseract",
        "raw_text": "",
        "structured_data": {},
        "field_confidences": {},
        "extraction_version": 1,
        "ocr_result": {},
        "warnings": [],
    }
    entity = repo._to_entity(item)
    assert entity.layout_snapshot == {}
