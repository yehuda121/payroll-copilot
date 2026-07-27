"""Missing/unparseable pay_period must not invent today's legal as_of."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import payroll_copilot.domain.rules.contract  # noqa: F401
import payroll_copilot.domain.rules.employee  # noqa: F401
import payroll_copilot.domain.rules.legal  # noqa: F401
import payroll_copilot.domain.rules.sanity  # noqa: F401
from payroll_copilot.application.services.validation_catalog import (
    OUTCOME_NOT_RUN,
    OUTCOME_PASSED,
    OUTCOME_UNCERTAIN,
    REASON_MISSING_PAY_PERIOD,
    REASON_RULE_NOT_READY,
)
from payroll_copilot.application.use_cases.validation import RunValidationCommand, RunValidationUseCase
from payroll_copilot.application.validation.orchestrator import ValidationOrchestrator
from payroll_copilot.application.validation.structured_payslip_mapper import (
    map_structured_payslip_to_validation_inputs,
)
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.domain.rules import LegalRuleConfig, LegalRulesBundle, ValidationContext
from payroll_copilot.domain.enums import FindingSeverity
from payroll_copilot.domain.value_objects import Money, PayPeriod
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader


def _field(value, *, status="FOUND", confidence=0.9):
    return {
        "value": value,
        "confidence": confidence,
        "source_text": str(value) if value is not None else None,
        "status": status,
        "edited_by_user": False,
        "original_value": None,
    }


def test_known_pay_period_maps_to_command_period() -> None:
    mapped = map_structured_payslip_to_validation_inputs(
        document_id=uuid4(),
        structured_data={
            "pay_period": _field("2020-01"),
            "hourly_rate": _field("40"),
            "salary_calculation_basis": _field("hourly"),
            "employee_name": _field("Dana"),
            "national_id": _field("313366783"),
        },
    )
    assert mapped.command.period == PayPeriod(year=2020, month=1)
    assert mapped.command.payslip.period == PayPeriod(year=2020, month=1)
    assert "pay_period_missing" not in mapped.mapping_warnings


def test_missing_pay_period_does_not_invent_today() -> None:
    today = date.today()
    mapped = map_structured_payslip_to_validation_inputs(
        document_id=uuid4(),
        structured_data={
            "pay_period": _field(None, status="MISSING", confidence=None),
            "hourly_rate": _field("40"),
            "salary_calculation_basis": _field("hourly"),
            "employee_name": _field("Dana"),
            "national_id": _field("313366783"),
            "gross_salary": _field("10000"),
        },
    )
    assert mapped.command.period is None
    assert mapped.command.payslip.period is None
    assert "pay_period_missing" in mapped.mapping_warnings
    assert mapped.command.period != PayPeriod(year=today.year, month=today.month)


def test_invalid_pay_period_does_not_invent_today() -> None:
    today = date.today()
    mapped = map_structured_payslip_to_validation_inputs(
        document_id=uuid4(),
        structured_data={
            "pay_period": _field("not-a-period"),
            "hourly_rate": _field("40"),
            "salary_calculation_basis": _field("hourly"),
        },
    )
    assert mapped.command.period is None
    assert "pay_period_unparseable" in mapped.mapping_warnings
    assert mapped.command.period != PayPeriod(year=today.year, month=today.month)


def test_missing_period_legal_rules_not_run_without_today_law() -> None:
    emp = Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="1",
        first_name="A",
        last_name="B",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.HOURLY,
        contract_start_date=date(1970, 1, 1),
        status=EmployeeStatus.ACTIVE,
        hourly_rate=Decimal("40"),
    )
    ctx = ValidationContext(
        payslip=PayslipData(
            employee_name="Dana",
            overtime_hours=Decimal("1"),
            additional_fields={
                "hourly_rate": "40",
                "salary_calculation_basis": "hourly",
                "national_id": "313366783",
            },
            period=None,
        ),
        employee=emp,
        department=Department(
            id=emp.department_id,
            organization_id=emp.organization_id,
            code="x",
            name={"en": "x"},
            rule_profile="payroll",
        ),
        period=None,
        legal_rules=LegalRulesBundle(
            version="1",
            effective_from="2026-01-01",
            rules={
                "minimum_wage_hourly": LegalRuleConfig(
                    rule_id="legal.minimum_wage",
                    description={"en": "min"},
                    parameters={"amount": 32.11},
                    legal_reference={"he": "x"},
                    severity=FindingSeverity.CRITICAL,
                ),
                "daily_overtime_limit": LegalRuleConfig(
                    rule_id="legal.overtime.daily_limit",
                    description={"en": "ot"},
                    parameters={"max_hours": 2},
                    legal_reference={"he": "x"},
                    severity=FindingSeverity.WARNING,
                ),
            },
        ),
        authorized_employee=True,
        trusted_national_id="313366783",
        selected_period_year=2020,
        selected_period_month=1,
        field_confidences={"hourly_rate": 0.9, "overtime_hours": 0.9, "national_id": 0.9},
    )
    report = ValidationOrchestrator().run(ctx)
    outcomes = {item.rule_id: item for item in report.rule_outcomes}
    assert outcomes["legal.minimum_wage"].outcome == OUTCOME_NOT_RUN
    assert outcomes["legal.minimum_wage"].reason_code == REASON_MISSING_PAY_PERIOD
    assert outcomes["legal.overtime.daily_limit"].outcome == OUTCOME_NOT_RUN
    assert outcomes["legal.overtime.daily_limit"].reason_code == REASON_MISSING_PAY_PERIOD
    # Unrelated identity check can still execute when authorized.
    assert outcomes["employee.national_id.match"].outcome in {
        OUTCOME_PASSED,
        OUTCOME_UNCERTAIN,
    }
    assert outcomes["legal.overtime.weekly_limit"].reason_code == REASON_RULE_NOT_READY


def test_run_validation_use_case_skips_as_of_when_period_none(tmp_path) -> None:
    """as_of must not become today when command.period is None."""
    loader = YamlLegalRulesLoader("config/rules/labor_law")
    use_case = RunValidationUseCase(loader)
    emp = Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="1",
        first_name="A",
        last_name="B",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(1970, 1, 1),
        status=EmployeeStatus.ACTIVE,
    )
    report = use_case.execute(
        RunValidationCommand(
            payslip=PayslipData(gross_salary=Money(Decimal("10000")), period=None),
            employee=emp,
            department=Department(
                id=emp.department_id,
                organization_id=emp.organization_id,
                code="x",
                name={"en": "x"},
                rule_profile="payroll",
            ),
            period=None,
            field_confidences={},
            authorized_employee=False,
        )
    )
    outcomes = {item.rule_id: item for item in report.rule_outcomes}
    assert outcomes["legal.minimum_wage"].outcome == OUTCOME_NOT_RUN
    assert outcomes["legal.minimum_wage"].reason_code in {
        REASON_MISSING_PAY_PERIOD,
        REASON_RULE_NOT_READY,
        "NOT_APPLICABLE",
    }
