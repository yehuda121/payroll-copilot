"""Unit tests for DynamoDB empty-value pruning."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from payroll_copilot.domain.entities import DocumentExtraction
from payroll_copilot.infrastructure.persistence.dynamodb.extractions import (
    DynamoDocumentExtractionRepository,
)
from payroll_copilot.infrastructure.persistence.dynamodb.serde import (
    is_empty_for_storage,
    prune_empty,
)


class _SampleStatus(Enum):
    MISSING = "MISSING"
    FOUND = "FOUND"


def test_is_empty_for_storage_rules() -> None:
    assert is_empty_for_storage(None) is True
    assert is_empty_for_storage("") is True
    assert is_empty_for_storage("   ") is True
    assert is_empty_for_storage([]) is True
    assert is_empty_for_storage({}) is True
    assert is_empty_for_storage(0) is False
    assert is_empty_for_storage(False) is False
    assert is_empty_for_storage(_SampleStatus.MISSING) is False
    assert is_empty_for_storage("net") is False


def test_prune_empty_recursively_removes_vacant_values() -> None:
    payload = {
        "employee_name": {
            "value": "",
            "confidence": None,
            "warnings": [],
            "status": _SampleStatus.MISSING,
            "edited_by_user": False,
            "amount": 0,
        },
        "empty_list": [None, "", {}, []],
        "nested": {"keep": "ok", "drop": "  "},
        "blank": "   ",
    }

    pruned = prune_empty(payload)

    assert pruned == {
        "employee_name": {
            "status": _SampleStatus.MISSING,
            "edited_by_user": False,
            "amount": 0,
        },
        "nested": {"keep": "ok"},
    }


def test_extraction_to_item_prunes_empties_and_keeps_required_keys() -> None:
    repo = DynamoDocumentExtractionRepository(table=None)  # type: ignore[arg-type]
    extraction = DocumentExtraction(
        id=uuid4(),
        document_id=uuid4(),
        engine="test-engine",
        raw_text="",
        structured_data={
            "employee_name": {
                "value": None,
                "status": "MISSING",
                "confidence": None,
                "warnings": [],
                "edited_by_user": False,
            },
            "net_pay": {
                "value": 0,
                "status": "FOUND",
                "warnings": [],
            },
            "vacant": {"value": "", "warnings": []},
        },
        overall_confidence=None,
        field_confidences={},
        ocr_result={},
        layout_snapshot={},
        layout_analysis={},
        warnings=[],
        error_message=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    item = repo._to_item(extraction)

    for key in (
        "PK",
        "SK",
        "entity_type",
        "GSI1PK",
        "GSI1SK",
        "id",
        "document_id",
        "extraction_version",
        "confirmation_status",
        "ocr_status",
        "parser_status",
        "created_at",
        "updated_at",
    ):
        assert key in item

    assert "raw_text" not in item
    assert "warnings" not in item
    assert "field_confidences" not in item
    assert "ocr_result" not in item
    assert "layout_snapshot" not in item
    assert "error_message" not in item

    structured = item["structured_data"]
    assert structured["employee_name"] == {
        "status": "MISSING",
        "edited_by_user": False,
    }
    assert structured["net_pay"] == {"value": 0, "status": "FOUND"}
    assert "vacant" not in structured
