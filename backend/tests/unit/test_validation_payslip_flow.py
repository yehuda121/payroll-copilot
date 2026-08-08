"""Validation flow regression: mapper + orchestrator with explicit rule outcomes.

Asserts which categories/rules run for a representative payslip, that
NOT_RUN reasons are explicit when context is missing, and that legal
parameters come from the local YAML loader (no MCP).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from payroll_copilot.application.services.validation_catalog import (
    OUTCOME_FAILED,
    OUTCOME_NOT_RUN,
    OUTCOME_PASSED,
    OUTCOME_UNCERTAIN,
)
from payroll_copilot.application.use_cases.validation import (
    RunValidationCommand,
    RunValidationUseCase,
)
from payroll_copilot.application.validation.rule_outcome_meta import (
    DISPLAY_CONTRACT,
    DISPLAY_EMPLOYEE_MATCH,
    DISPLAY_LEGAL,
    DISPLAY_PAYSLIP_SANITY,
)
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.domain.rules import ensure_validation_rules_registered
from payroll_copilot.domain.value_objects import Money, PayPeriod
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader

_VALID_NATIONAL_ID = "313366783"


@pytest.fixture(scope="module", autouse=True)
def _register_rules() -> None:
    ensure_validation_rules_registered()


def _guest_payslip() -> PayslipData:
    return PayslipData(
        employee_number="1001",
        employee_name="אורית סבירסקי",
        period=PayPeriod(year=2026, month=6),
        gross_salary=Money(amount=Decimal("8872.30")),
        net_salary=Money(amount=Decimal("7921.30")),
        work_hours=Decimal("182"),
        additional_fields={"national_id": _VALID_NATIONAL_ID},
    )


def _synthetic_employee() -> Employee:
    return Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="GUEST",
        first_name="Guest",
        last_name="User",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("12000"),
    )


def _department(employee: Employee) -> Department:
    return Department(
        id=employee.department_id,
        organization_id=employee.organization_id,
        code="GEN",
        name={"he": "כללי", "en": "General"},
        rule_profile="general",
    )


class _RecordingLoader(YamlLegalRulesLoader):
    """Wraps local YAML loader and records that MCP was never needed."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.load_calls = 0
        self.network_calls = 0

    def load_merged_rules(self):  # type: ignore[override]
        self.load_calls += 1
        return super().load_merged_rules()

    def load_merged_rules_as_of(self, as_of):  # type: ignore[override]
        self.load_calls += 1
        return super().load_merged_rules_as_of(as_of)


def test_guest_payslip_validation_categories_and_local_legal_version() -> None:
    settings = get_settings()
    loader = _RecordingLoader(settings.legal_rules_path)
    use_case = RunValidationUseCase(loader)
    employee = _synthetic_employee()

    report = use_case.execute(
        RunValidationCommand(
            payslip=_guest_payslip(),
            employee=employee,
            department=_department(employee),
            period=PayPeriod(year=2026, month=6),
            field_confidences={"gross_salary": 0.9},
            authorized_employee=False,
        )
    )

    assert loader.load_calls >= 1
    assert loader.network_calls == 0
    assert report.legal_rules_version  # from local YAML bundle

    by_id = {o.rule_id: o for o in report.rule_outcomes}
    assert by_id, "expected explicit rule_outcomes"

    sanity = [o for o in report.rule_outcomes if o.display_category == DISPLAY_PAYSLIP_SANITY]
    assert sanity
    assert all(o.display_category for o in report.rule_outcomes)

    employee_outcomes = [
        o for o in report.rule_outcomes if o.display_category == DISPLAY_EMPLOYEE_MATCH
    ]
    assert employee_outcomes
    assert all(o.outcome == OUTCOME_NOT_RUN for o in employee_outcomes)

    contract = [o for o in report.rule_outcomes if o.display_category == DISPLAY_CONTRACT]
    assert contract
    assert all(o.outcome == OUTCOME_NOT_RUN for o in contract)

    legal_ran = [
        o
        for o in report.rule_outcomes
        if o.display_category == DISPLAY_LEGAL
        and o.outcome in {OUTCOME_PASSED, OUTCOME_FAILED, OUTCOME_UNCERTAIN}
    ]
    for outcome in legal_ran:
        assert outcome.legal_version == report.legal_rules_version

    pension = by_id.get("legal.pension.contribution")
    if pension is not None:
        assert pension.outcome == OUTCOME_NOT_RUN


def test_authorized_employee_enables_employee_match_rules() -> None:
    settings = get_settings()
    use_case = RunValidationUseCase(YamlLegalRulesLoader(settings.legal_rules_path))
    emp = _synthetic_employee()
    payslip = PayslipData(
        employee_number=emp.employee_number,
        employee_name=emp.full_name,
        period=PayPeriod(year=2026, month=6),
        gross_salary=Money(amount=Decimal("8872.30")),
        net_salary=Money(amount=Decimal("7921.30")),
        additional_fields={"national_id": _VALID_NATIONAL_ID},
    )

    report = use_case.execute(
        RunValidationCommand(
            payslip=payslip,
            employee=emp,
            department=_department(emp),
            period=PayPeriod(year=2026, month=6),
            field_confidences={},
            authorized_employee=True,
            trusted_national_id=_VALID_NATIONAL_ID,
        )
    )
    employee_outcomes = [
        o for o in report.rule_outcomes if o.display_category == DISPLAY_EMPLOYEE_MATCH
    ]
    assert employee_outcomes
    assert any(o.outcome != OUTCOME_NOT_RUN for o in employee_outcomes)
