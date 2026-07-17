"""Semantic validation, coercion hardening, and Document Lab word preservation."""

from __future__ import annotations

from typing import Any

import pytest

from payroll_copilot.application.exceptions import (
    PayslipParserSemanticError,
)
from payroll_copilot.application.ports.ocr import OcrLine, OcrPage, OcrWord
from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_FIELD_KEYS,
    ExtractedField,
    FieldExtractionStatus,
    PayslipParseResult,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.document_lab import (
    DocumentLabService,
    _words_from_payload,
)
from payroll_copilot.application.services.parser_layout_context import (
    ParserLayoutConfig,
    build_parser_layout_context,
)
from payroll_copilot.application.services.parser_semantic import (
    is_invalid_additional_field_key,
    ocr_context_has_usable_evidence,
    validate_payslip_parser_payload,
)
from payroll_copilot.application.use_cases.parse_payslip import (
    ParsePayslipFromOcrCommand,
    ParsePayslipFromOcrUseCase,
)
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import (
    build_payslip_instance_template,
    coerce_structured_payslip,
)


def _missing_field() -> dict[str, Any]:
    return {
        "value": None,
        "confidence": None,
        "source_text": None,
        "status": "MISSING",
        "evidence_ids": [],
        "source_bbox": None,
        "source_page": None,
        "parser_method": "layout_llm",
        "warnings": [],
        "normalized_value": None,
    }


def _found_field(
    value: Any,
    *,
    source: str,
    evidence_ids: list[str] | None = None,
    conf: float = 0.9,
) -> dict[str, Any]:
    return {
        "value": value,
        "confidence": conf,
        "source_text": source,
        "status": "FOUND",
        "evidence_ids": evidence_ids or [],
        "source_bbox": [100.0, 200.0, 80.0, 20.0] if evidence_ids else None,
        "source_page": 1 if evidence_ids else None,
        "parser_method": "layout_llm",
        "warnings": [],
        "normalized_value": None,
    }


def _full_instance(**overrides: Any) -> dict[str, Any]:
    payload = build_payslip_instance_template(language="heb+eng", simplified=False)
    payload.update(overrides)
    return payload


OCR_WITH_AMOUNTS = "Base 8,000.00 travel 323.00 gross 8,872.30 hours 54.93"


def test_schema_copy_ref_rejected() -> None:
    payload = _full_instance(
        gross_salary={"$ref": "#/$defs/ExtractedField"},
    )
    with pytest.raises(PayslipParserSemanticError) as exc:
        validate_payslip_parser_payload(payload, ocr_text=OCR_WITH_AMOUNTS)
    assert exc.value.warning_code == "parser_schema_copy_detected"


def test_defs_rejected() -> None:
    payload = _full_instance()
    payload["$defs"] = {"ExtractedField": {"type": "object"}}
    with pytest.raises(PayslipParserSemanticError) as exc:
        validate_payslip_parser_payload(payload, ocr_text=OCR_WITH_AMOUNTS)
    assert exc.value.warning_code == "parser_schema_copy_detected"


def test_missing_required_fields_rejected() -> None:
    payload = {"employee_name": _missing_field(), "additional_fields": {}}
    with pytest.raises(PayslipParserSemanticError) as exc:
        validate_payslip_parser_payload(payload, ocr_text=OCR_WITH_AMOUNTS)
    assert exc.value.warning_code == "parser_missing_required_fields"


@pytest.mark.parametrize("key", ["323.00", "8,872.30", "4080234"])
def test_numeric_additional_field_key_rejected(key: str) -> None:
    assert is_invalid_additional_field_key(key) is True
    payload = _full_instance(
        additional_fields={key: _missing_field()},
    )
    with pytest.raises(PayslipParserSemanticError) as exc:
        validate_payslip_parser_payload(payload, ocr_text=OCR_WITH_AMOUNTS)
    assert exc.value.warning_code == "parser_invalid_additional_field_key"


def test_semantic_additional_field_key_accepted() -> None:
    assert is_invalid_additional_field_key("meal_allowance") is False
    payload = _full_instance(
        additional_fields={"meal_allowance": _missing_field()},
    )
    validate_payslip_parser_payload(
        payload,
        ocr_text="",
        layout_context=None,
        require_evidence_ids=False,
    )


def test_valid_full_instance_accepted() -> None:
    payload = _full_instance(
        base_salary=_found_field("8,000.00", source="8,000.00", evidence_ids=["p1_l1_w1"]),
    )
    layout = {
        "pages": [
            {
                "page": 1,
                "lines": [
                    {
                        "id": "p1_l1",
                        "text": "8,000.00",
                        "words": [{"id": "p1_l1_w1", "text": "8,000.00"}],
                    }
                ],
            }
        ]
    }
    validate_payslip_parser_payload(
        payload,
        ocr_text=OCR_WITH_AMOUNTS,
        layout_context=layout,
    )
    coerced = coerce_structured_payslip(payload)
    assert coerced.base_salary.status == FieldExtractionStatus.FOUND
    assert coerced.base_salary.value == "8,000.00"


def test_all_missing_with_ocr_evidence_rejected() -> None:
    payload = _full_instance()
    with pytest.raises(PayslipParserSemanticError) as exc:
        validate_payslip_parser_payload(payload, ocr_text=OCR_WITH_AMOUNTS)
    assert exc.value.warning_code == "parser_all_fields_missing_with_ocr_evidence"


def test_legitimate_all_missing_without_usable_ocr_accepted() -> None:
    payload = _full_instance()
    assert ocr_context_has_usable_evidence(ocr_text="", layout_context=None) is False
    validate_payslip_parser_payload(payload, ocr_text="", layout_context=None)


@pytest.mark.asyncio
async def test_semantic_retry_success() -> None:
    valid = _full_instance(
        base_salary=_found_field(8000, source="8,000.00", evidence_ids=["p1_l1_w1"]),
    )
    schema_copy = _full_instance(gross_salary={"$ref": "#/$defs/ExtractedField"})

    class _Parser:
        def __init__(self) -> None:
            self.calls = 0

        async def parse(self, **kwargs: Any) -> PayslipParseResult:
            self.calls += 1
            if self.calls == 1:
                validate_payslip_parser_payload(schema_copy, ocr_text=OCR_WITH_AMOUNTS)
            fields = coerce_structured_payslip(valid)
            return PayslipParseResult(
                model="fake",
                language="heb+eng",
                fields=fields,
                retry_used=bool(kwargs.get("retry_hint")),
            )

    pages = (
        OcrPage(
            page=1,
            language="heb+eng",
            text=OCR_WITH_AMOUNTS,
            confidence=0.9,
            lines=(
                OcrLine(
                    text="8,000.00",
                    confidence=0.9,
                    bbox=(100.0, 200.0, 80.0, 20.0),
                    words=(OcrWord("8,000.00", 0.9, (100.0, 200.0, 80.0, 20.0), 1, 1, 1, 1),),
                ),
            ),
        ),
    )
    parser = _Parser()
    use_case = ParsePayslipFromOcrUseCase(
        parser,
        timeout_seconds=5,
        layout_config=ParserLayoutConfig(enabled=True, include_words=True),
    )
    result = await use_case.execute(
        ParsePayslipFromOcrCommand(raw_text=OCR_WITH_AMOUNTS, language="heb+eng", pages=pages)
    )
    assert parser.calls == 2
    assert result.retry_used is True
    assert "parser_retry_used" in result.warnings
    assert "parser_schema_copy_detected" in result.warnings
    assert result.fields.base_salary.value == 8000


@pytest.mark.asyncio
async def test_semantic_retry_failure() -> None:
    schema_copy = _full_instance(gross_salary={"$ref": "#/$defs/ExtractedField"})

    class _Parser:
        def __init__(self) -> None:
            self.calls = 0

        async def parse(self, **kwargs: Any) -> PayslipParseResult:
            self.calls += 1
            validate_payslip_parser_payload(schema_copy, ocr_text=OCR_WITH_AMOUNTS)
            raise AssertionError("unreachable")

    parser = _Parser()
    use_case = ParsePayslipFromOcrUseCase(parser, timeout_seconds=5, total_budget_seconds=10)
    with pytest.raises(PayslipParserSemanticError):
        await use_case.execute(ParsePayslipFromOcrCommand(raw_text=OCR_WITH_AMOUNTS))
    assert parser.calls == 2


def test_no_silent_coercion_of_schema_stubs() -> None:
    payload = _full_instance(gross_salary={"$ref": "#/$defs/ExtractedField"})
    with pytest.raises(PayslipParserSemanticError):
        coerce_structured_payslip(payload)


def test_unknown_top_level_keys_not_promoted() -> None:
    payload = _full_instance()
    payload["4080234"] = _found_field("x", source="x")
    with pytest.raises(PayslipParserSemanticError):
        validate_payslip_parser_payload(payload, ocr_text=OCR_WITH_AMOUNTS)
    # Coercion also ignores unknown keys when called on a partial cleaned object.
    clean = _full_instance(additional_fields={"meal_allowance": _missing_field()})
    coerced = coerce_structured_payslip(clean)
    assert "4080234" not in coerced.additional_fields
    assert "meal_allowance" in coerced.additional_fields


def test_words_from_payload_preserves_hierarchy() -> None:
    words = _words_from_payload(
        [
            {
                "text": "8,000.00",
                "confidence": 0.91,
                "bbox": [867, 453, 91, 20],
                "block_number": 1,
                "paragraph_number": 2,
                "line_number": 3,
                "word_number": 4,
            }
        ]
    )
    assert len(words) == 1
    assert words[0].text == "8,000.00"
    assert words[0].bbox == (867.0, 453.0, 91.0, 20.0)
    assert words[0].block_number == 1
    assert words[0].paragraph_number == 2
    assert words[0].line_number == 3
    assert words[0].word_number == 4


@pytest.mark.asyncio
async def test_document_lab_run_parser_preserves_words_and_evidence_ids() -> None:
    captured: dict[str, Any] = {}

    class _ParseUseCase:
        async def execute(self, command: Any) -> PayslipParseResult:
            captured["pages"] = command.pages
            built = build_parser_layout_context(
                pages=command.pages,
                language="heb+eng",
                config=ParserLayoutConfig(enabled=True, include_words=True),
            )
            captured["evidence_ids"] = list(built.evidence_index.keys())
            return PayslipParseResult(
                model="fake",
                language="heb+eng",
                fields=StructuredPayslipParse(),
                warnings=[],
                retry_used=False,
            )

    class _Unused:
        async def execute(self, *_a: object, **_k: object) -> None:
            raise AssertionError("unused")

    service = DocumentLabService(
        ocr_use_case=_Unused(),  # type: ignore[arg-type]
        parse_use_case=_ParseUseCase(),  # type: ignore[arg-type]
        extract_guest_use_case=_Unused(),  # type: ignore[arg-type]
        validation_use_case=_Unused(),  # type: ignore[arg-type]
    )
    ocr_payload = {
        "engine": "tesseract",
        "language_requested": "auto",
        "language_effective": "heb+eng",
        "overall_confidence": 0.9,
        "raw_text": "8,000.00",
        "warnings": [],
        "pages": [
            {
                "page": 1,
                "language": "heb+eng",
                "text": "8,000.00",
                "confidence": 0.9,
                "lines": [
                    {
                        "text": "8,000.00",
                        "confidence": 0.9,
                        "bbox": [867, 453, 91, 20],
                        "words": [
                            {
                                "text": "8,000.00",
                                "confidence": 0.91,
                                "bbox": [867, 453, 91, 20],
                                "block_number": 1,
                                "paragraph_number": 1,
                                "line_number": 1,
                                "word_number": 1,
                            }
                        ],
                    }
                ],
                "words": [
                    {
                        "text": "8,000.00",
                        "confidence": 0.91,
                        "bbox": [867, 453, 91, 20],
                        "block_number": 1,
                        "paragraph_number": 1,
                        "line_number": 1,
                        "word_number": 1,
                    }
                ],
            }
        ],
    }
    await service.run_parser(ocr_payload=ocr_payload)
    page = captured["pages"][0]
    assert page.words[0].text == "8,000.00"
    assert page.lines[0].words[0].confidence == 0.91
    assert page.lines[0].words[0].block_number == 1
    assert "p1_l1_w1" in captured["evidence_ids"]


@pytest.mark.asyncio
async def test_all_missing_after_retry_raises() -> None:
    empty = _full_instance()

    class _Parser:
        def __init__(self) -> None:
            self.calls = 0

        async def parse(self, **kwargs: Any) -> PayslipParseResult:
            self.calls += 1
            validate_payslip_parser_payload(empty, ocr_text=OCR_WITH_AMOUNTS)
            raise AssertionError("unreachable")

    parser = _Parser()
    use_case = ParsePayslipFromOcrUseCase(parser, timeout_seconds=5, total_budget_seconds=10)
    with pytest.raises(PayslipParserSemanticError):
        await use_case.execute(ParsePayslipFromOcrCommand(raw_text=OCR_WITH_AMOUNTS))
    assert parser.calls == 2


def test_invalid_evidence_ids_rejected() -> None:
    payload = _full_instance(
        base_salary=_found_field("8,000.00", source="8,000.00", evidence_ids=["evid1"]),
    )
    layout = {
        "pages": [
            {
                "page": 1,
                "lines": [
                    {
                        "id": "p1_l1",
                        "text": "8,000.00",
                        "words": [{"id": "p1_l1_w1", "text": "8,000.00"}],
                    }
                ],
            }
        ]
    }
    with pytest.raises(PayslipParserSemanticError) as exc:
        validate_payslip_parser_payload(
            payload,
            ocr_text=OCR_WITH_AMOUNTS,
            layout_context=layout,
        )
    assert exc.value.category == "invalid_evidence_ids"

    from payroll_copilot.application.services.parser_semantic import normalize_payslip_parser_payload

    payload = _full_instance()
    payload.pop("employee_name")
    payload["name"] = _missing_field()
    payload["parser_version"] = "1.0"
    normalized, warnings = normalize_payslip_parser_payload(payload)
    assert "employee_name" in normalized
    assert "name" not in normalized
    assert "parser_version" not in normalized
    assert "parser_field_alias_normalized" in warnings
    assert "parser_unknown_top_level_stripped" in warnings


def test_instance_template_lists_all_required_fields() -> None:
    template = build_payslip_instance_template(simplified=True)
    for key in PAYSLIP_FIELD_KEYS:
        assert key in template
        assert "value" in template[key]
        assert "source_text" in template[key]
    assert "$ref" not in json_dumps_safe(template)


def json_dumps_safe(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload)
