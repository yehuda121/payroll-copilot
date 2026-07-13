"""Unit tests for Phase 2A AI payslip parser (fake LLM — no Ollama required)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from payroll_copilot.application.exceptions import (
    PayslipParserEmptyOcrError,
    PayslipParserJsonError,
    PayslipParserSchemaError,
)
from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    PayslipParseResult,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.payslip_field_sanitizer import (
    sanitize_field,
    sanitize_structured_payslip,
    source_appears_in_ocr,
)
from payroll_copilot.application.use_cases.parse_payslip import (
    ParsePayslipFromOcrCommand,
    ParsePayslipFromOcrUseCase,
)
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import (
    _parse_json_object,
    coerce_structured_payslip,
)


OCR_SAMPLE = (
    "Employee: Dana Levi\n"
    "ID 123456789\n"
    "Period 03/2024\n"
    "Base salary 12,000\n"
    "Net pay 9,850\n"
)


def _found(value: Any, source: str, conf: float | None = 0.9) -> ExtractedField:
    return ExtractedField(
        value=value,
        confidence=conf,
        source_text=source,
        status=FieldExtractionStatus.FOUND,
    )


def test_source_appears_in_ocr() -> None:
    assert source_appears_in_ocr("Dana Levi", OCR_SAMPLE)
    assert source_appears_in_ocr("12,000", OCR_SAMPLE)
    assert not source_appears_in_ocr("Totally Missing Value", OCR_SAMPLE)


def test_sanitize_clears_unjustified_confidence() -> None:
    field = _found("Ghost Corp", "Ghost Corp", 0.95)
    cleaned = sanitize_field(field, ocr_text=OCR_SAMPLE)
    assert cleaned.status == FieldExtractionStatus.UNCERTAIN
    assert cleaned.confidence is None


def test_sanitize_keeps_justified_confidence() -> None:
    field = _found("Dana Levi", "Employee: Dana Levi", 0.88)
    cleaned = sanitize_field(field, ocr_text=OCR_SAMPLE)
    assert cleaned.status == FieldExtractionStatus.FOUND
    assert cleaned.confidence == 0.88


def test_sanitize_missing_forces_null_confidence() -> None:
    field = ExtractedField(
        value="x",
        confidence=0.7,
        source_text="x",
        status=FieldExtractionStatus.MISSING,
    )
    cleaned = sanitize_field(field, ocr_text=OCR_SAMPLE)
    assert cleaned.confidence is None
    assert cleaned.value is None or cleaned.value == "x"


def test_coerce_structured_payslip_requires_complete_instances() -> None:
    from payroll_copilot.infrastructure.ai.payslip_parser_ollama import (
        build_payslip_instance_template,
    )

    payload = build_payslip_instance_template(language="he")
    payload["employee_name"] = {
        "value": "Dana Levi",
        "confidence": 0.9,
        "source_text": "Employee: Dana Levi",
        "status": "FOUND",
        "evidence_ids": [],
        "source_bbox": None,
        "source_page": None,
        "parser_method": "layout_llm",
        "warnings": [],
        "normalized_value": None,
    }
    parsed = coerce_structured_payslip(payload)
    assert parsed.employee_name.status == FieldExtractionStatus.FOUND
    assert parsed.net_salary.status == FieldExtractionStatus.MISSING


def test_parse_json_object_rejects_non_object() -> None:
    with pytest.raises(PayslipParserJsonError):
        _parse_json_object("[1,2,3]")


class _FakeParser:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def parse(self, **kwargs: Any) -> PayslipParseResult:
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _valid_result(*, retry_used: bool = False) -> PayslipParseResult:
    fields = StructuredPayslipParse(
        employee_name=_found("Dana Levi", "Employee: Dana Levi", 0.9),
        base_salary=_found(12000, "Base salary 12,000", 0.8),
        language="he",
    )
    return PayslipParseResult(
        model="fake-model",
        language="he",
        fields=fields,
        raw_model_response="{}",
        warnings=[],
        retry_used=retry_used,
    )


@pytest.mark.asyncio
async def test_use_case_empty_ocr() -> None:
    use_case = ParsePayslipFromOcrUseCase(_FakeParser([]), timeout_seconds=5)
    with pytest.raises(PayslipParserEmptyOcrError):
        await use_case.execute(ParsePayslipFromOcrCommand(raw_text="   "))


@pytest.mark.asyncio
async def test_use_case_success_sanitizes() -> None:
    parser = _FakeParser([_valid_result()])
    use_case = ParsePayslipFromOcrUseCase(parser, timeout_seconds=5)
    result = await use_case.execute(
        ParsePayslipFromOcrCommand(raw_text=OCR_SAMPLE, language="he")
    )
    assert result.fields.employee_name.value == "Dana Levi"
    assert result.fields.employee_name.confidence == 0.9
    assert result.retry_used is False
    assert parser.calls == 1


@pytest.mark.asyncio
async def test_use_case_retries_once_on_json_error() -> None:
    parser = _FakeParser(
        [
            PayslipParserJsonError("bad json"),
            _valid_result(),
        ]
    )
    use_case = ParsePayslipFromOcrUseCase(parser, timeout_seconds=5)
    result = await use_case.execute(
        ParsePayslipFromOcrCommand(raw_text=OCR_SAMPLE, language="en")
    )
    assert parser.calls == 2
    assert result.retry_used is True
    assert any("retried" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_use_case_fails_after_retry() -> None:
    parser = _FakeParser(
        [
            PayslipParserJsonError("bad json"),
            PayslipParserSchemaError("still bad"),
        ]
    )
    use_case = ParsePayslipFromOcrUseCase(parser, timeout_seconds=5)
    with pytest.raises(PayslipParserSchemaError):
        await use_case.execute(ParsePayslipFromOcrCommand(raw_text=OCR_SAMPLE))
    assert parser.calls == 2


def test_sanitize_structured_nulls_fake_confidence() -> None:
    parsed = StructuredPayslipParse(
        employee_name=_found("Not In OCR", "Not In OCR", 0.99),
    )
    cleaned = sanitize_structured_payslip(parsed, ocr_text=OCR_SAMPLE)
    assert cleaned.employee_name.confidence is None
    assert cleaned.employee_name.status == FieldExtractionStatus.UNCERTAIN


def test_confidence_validator_rejects_out_of_range() -> None:
    field = ExtractedField.model_validate(
        {
            "value": "x",
            "confidence": 1.5,
            "source_text": "x",
            "status": "FOUND",
        }
    )
    assert field.confidence is None
