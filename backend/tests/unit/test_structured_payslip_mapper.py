"""Unit tests for structured payslip → validation mapper."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from payroll_copilot.application.ports.payslip_parser import FieldExtractionStatus
from payroll_copilot.application.validation.structured_payslip_mapper import (
    coerce_money,
    map_structured_payslip_to_validation_inputs,
)


def _field(value, *, status="FOUND", confidence=0.9, edited=False, original=None):
    return {
        "value": value,
        "confidence": confidence,
        "source_text": str(value) if value is not None else None,
        "status": status,
        "edited_by_user": edited,
        "original_value": original,
    }


def test_coerce_money_common_strings() -> None:
    money = coerce_money("₪12,345.50")
    assert money is not None
    assert money.amount == Decimal("12345.50")
    assert money.currency == "ILS"
    assert coerce_money("-10") is None
    assert coerce_money("not-a-number") is None


def test_maps_aliases_and_keeps_balances_additional() -> None:
    document_id = uuid4()
    mapped = map_structured_payslip_to_validation_inputs(
        document_id=document_id,
        structured_data={
            "employee_name": _field("Dana Levi"),
            "employee_number": _field("9988"),
            "pay_period": _field("2026-06"),
            "base_salary": _field("10000"),
            "gross_salary": _field("12000"),
            "net_salary": _field("9000"),
            "regular_hours": _field("160"),
            "income_tax": _field("1500"),
            "travel_expenses": _field("220"),
            "vacation_balance": _field("12"),
            "sick_leave_balance": _field("5"),
            "pension_employee": _field("720"),
        },
        parser_completed=True,
    )
    payslip = mapped.command.payslip
    assert payslip.work_hours == Decimal("160")
    assert payslip.transportation_allowance is not None
    assert payslip.transportation_allowance.amount == Decimal("220")
    assert payslip.tax_deducted is not None
    assert payslip.tax_deducted.amount == Decimal("1500")
    assert "vacation_days_used" not in (payslip.additional_fields or {})
    assert payslip.additional_fields.get("vacation_balance") == 12 or payslip.additional_fields.get(
        "vacation_balance"
    ) == "12"
    assert mapped.extraction_connected is True
    assert mapped.core_fields_usable is True
    assert mapped.command.department.rule_profile == "payroll"
    assert mapped.command.employee.metadata.get("guest_synthetic") is True
    assert mapped.command.employee.metadata.get("age") is None


def test_missing_and_invalid_money_are_unavailable() -> None:
    mapped = map_structured_payslip_to_validation_inputs(
        document_id=uuid4(),
        structured_data={
            "gross_salary": _field(None, status="MISSING", confidence=None),
            "base_salary": _field("-500", status="FOUND"),
            "income_tax": _field("abc", status="FOUND"),
            "pension_employee": _field(None, status="MISSING", confidence=None),
            "regular_hours": _field(None, status="MISSING", confidence=None),
        },
        parser_completed=True,
    )
    payslip = mapped.command.payslip
    assert payslip.gross_salary is None
    assert payslip.base_salary is None
    assert payslip.tax_deducted is None
    assert mapped.core_fields_usable is False


def test_uncertain_caps_confidence_user_edit_sets_one() -> None:
    mapped = map_structured_payslip_to_validation_inputs(
        document_id=uuid4(),
        structured_data={
            "employee_name": _field("Ada", status="UNCERTAIN", confidence=0.92),
            "gross_salary": _field("10000", status="FOUND", confidence=0.8, edited=True, original="9000"),
            "base_salary": _field("9000"),
            "net_salary": _field("7000"),
            "regular_hours": _field("160"),
        },
        parser_completed=True,
    )
    conf = mapped.command.field_confidences
    assert conf["employee_name"] <= 0.55
    assert conf["gross_salary"] == 1.0


def test_parser_incomplete_not_extraction_connected() -> None:
    mapped = map_structured_payslip_to_validation_inputs(
        document_id=uuid4(),
        structured_data={"gross_salary": _field("10000")},
        parser_completed=False,
    )
    assert mapped.extraction_connected is False
