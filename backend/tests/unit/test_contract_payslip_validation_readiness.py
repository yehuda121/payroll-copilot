"""CONTRACT readiness regressions — confirmed terms only; never profile dates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

import payroll_copilot.domain.rules.contract  # noqa: F401
import payroll_copilot.domain.rules.departments  # noqa: F401
import payroll_copilot.domain.rules.employee  # noqa: F401
import payroll_copilot.domain.rules.historical  # noqa: F401
import payroll_copilot.domain.rules.legal  # noqa: F401
import payroll_copilot.domain.rules.sanity  # noqa: F401
from payroll_copilot.application.use_cases.validation import RunValidationCommand, RunValidationUseCase
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.domain.value_objects import Money, PayPeriod
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader

_VALID_NATIONAL_ID = "313366783"


@pytest.fixture
def rules_loader() -> YamlLegalRulesLoader:
    return YamlLegalRulesLoader("config/rules/labor_law")


@pytest.fixture
def employee() -> Employee:
    return Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="E-1001",
        first_name="Dana",
        last_name="Cohen",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date.today(),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("15000"),
        hourly_rate=Decimal("50"),
        metadata={"created_at": "2026-07-24T10:00:00Z"},
    )


@pytest.fixture
def department(employee: Employee) -> Department:
    return Department(
        id=employee.department_id,
        organization_id=employee.organization_id,
        code="payroll",
        name={"he": "שכר", "en": "Payroll"},
        rule_profile="payroll",
    )


def _run(
    rules_loader: YamlLegalRulesLoader,
    *,
    payslip: PayslipData,
    employee: Employee,
    department: Department,
    authorized: bool,
) -> object:
    return RunValidationUseCase(rules_loader).execute(
        RunValidationCommand(
            payslip=payslip,
            employee=employee,
            department=department,
            period=payslip.period or PayPeriod(year=2026, month=6),
            field_confidences={},
            authorized_employee=authorized,
            trusted_national_id=_VALID_NATIONAL_ID if authorized else None,
            selected_period_year=2026,
            selected_period_month=6,
            confirmed_employment_terms=None,
        )
    )


def _ids(report: object) -> set[str]:
    return {f.rule_id for f in report.findings}  # type: ignore[attr-defined]


class TestWithoutConfirmedTerms:
    def test_profile_salary_not_compared_as_contract(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        payslip = PayslipData(
            period=PayPeriod(year=2026, month=6),
            gross_salary=Money(amount=Decimal("9999"), currency="ILS"),
            base_salary=Money(amount=Decimal("8000"), currency="ILS"),
            additional_fields={
                "national_id": _VALID_NATIONAL_ID,
                "employment_start_date": "2010-01-01",
                "employment_scope": "50",
                "hourly_rate": "80",
                "seniority_years": "5",
                "salary_mode": "hourly",
            },
        )
        report = _run(
            rules_loader,
            payslip=payslip,
            employee=employee,
            department=department,
            authorized=True,
        )
        assert "contract.hourly_rate.match" not in _ids(report)
        assert "contract.employment_commencement_date.match" not in _ids(report)
        assert "employee.employment_start_date.match" not in _ids(report)

    def test_guest_without_contract_does_not_fail_contract_rules(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(
                period=PayPeriod(year=2026, month=6),
                additional_fields={"employment_start_date": "2010-01-01"},
            ),
            employee=employee,
            department=department,
            authorized=False,
        )
        assert not any(rid.startswith("contract.") for rid in _ids(report))
        assert not any(rid.startswith("employee.") for rid in _ids(report))
