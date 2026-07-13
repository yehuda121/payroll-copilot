"""Unit tests for layout-aware payslip parser context and evidence validation."""

from __future__ import annotations

import json

import pytest

from payroll_copilot.application.ports.ocr import OcrLine, OcrPage, OcrWord
from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.parser_evidence import (
    is_valid_evidence_id,
    normalize_numeric_token,
    validate_extracted_field_evidence,
    validate_structured_payslip_evidence,
)
from payroll_copilot.application.services.parser_layout_context import (
    ParserLayoutConfig,
    build_parser_layout_context,
)
from payroll_copilot.application.use_cases.parse_payslip import (
    ParsePayslipFromOcrCommand,
    ParsePayslipFromOcrUseCase,
)
from payroll_copilot.application.ports.payslip_parser import PayslipParseResult
from payroll_copilot.application.exceptions import PayslipParserJsonError


def _sample_pages() -> tuple[OcrPage, ...]:
    words = (
        OcrWord("8,000.00", 0.95, (100.0, 200.0, 80.0, 20.0), 1, 1, 1, 1),
        OcrWord("323.00", 0.9, (200.0, 200.0, 60.0, 20.0), 1, 1, 1, 2),
        OcrWord("54.93", 0.7, (300.0, 220.0, 50.0, 18.0), 1, 1, 2, 1),
    )
    line1 = OcrLine(
        text="בסיס 8,000.00 נסיעות 323.00",
        confidence=0.92,
        bbox=(90.0, 195.0, 200.0, 30.0),
        words=words[:2],
    )
    line2 = OcrLine(
        text="שעות 54.93",
        confidence=0.7,
        bbox=(290.0, 215.0, 80.0, 25.0),
        words=words[2:],
    )
    return (
        OcrPage(
            page=1,
            language="auto",
            text=f"{line1.text}\n{line2.text}",
            confidence=0.85,
            lines=(line1, line2),
            words=words,
        ),
    )


def test_layout_context_preserves_text_bbox_and_stable_ids() -> None:
    built = build_parser_layout_context(
        pages=_sample_pages(),
        language="heb+eng",
        config=ParserLayoutConfig(enabled=True, include_words=True),
    )
    assert built.line_count == 2
    assert built.word_count == 3
    assert "p1_l1" in built.evidence_index
    assert "p1_l1_w1" in built.evidence_index
    assert built.evidence_index["p1_l1_w1"]["text"] == "8,000.00"
    assert built.evidence_index["p1_l1_w1"]["bbox"] == [100.0, 200.0, 80.0, 20.0]
    again = build_parser_layout_context(
        pages=_sample_pages(),
        language="heb+eng",
        config=ParserLayoutConfig(enabled=True, include_words=True),
    )
    assert again.payload == built.payload


def test_context_size_limits_truncate_safely() -> None:
    built = build_parser_layout_context(
        pages=_sample_pages(),
        language="heb+eng",
        config=ParserLayoutConfig(
            enabled=True,
            include_words=True,
            max_lines=1,
            max_words=10,
            max_context_chars=50_000,
        ),
    )
    assert built.truncated is True
    assert built.line_count == 1
    # Payload must remain valid JSON-serializable structure.
    json.dumps(built.payload)


def test_evidence_id_validation() -> None:
    assert is_valid_evidence_id("p1_l3")
    assert is_valid_evidence_id("p1_l3_w2")
    assert not is_valid_evidence_id("line-1")
    assert not is_valid_evidence_id("p1")


def test_numeric_normalization_and_digit_invention_rejection() -> None:
    assert normalize_numeric_token("8,000.00") == 8000.0
    assert normalize_numeric_token("323.00") == 323.0
    index = {
        "p1_l1_w1": {"type": "word", "page": 1, "text": "8,000.00", "confidence": 0.95, "bbox": [1, 2, 3, 4]},
        "p1_l2_w1": {"type": "word", "page": 1, "text": "54.93", "confidence": 0.7, "bbox": [5, 6, 7, 8]},
    }
    ok = validate_extracted_field_evidence(
        ExtractedField(
            value=8000.0,
            confidence=0.9,
            source_text="8,000.00",
            status=FieldExtractionStatus.FOUND,
            evidence_ids=["p1_l1_w1"],
            source_bbox=[1, 2, 3, 4],
            source_page=1,
            parser_method="layout_llm",
        ),
        evidence_index=index,
        ocr_text="8,000.00 54.93",
    )
    assert ok.status == FieldExtractionStatus.FOUND
    assert ok.normalized_value == 8000.0

    invented = validate_extracted_field_evidence(
        ExtractedField(
            value=549.30,
            confidence=0.9,
            source_text="54.93",
            status=FieldExtractionStatus.FOUND,
            evidence_ids=["p1_l2_w1"],
            source_page=1,
            parser_method="layout_llm",
        ),
        evidence_index=index,
        ocr_text="8,000.00 54.93",
    )
    assert invented.value is None
    assert invented.status == FieldExtractionStatus.UNCERTAIN
    assert invented.warnings  # rejected for inventing digits / value mismatch
    assert any(
        w.startswith("numeric_value_mismatches_evidence") or w.startswith("value_not_supported_by_source_text")
        for w in invented.warnings
    )


def test_unknown_evidence_id_and_source_text_rejected() -> None:
    index = {
        "p1_l1_w1": {"type": "word", "page": 1, "text": "323.00", "confidence": 0.9, "bbox": [1, 2, 3, 4]},
    }
    unknown = validate_extracted_field_evidence(
        ExtractedField(
            value=323.0,
            confidence=0.9,
            source_text="323.00",
            status=FieldExtractionStatus.FOUND,
            evidence_ids=["p9_l9_w9"],
        ),
        evidence_index=index,
        ocr_text="323.00",
    )
    assert unknown.value is None

    invented_source = validate_extracted_field_evidence(
        ExtractedField(
            value="Ghost",
            confidence=0.9,
            source_text="Ghost Name",
            status=FieldExtractionStatus.FOUND,
            evidence_ids=["p1_l1_w1"],
        ),
        evidence_index=index,
        ocr_text="323.00",
    )
    assert invented_source.value is None


def test_bbox_and_confidence_policy() -> None:
    index = {
        "p1_l1_w1": {
            "type": "word",
            "page": 1,
            "text": "8,872.30",
            "confidence": 0.8,
            "bbox": [10.0, 20.0, 30.0, 12.0],
        }
    }
    capped = validate_extracted_field_evidence(
        ExtractedField(
            value=8872.30,
            confidence=0.99,
            source_text="8,872.30",
            status=FieldExtractionStatus.FOUND,
            evidence_ids=["p1_l1_w1"],
            source_bbox=[10.0, 20.0, 30.0, 12.0],
            source_page=1,
        ),
        evidence_index=index,
        ocr_text="8,872.30",
    )
    assert capped.confidence == pytest.approx(0.8)

    bad_bbox = validate_extracted_field_evidence(
        ExtractedField(
            value=8872.30,
            confidence=0.7,
            source_text="8,872.30",
            status=FieldExtractionStatus.FOUND,
            evidence_ids=["p1_l1_w1"],
            source_bbox=[999.0, 999.0, 10.0, 10.0],
            source_page=1,
        ),
        evidence_index=index,
        ocr_text="8,872.30",
    )
    assert bad_bbox.value is None


def test_missing_field_without_evidence() -> None:
    field = validate_extracted_field_evidence(
        ExtractedField(value=None, status=FieldExtractionStatus.MISSING),
        evidence_index={},
        ocr_text="anything",
    )
    assert field.status == FieldExtractionStatus.MISSING
    assert field.value is None


def test_no_reasoning_field_in_schema() -> None:
    schema = StructuredPayslipParse.model_json_schema()
    assert "reasoning" not in json.dumps(schema).casefold()
    assert "chain" not in json.dumps(ExtractedField.model_json_schema()).casefold()


@pytest.mark.asyncio
async def test_use_case_evidence_validation_rejects_invented_name() -> None:
    pages = _sample_pages()
    ocr_text = pages[0].text

    class _FakeParser:
        async def parse(self, **kwargs):  # noqa: ANN003
            fields = StructuredPayslipParse(
                employee_name=ExtractedField(
                    value="סבירסקי אורית",
                    confidence=0.95,
                    source_text="סבירסקי אורית",
                    status=FieldExtractionStatus.FOUND,
                    evidence_ids=["p1_l1_w1"],
                    source_page=1,
                ),
                base_salary=ExtractedField(
                    value=8000.0,
                    confidence=0.9,
                    source_text="8,000.00",
                    status=FieldExtractionStatus.FOUND,
                    evidence_ids=["p1_l1_w1"],
                    source_bbox=[100.0, 200.0, 80.0, 20.0],
                    source_page=1,
                ),
            )
            return PayslipParseResult(model="fake", language="heb+eng", fields=fields)

    use_case = ParsePayslipFromOcrUseCase(
        _FakeParser(),
        timeout_seconds=5,
        layout_config=ParserLayoutConfig(enabled=True, include_words=True),
    )
    result = await use_case.execute(
        ParsePayslipFromOcrCommand(raw_text=ocr_text, language="heb+eng", pages=pages)
    )
    assert result.fields.employee_name.value is None
    assert result.fields.base_salary.value == 8000.0
    assert result.fields.base_salary.evidence_ids == ["p1_l1_w1"]


@pytest.mark.asyncio
async def test_use_case_retry_once_on_invalid_json() -> None:
    class _RetryParser:
        def __init__(self) -> None:
            self.calls = 0

        async def parse(self, **kwargs):  # noqa: ANN003
            self.calls += 1
            if self.calls == 1:
                raise PayslipParserJsonError("bad json")
            return PayslipParseResult(
                model="fake",
                language="en",
                fields=StructuredPayslipParse(
                    base_salary=ExtractedField(
                        value=8000.0,
                        confidence=0.9,
                        source_text="8,000.00",
                        status=FieldExtractionStatus.FOUND,
                        evidence_ids=["p1_l1_w1"],
                        source_bbox=[100.0, 200.0, 80.0, 20.0],
                        source_page=1,
                    )
                ),
                retry_used=True,
            )

    parser = _RetryParser()
    use_case = ParsePayslipFromOcrUseCase(
        parser,
        timeout_seconds=5,
        layout_config=ParserLayoutConfig(enabled=True),
    )
    result = await use_case.execute(
        ParsePayslipFromOcrCommand(
            raw_text=_sample_pages()[0].text,
            language="heb+eng",
            pages=_sample_pages(),
        )
    )
    assert parser.calls == 2
    assert result.retry_used is True
    assert result.fields.base_salary.value == 8000.0


def test_structured_validation_clears_unsupported_values() -> None:
    pages = _sample_pages()
    built = build_parser_layout_context(pages=pages, language="heb+eng")
    parsed = StructuredPayslipParse(
        overtime_hours=ExtractedField(
            value=549.30,
            confidence=0.9,
            source_text="54.93",
            status=FieldExtractionStatus.FOUND,
            evidence_ids=["p1_l2_w1"],
            source_page=1,
        ),
        net_salary=ExtractedField(
            value=7921.30,
            confidence=0.9,
            source_text="7,921.30",
            status=FieldExtractionStatus.FOUND,
            evidence_ids=["p1_l1_w1"],
            source_page=1,
        ),
    )
    validated = validate_structured_payslip_evidence(
        parsed,
        evidence_index=built.evidence_index,
        ocr_text=pages[0].text,
    )
    assert validated.overtime_hours.value is None
    assert validated.net_salary.value is None
