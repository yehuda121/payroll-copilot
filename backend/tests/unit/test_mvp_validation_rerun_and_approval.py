"""Selective rerun scope + manual approval unit tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import payroll_copilot.domain.rules.contract  # noqa: F401
import payroll_copilot.domain.rules.employee  # noqa: F401
import payroll_copilot.domain.rules.legal  # noqa: F401
import payroll_copilot.domain.rules.sanity  # noqa: F401
from payroll_copilot.application.services.legal_parameter_resolver import resolve_parameters_as_of
from payroll_copilot.application.services.validation_rerun_scope import disabled_rule_ids_for_scope
from payroll_copilot.application.use_cases.approve_validation_finding import apply_approvals_to_display
from payroll_copilot.domain.rules import LegalRuleConfig, get_registered_rules
from payroll_copilot.domain.enums import FindingSeverity


def test_employee_checks_scope_excludes_law() -> None:
    disabled = disabled_rule_ids_for_scope(scope="employee_checks")
    assert "legal.minimum_wage" in disabled
    assert "employee.national_id.match" not in disabled
    assert "contract.employment_commencement_date.match" not in disabled


def test_law_checks_scope_excludes_employee() -> None:
    disabled = disabled_rule_ids_for_scope(scope="law_checks")
    assert "employee.national_id.match" in disabled
    assert "legal.minimum_wage" not in disabled


def test_single_rule_scope() -> None:
    disabled = disabled_rule_ids_for_scope(
        scope="rules",
        rule_ids=frozenset({"legal.minimum_wage"}),
    )
    assert "legal.minimum_wage" not in disabled
    assert "employee.name.match" in disabled


def test_full_scope_disables_nothing() -> None:
    assert disabled_rule_ids_for_scope(scope="full") == frozenset()


def test_legal_parameter_schedule_as_of() -> None:
    cfg = LegalRuleConfig(
        rule_id="legal.minimum_wage",
        description={},
        parameters={
            "amount": 32.11,
            "schedule": [
                {"effective_from": "2024-04-01", "amount": 32.11},
                {"effective_from": "2026-01-01", "amount": 32.11},
            ],
        },
        legal_reference={},
        severity=FindingSeverity.CRITICAL,
    )
    params = resolve_parameters_as_of(cfg, as_of=date(2026, 6, 1))
    assert Decimal(str(params["amount"])) == Decimal("32.11")


def test_manual_approval_display_preserves_severity() -> None:
    findings = [
        {
            "id": "f1",
            "rule_id": "contract.hourly_rate.match",
            "severity": "warning",
        }
    ]
    approvals = [
        {
            "finding_id": "f1",
            "rule_id": "contract.hourly_rate.match",
            "original_severity": "warning",
        }
    ]
    annotated = apply_approvals_to_display(findings=findings, approvals=approvals)
    assert annotated[0]["severity"] == "warning"
    assert annotated[0]["display_status"] == "manually_approved"


def test_pension_rule_deferred_not_applicable() -> None:
    cls = get_registered_rules()["legal.pension.contribution"]
    # applies_to always False — deferred complex/ambiguous base
    from payroll_copilot.domain.entities import Department, Employee, PayslipData
    from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
    from payroll_copilot.domain.rules import LegalRulesBundle, ValidationContext
    from payroll_copilot.domain.value_objects import Money, PayPeriod

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
    )
    assert cls().applies_to(ctx) is False
