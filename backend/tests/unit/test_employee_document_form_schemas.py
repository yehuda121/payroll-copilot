"""Unit tests for fixed document form validation/normalization."""

from __future__ import annotations

import pytest

from payroll_copilot.application.services.employee_document_form_schemas import (
    FixedDocumentFormValidationError,
    normalize_human_text,
    structured_from_fixed_fields,
    validate_person_name,
)
from payroll_copilot.domain.enums import DocumentType


def test_normalize_human_text_collapses_whitespace():
    assert normalize_human_text("   Yehuda\t\tShmulevitz   ") == "Yehuda Shmulevitz"


def test_person_name_rejects_digits():
    with pytest.raises(FixedDocumentFormValidationError) as exc:
        validate_person_name("Yehuda123")
    assert exc.value.code == "name_digits"


def test_structured_from_fixed_fields_rejects_invalid_national_id():
    with pytest.raises(FixedDocumentFormValidationError) as exc:
        structured_from_fixed_fields(
            DocumentType.NATIONAL_ID,
            [{"key": "national_id", "value": "123456789"}],
        )
    assert exc.value.code == "national_id_checksum"


def test_structured_from_fixed_fields_normalizes_name_and_birth():
    structured = structured_from_fixed_fields(
        DocumentType.NATIONAL_ID,
        [
            {"key": "full_name", "value": "  Yehuda   Shmulevitz "},
            {"key": "national_id", "value": "313366783"},
            {"key": "birth_date", "value": "25.11.1994"},
        ],
    )
    fields = structured["additional_fields"]
    assert fields["full_name"]["value"] == "Yehuda Shmulevitz"
    assert fields["birth_date"]["value"] == "1994-11-25"


def test_appendix_children_drop_empty_and_reject_partial():
    structured = structured_from_fixed_fields(
        DocumentType.ID_APPENDIX,
        [
            {
                "key": "children",
                "value": [
                    {"name": "", "birth_date": ""},
                    {"name": "נועה", "birth_date": "12.03.2015"},
                ],
            }
        ],
    )
    assert structured["additional_fields"]["children"]["value"] == [
        {"name": "נועה", "birth_date": "2015-03-12"}
    ]

    with pytest.raises(FixedDocumentFormValidationError) as exc:
        structured_from_fixed_fields(
            DocumentType.ID_APPENDIX,
            [{"key": "children", "value": [{"name": "נועה", "birth_date": ""}]}],
        )
    assert exc.value.code == "child_incomplete"
