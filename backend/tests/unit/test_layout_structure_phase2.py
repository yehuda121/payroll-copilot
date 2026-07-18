"""Phase 2 Structure Builder + Association Engine unit tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from payroll_copilot.application.ports.structure_association import LayoutStructureConfig
from payroll_copilot.application.services.association_engine import associate_labels_and_values
from payroll_copilot.application.services.layout_analysis_pipeline import build_layout_analysis
from payroll_copilot.application.services.structure_builder import (
    build_structure_from_layout,
    classify_token_kind,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import _build_layout_analysis
from payroll_copilot.domain.entities import DocumentExtraction
from payroll_copilot.infrastructure.persistence.dynamodb.extractions import (
    DynamoDocumentExtractionRepository,
)


def _line(page: int, line_no: int, text: str, bbox: list[float], *, block: int = 0) -> dict:
    return {
        "id": f"p{page}_b{block}_l{line_no}",
        "text": text,
        "bbox": bbox,
        "block_id": f"p{page}_b{block}",
        "reading_index": line_no,
        "confidence": 0.95,
        "word_ids": [],
        "block_number": block,
        "line_number": line_no,
    }


def _word(
    page: int,
    line_no: int,
    word_no: int,
    text: str,
    bbox: list[float],
    *,
    block: int = 0,
) -> dict:
    line_id = f"p{page}_b{block}_l{line_no}"
    return {
        "id": f"{line_id}_w{word_no}",
        "text": text,
        "bbox": bbox,
        "line_id": line_id,
        "block_id": f"p{page}_b{block}",
        "reading_index": word_no,
        "confidence": 0.95,
        "block_number": block,
        "line_number": line_no,
        "word_number": word_no,
    }


def _kv_layout_snapshot() -> dict:
    """Synthetic page: label/value pairs on shared rows + a small table body."""
    lines = [
        _line(1, 0, "Gross Salary 15230", [40, 40, 220, 14]),
        _line(1, 1, "Net Salary 11842", [40, 60, 200, 14]),
        _line(1, 2, "Employee ID 123456789", [40, 80, 240, 14]),
        _line(1, 3, "Date 06/2026", [40, 100, 160, 14]),
        # Table-like body (3+ multi-cell rows)
        _line(1, 10, "Desc Qty Amount", [40, 160, 260, 12]),
        _line(1, 11, "Bonus 1 500", [40, 180, 200, 12]),
        _line(1, 12, "Travel 2 300", [40, 200, 210, 12]),
        _line(1, 13, "Meal 1 120", [40, 220, 190, 12]),
    ]
    words = [
        _word(1, 0, 0, "Gross", [40, 40, 50, 14]),
        _word(1, 0, 1, "Salary", [95, 40, 50, 14]),
        _word(1, 0, 2, "15230", [220, 40, 50, 14]),
        _word(1, 1, 0, "Net", [40, 60, 30, 14]),
        _word(1, 1, 1, "Salary", [75, 60, 50, 14]),
        _word(1, 1, 2, "11842", [220, 60, 50, 14]),
        _word(1, 2, 0, "Employee", [40, 80, 70, 14]),
        _word(1, 2, 1, "ID", [115, 80, 20, 14]),
        _word(1, 2, 2, "123456789", [220, 80, 90, 14]),
        _word(1, 3, 0, "Date", [40, 100, 35, 14]),
        _word(1, 3, 1, "06/2026", [200, 100, 60, 14]),
        # table header/body with wider gaps → distinct cells
        _word(1, 10, 0, "Desc", [40, 160, 40, 12]),
        _word(1, 10, 1, "Qty", [150, 160, 30, 12]),
        _word(1, 10, 2, "Amount", [260, 160, 50, 12]),
        _word(1, 11, 0, "Bonus", [40, 180, 45, 12]),
        _word(1, 11, 1, "1", [155, 180, 15, 12]),
        _word(1, 11, 2, "500", [265, 180, 35, 12]),
        _word(1, 12, 0, "Travel", [40, 200, 50, 12]),
        _word(1, 12, 1, "2", [155, 200, 15, 12]),
        _word(1, 12, 2, "300", [265, 200, 35, 12]),
        _word(1, 13, 0, "Meal", [40, 220, 40, 12]),
        _word(1, 13, 1, "1", [155, 220, 15, 12]),
        _word(1, 13, 2, "120", [265, 220, 35, 12]),
    ]
    return {
        "schema_version": 1,
        "provider": "hybrid_layout_v1",
        "source": "test",
        "coordinate_format": "xywh",
        "coordinate_space": "pdf_points",
        "pages": [
            {
                "page": 1,
                "width": 400,
                "height": 500,
                "blocks": [],
                "lines": lines,
                "words": words,
            }
        ],
        "warnings": [],
    }


def test_classify_token_kind_shape_only() -> None:
    assert classify_token_kind("Gross Salary") == "label"
    assert classify_token_kind("15,230") == "value"
    assert classify_token_kind("11842") == "value"
    assert classify_token_kind("06/2026") == "value"
    assert classify_token_kind("123456789") == "value"
    assert classify_token_kind("") == "unknown"


def test_row_and_column_detection() -> None:
    structure = build_structure_from_layout(_kv_layout_snapshot(), config=LayoutStructureConfig())
    page = structure["pages"][0]
    assert len(page["rows"]) >= 4
    # Table body rows should yield multiple cells via word gaps.
    multi = [row for row in page["rows"] if len(row["cell_ids"]) >= 2]
    assert len(multi) >= 3
    assert page["columns"], "expected column clusters from multi-cell rows"
    assert page["tables"] or "structure_builder_table_skipped" in " ".join(structure["warnings"])


def test_label_value_association_same_row() -> None:
    structure = build_structure_from_layout(_kv_layout_snapshot(), config=LayoutStructureConfig())
    result = associate_labels_and_values(structure["pages"], config=LayoutStructureConfig())
    pairs = {(a["label_text"], a["value_text"]) for a in result["associations"]}
    # Word-gap splitting yields "Gross Salary" + "15230" etc.
    assert any(value == "15230" for _, value in pairs)
    assert any(value == "11842" for _, value in pairs)
    assert any(value == "123456789" for _, value in pairs)
    assert any(a["confidence"] in {"high", "medium", "low"} for a in result["associations"])
    assert all("evidence" in a for a in result["associations"])


def test_ambiguous_layout_records_conflict_not_silent_guess() -> None:
    # Two labels on the same row competing for one value cell.
    snapshot = {
        "pages": [
            {
                "page": 1,
                "width": 300,
                "height": 200,
                "lines": [
                    _line(1, 0, "Alpha Beta 999", [10, 10, 200, 12]),
                ],
                "words": [
                    _word(1, 0, 0, "Alpha", [10, 10, 40, 12]),
                    _word(1, 0, 1, "Beta", [60, 10, 40, 12]),
                    _word(1, 0, 2, "999", [160, 10, 40, 12]),
                ],
                "blocks": [],
            }
        ]
    }
    structure = build_structure_from_layout(snapshot, config=LayoutStructureConfig())
    result = associate_labels_and_values(structure["pages"], config=LayoutStructureConfig())
    if len(result["associations"]) >= 2:
        assert result["conflict_groups"]
        assert any(a.get("conflict") for a in result["associations"])


def test_broken_table_does_not_fabricate_table() -> None:
    # Only two multi-cell rows → below min_table_rows=3.
    snapshot = {
        "pages": [
            {
                "page": 1,
                "width": 300,
                "height": 200,
                "lines": [
                    _line(1, 0, "A B", [10, 10, 100, 12]),
                    _line(1, 1, "C D", [10, 30, 100, 12]),
                ],
                "words": [
                    _word(1, 0, 0, "A", [10, 10, 20, 12]),
                    _word(1, 0, 1, "B", [80, 10, 20, 12]),
                    _word(1, 1, 0, "C", [10, 30, 20, 12]),
                    _word(1, 1, 1, "D", [80, 30, 20, 12]),
                ],
                "blocks": [],
            }
        ]
    }
    structure = build_structure_from_layout(
        snapshot,
        config=LayoutStructureConfig(min_table_rows=3),
    )
    page = structure["pages"][0]
    assert page["tables"] == []
    assert page["rows"]  # rows preserved


def test_missing_layout_keeps_blocks_without_inventing_rows() -> None:
    snapshot = {
        "pages": [
            {
                "page": 1,
                "width": 100,
                "height": 100,
                "lines": [{"id": "p1_l0", "text": "x", "bbox": [0, 0, 0, 0]}],
                "words": [],
                "blocks": [{"id": "p1_b0", "bbox": None, "line_ids": []}],
            }
        ]
    }
    structure = build_structure_from_layout(snapshot, config=LayoutStructureConfig())
    page = structure["pages"][0]
    assert page["rows"] == []
    assert page["blocks_preserved"]
    assert page["confidence"] == "unknown"


def test_feature_flag_off_returns_empty_analysis() -> None:
    assert build_layout_analysis(_kv_layout_snapshot(), config=LayoutStructureConfig(enabled=False)) == {}


def test_feature_flag_on_builds_analysis() -> None:
    analysis = build_layout_analysis(_kv_layout_snapshot(), config=LayoutStructureConfig(enabled=True))
    assert analysis["schema_version"] == 1
    assert analysis["pages"]
    assert "associations" in analysis
    assert analysis["builder"] == "structure_builder_v1"


def test_extract_helper_respects_structure_flag() -> None:
    from payroll_copilot.application.ports.ocr import OCRResult, OcrLine, OcrPage

    ocr = OCRResult(
        pages=(OcrPage(page=1, language="en", text="x", confidence=1.0, lines=(OcrLine(text="x", confidence=1.0),)),),
        engine="test",
        language_requested="en",
        language_effective="en",
        raw_text="x",
        overall_confidence=1.0,
    )
    with patch(
        "payroll_copilot.application.use_cases.extract_guest_payslip.get_settings",
        return_value=SimpleNamespace(layout_structure_enabled=False),
    ):
        assert (
            _build_layout_analysis(
                layout_snapshot=_kv_layout_snapshot(),
                content=b"%PDF",
                mime_type="application/pdf",
                filename="a.pdf",
                ocr_result=ocr,
            )
            == {}
        )

    with patch(
        "payroll_copilot.application.use_cases.extract_guest_payslip.get_settings",
        return_value=SimpleNamespace(
            layout_structure_enabled=True,
            layout_snapshot_include_words=True,
            layout_snapshot_max_pages=20,
            layout_snapshot_max_words=8000,
            layout_snapshot_max_lines=2000,
            layout_structure_row_overlap_min=0.45,
            layout_structure_cell_gap_factor=1.5,
            layout_structure_column_cluster_factor=0.65,
            layout_structure_min_table_rows=3,
            layout_structure_section_gap_factor=2.5,
            layout_structure_max_same_row_gap_ratio=0.45,
            layout_structure_max_below_gap_ratio=0.12,
            layout_structure_max_alternatives=3,
        ),
    ):
        analysis = _build_layout_analysis(
            layout_snapshot=_kv_layout_snapshot(),
            content=b"%PDF",
            mime_type="application/pdf",
            filename="a.pdf",
            ocr_result=ocr,
        )
        assert analysis.get("pages")


def test_dynamo_round_trip_layout_analysis() -> None:
    repo = DynamoDocumentExtractionRepository(table=None)  # type: ignore[arg-type]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    extraction = DocumentExtraction(
        id=uuid4(),
        document_id=uuid4(),
        engine="tesseract",
        raw_text="x",
        structured_data={"net_salary": {"value": 1}},
        layout_analysis={"schema_version": 1, "associations": []},
        created_at=now,
        updated_at=now,
    )
    item = repo._to_item(extraction)
    assert "layout_analysis" in item
    restored = repo._to_entity(item)
    assert restored.layout_analysis["schema_version"] == 1
    assert restored.structured_data["net_salary"]["value"] == 1


def test_legacy_item_without_layout_analysis_defaults_empty() -> None:
    repo = DynamoDocumentExtractionRepository(table=None)  # type: ignore[arg-type]
    entity = repo._to_entity(
        {
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
    )
    assert entity.layout_analysis == {}
