"""Unit tests for semantic extraction plausibility / quality gates."""

from __future__ import annotations

from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.parser_evidence import (
    apply_plausibility_checks,
    employee_name_implausible_reason,
)


def _parse(**overrides: ExtractedField) -> StructuredPayslipParse:
    data = StructuredPayslipParse().model_dump()
    for key, field in overrides.items():
        data[key] = field.model_dump()
    return StructuredPayslipParse.model_validate(data)


def test_implausible_numeric_employee_name_becomes_uncertain():
    original = "5"
    parsed = _parse(
        employee_name=ExtractedField(
            value=original,
            status=FieldExtractionStatus.FOUND,
            confidence=0.95,
            source_text=original,
        )
    )
    result = apply_plausibility_checks(parsed)
    assert result.employee_name.value == original
    assert result.employee_name.status == FieldExtractionStatus.UNCERTAIN
    assert result.employee_name.confidence is None
    assert "implausible_employee_name_numeric_only" in result.employee_name.warnings


def test_implausible_single_letter_employee_name_becomes_uncertain():
    original = "A"
    parsed = _parse(
        employee_name=ExtractedField(
            value=original,
            status=FieldExtractionStatus.FOUND,
            confidence=0.88,
            source_text=original,
        )
    )
    result = apply_plausibility_checks(parsed)
    assert result.employee_name.value == original
    assert result.employee_name.status == FieldExtractionStatus.UNCERTAIN
    assert result.employee_name.confidence is None
    assert "implausible_employee_name_too_short" in result.employee_name.warnings


def test_hebrew_single_letter_employee_name_becomes_uncertain():
    original = "י"
    assert employee_name_implausible_reason(original) == "implausible_employee_name_too_short"
    result = apply_plausibility_checks(
        _parse(
            employee_name=ExtractedField(
                value=original,
                status=FieldExtractionStatus.FOUND,
                confidence=0.9,
            )
        )
    )
    assert result.employee_name.value == original
    assert result.employee_name.status == FieldExtractionStatus.UNCERTAIN


def test_plausible_employee_name_unchanged():
    original = "יהודה שמולביץ"
    parsed = _parse(
        employee_name=ExtractedField(
            value=original,
            status=FieldExtractionStatus.FOUND,
            confidence=0.91,
            source_text=original,
        )
    )
    result = apply_plausibility_checks(parsed)
    assert result.employee_name.value == original
    assert result.employee_name.status == FieldExtractionStatus.FOUND
    assert result.employee_name.confidence == 0.91
    assert result.employee_name.warnings == []
    assert result.employee_name.trust_tier is not None


def test_semantic_gate_never_invents_replacement_name():
    garbage = "313366783"
    result = apply_plausibility_checks(
        _parse(
            employee_name=ExtractedField(
                value=garbage,
                status=FieldExtractionStatus.FOUND,
                confidence=0.99,
            )
        )
    )
    assert result.employee_name.value == garbage
    assert result.employee_name.status == FieldExtractionStatus.UNCERTAIN
    assert result.employee_name.confidence is None
