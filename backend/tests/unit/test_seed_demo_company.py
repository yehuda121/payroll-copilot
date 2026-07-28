"""Unit tests for demo company factory and seed use-case guards."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from payroll_copilot.application.ports.employee_audit import EmployeeListFilter
from payroll_copilot.application.services.demo_company_factory import (
    DATASET_ID,
    all_demo_profiles,
    build_contract_structured,
    build_payslip_structured,
    payslip_months_through_today,
)
from payroll_copilot.application.services.employee_fixed_document_extractor import (
    is_valid_israeli_id,
)
from payroll_copilot.application.use_cases.seed_accountant_portal import (
    SeedProductionBlockedError,
    assert_seed_environment_allowed,
)
from payroll_copilot.application.use_cases.seed_demo_company import SeedDemoCompanyUseCase
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.domain.seed_ids import DEMO_ORGANIZATION_ID


def test_demo_profiles_have_valid_israeli_ids() -> None:
    for profile in all_demo_profiles():
        assert is_valid_israeli_id(profile.national_id)
        assert profile.first_name
        assert profile.last_name


def test_payslip_months_never_include_future(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date(2026, 7, 24)
    months = payslip_months_through_today(today=today)
    assert months[0] == (2026, 1)
    assert months[-1] == (2026, 7)
    assert len(months) == 7
    assert all(m <= 7 for _, m in months)


def test_payslip_values_are_internally_consistent() -> None:
    profile = all_demo_profiles()[0]
    structured = build_payslip_structured(
        profile,
        employee_id=profile.employee_id,
        year=2026,
        month=6,
    )
    gross = Decimal(str(structured["gross_salary"]["value"]))
    net = Decimal(str(structured["net_salary"]["value"]))
    assert net <= gross
    contract = build_contract_structured(profile)
    additional = contract["additional_fields"]
    assert additional["salary_basis"]["value"] == "monthly"
    assert additional["contractual_monthly_salary"]["status"] == "FOUND"


def test_production_env_blocked() -> None:
    with pytest.raises(SeedProductionBlockedError):
        assert_seed_environment_allowed("production")


class _Employees:
    def __init__(self, rows: list[Employee]) -> None:
        self.rows = rows
        self.saved: list[Employee] = []

    async def list(self, filters: EmployeeListFilter) -> list[Employee]:
        return list(self.rows)

    async def get_by_number(self, organization_id, employee_number):
        return next((e for e in self.rows if e.employee_number == employee_number), None)

    async def get_by_national_id_hash(self, organization_id, national_id_hash):
        return None

    async def save_with_national_id(self, employee, *, national_id_encrypted):
        self.saved.append(employee)
        self.rows.append(employee)
        return employee

    async def get_national_id_encrypted(self, employee_id):
        return b"enc"


class _Docs:
    def __init__(self) -> None:
        self.saved = []
        self.by_period = {}

    async def list_for_employee(self, *, organization_id, employee_id):
        return [doc for doc in self.saved if doc.employee_id == employee_id]

    async def find_payslip_for_period(
        self, *, organization_id, employee_id, period_year, period_month
    ):
        return self.by_period.get((employee_id, period_year, period_month))

    async def save(self, document):
        self.saved.append(document)
        if document.period is not None:
            self.by_period[(document.employee_id, document.period.year, document.period.month)] = (
                document
            )
        return document


class _Extractions:
    def __init__(self) -> None:
        self.saved = []

    async def save(self, extraction):
        self.saved.append(extraction)
        return extraction


class _Workspace:
    async def ensure_organization(self, organization_id, *, name="Organization"):
        return organization_id

    async def ensure_default_department(self, organization_id):
        return uuid4()


class _Validation:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, command):
        self.calls += 1
        return object()


@pytest.mark.asyncio
async def test_seed_tops_up_to_ten_and_skips_duplicate_months() -> None:
    existing = [
        Employee(
            id=uuid4(),
            organization_id=DEMO_ORGANIZATION_ID,
            employee_number=f"EXIST-{i}",
            first_name="קיים",
            last_name=str(i),
            department_id=uuid4(),
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2024, 1, 1),
            status=EmployeeStatus.ACTIVE,
            monthly_salary=Decimal("9000"),
        )
        for i in range(3)
    ]
    employees = _Employees(existing)
    docs = _Docs()
    extractions = _Extractions()
    validation = _Validation()
    use_case = SeedDemoCompanyUseCase(
        employees=employees,  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        extractions=extractions,  # type: ignore[arg-type]
        workspace=_Workspace(),  # type: ignore[arg-type]
        encryption_key="test-key-32-bytes-long!!!!!!!!",
        app_env="development",
        validation=validation,  # type: ignore[arg-type]
        employee_validation=None,
        target_employees=10,
        today=date(2026, 3, 15),
    )
    result = await use_case.execute(dry_run=False)
    assert result.dataset_id == DATASET_ID
    assert result.employees_created == 7
    assert result.employees_total == 10
    assert result.months == ["2026-01", "2026-02", "2026-03"]
    # 10 employees × 3 months
    assert result.payslips_created == 30
    assert validation.calls == 30
    assert result.validations_failed == 0

    # Second run: no duplicates
    result2 = await use_case.execute(dry_run=False)
    assert result2.employees_created == 0
    assert result2.payslips_created == 0
    assert result2.identity_docs_created == 0
    assert result2.contract_docs_created == 0
