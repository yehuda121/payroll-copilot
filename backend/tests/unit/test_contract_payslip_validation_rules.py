"""CONTRACT payslip validation against confirmed employment terms."""

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
from payroll_copilot.domain.employment_terms import (
    ConfirmedEmploymentTerms,
    select_terms_for_period,
)
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.domain.rules import get_registered_rules
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
        salary_type=SalaryType.HOURLY,
        contract_start_date=date.today(),  # overloaded — must NEVER be compared
        status=EmployeeStatus.ACTIVE,
        hourly_rate=Decimal("50"),
        monthly_salary=Decimal("15000"),
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
    terms: ConfirmedEmploymentTerms | None,
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
            confirmed_employment_terms=terms,
        )
    )


def _ids(report: object) -> set[str]:
    return {f.rule_id for f in report.findings}  # type: ignore[attr-defined]


class TestContractRulesRegistered:
    def test_agreement_rules_registered(self) -> None:
        registered = get_registered_rules()
        assert "contract.employment_commencement_date.match" in registered
        assert "contract.hourly_rate.match" in registered
        assert "contract.salary_basis.match" in registered


class TestEmploymentCommencement:
    def test_match(self, rules_loader, employee, department) -> None:
        terms = ConfirmedEmploymentTerms(employment_commencement_date=date(2018, 5, 1))
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_start_date": "2018-05-01"}),
            employee=employee,
            department=department,
            authorized=True,
            terms=terms,
        )
        assert "contract.employment_commencement_date.match" not in _ids(report)

    def test_mismatch(self, rules_loader, employee, department) -> None:
        terms = ConfirmedEmploymentTerms(employment_commencement_date=date(2018, 5, 1))
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_start_date": "2020-01-01"}),
            employee=employee,
            department=department,
            authorized=True,
            terms=terms,
        )
        assert "contract.employment_commencement_date.match" in _ids(report)

    def test_no_confirmed_terms_no_finding(self, rules_loader, employee, department) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_start_date": "2010-01-01"}),
            employee=employee,
            department=department,
            authorized=True,
            terms=None,
        )
        assert "contract.employment_commencement_date.match" not in _ids(report)

    def test_profile_contract_start_date_never_used(self, rules_loader, employee, department) -> None:
        # employee.contract_start_date is today; payslip differs — still no profile-based finding
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_start_date": "2010-01-01"}),
            employee=employee,
            department=department,
            authorized=True,
            terms=None,
        )
        assert "employee.employment_start_date.match" not in _ids(report)
        assert "contract.employment_commencement_date.match" not in _ids(report)

    def test_guest_skips_contract(self, rules_loader, employee, department) -> None:
        terms = ConfirmedEmploymentTerms(employment_commencement_date=date(2018, 5, 1))
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_start_date": "2020-01-01"}),
            employee=employee,
            department=department,
            authorized=False,
            terms=terms,
        )
        assert not any(rid.startswith("contract.") for rid in _ids(report))


class TestHourlyRateAndBasis:
    def test_hourly_match(self, rules_loader, employee, department) -> None:
        terms = ConfirmedEmploymentTerms(
            salary_basis="hourly",
            contractual_hourly_rate=Decimal("50.00"),
        )
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"hourly_rate": "50.00", "salary_basis": "hourly"}),
            employee=employee,
            department=department,
            authorized=True,
            terms=terms,
        )
        assert "contract.hourly_rate.match" not in _ids(report)
        assert "contract.salary_basis.match" not in _ids(report)

    def test_hourly_mismatch(self, rules_loader, employee, department) -> None:
        terms = ConfirmedEmploymentTerms(
            salary_basis="hourly",
            contractual_hourly_rate=Decimal("50.00"),
        )
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"hourly_rate": "40.00"}),
            employee=employee,
            department=department,
            authorized=True,
            terms=terms,
        )
        assert "contract.hourly_rate.match" in _ids(report)


class TestEffectiveDatingSelection:
    def test_selects_overlapping_version(self) -> None:
        older = ConfirmedEmploymentTerms(
            contractual_hourly_rate=Decimal("40"),
            salary_basis="hourly",
            effective_from=date(2020, 1, 1),
            effective_to=date(2024, 12, 31),
        )
        newer = ConfirmedEmploymentTerms(
            contractual_hourly_rate=Decimal("50"),
            salary_basis="hourly",
            effective_from=date(2025, 1, 1),
        )
        selected = select_terms_for_period([older, newer], year=2026, month=6)
        assert selected is newer

    def test_ambiguous_overlap_returns_none(self) -> None:
        a = ConfirmedEmploymentTerms(
            employment_commencement_date=date(2010, 1, 1),
            effective_from=date(2020, 1, 1),
        )
        b = ConfirmedEmploymentTerms(
            employment_commencement_date=date(2010, 1, 1),
            effective_from=date(2019, 1, 1),
        )
        assert select_terms_for_period([a, b], year=2026, month=1) is None

    def test_never_naive_latest_undated_multi(self) -> None:
        a = ConfirmedEmploymentTerms(employment_commencement_date=date(2010, 1, 1))
        b = ConfirmedEmploymentTerms(employment_commencement_date=date(2011, 1, 1))
        assert select_terms_for_period([a, b], year=2026, month=1) is None
