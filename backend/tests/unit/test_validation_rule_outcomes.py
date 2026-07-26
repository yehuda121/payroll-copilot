"""Orchestrator rule_outcomes are authoritative for PASS / skipped."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from payroll_copilot.application.validation.orchestrator import ValidationOrchestrator
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmploymentType, EmployeeStatus, RuleCategory, SalaryType
from payroll_copilot.domain.rules import LegalRulesBundle, ValidationContext, get_registered_rules
from payroll_copilot.domain.value_objects import Money, PayPeriod


def test_orchestrator_emits_rule_outcomes_for_registered_rules():
    emp = Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="1",
        first_name="A",
        last_name="B",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 1, 1),
        status=EmployeeStatus.ACTIVE,
    )
    ctx = ValidationContext(
        payslip=PayslipData(gross_salary=Money(Decimal("10000")), pension_employee=Money(Decimal("100"))),
        employee=emp,
        department=Department(
            id=emp.department_id,
            organization_id=emp.organization_id,
            code="x",
            name={"en": "x"},
            rule_profile="payroll",
        ),
        period=PayPeriod(year=2026, month=6),
        legal_rules=LegalRulesBundle(version="1", effective_from="2026-01-01", rules={}),
        authorized_employee=False,
    )
    report = ValidationOrchestrator().run(ctx)
    assert report.rule_outcomes
    assert len(report.rule_outcomes) == len(get_registered_rules())
    outcomes = {item.rule_id: item for item in report.rule_outcomes}
    employee_rules = [
        rid
        for rid, cls in get_registered_rules().items()
        if getattr(cls, "category", None) == RuleCategory.EMPLOYEE
    ]
    assert employee_rules
    sample = employee_rules[0]
    assert outcomes[sample].outcome == "skipped"
    assert outcomes[sample].skip_reason == "employee_not_identified"
    assert report.rules_evaluated == sum(
        1 for item in report.rule_outcomes if item.outcome in {"passed", "failed"}
    )
