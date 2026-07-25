"""Employee update contract: email and national ID validation."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from payroll_copilot.application.use_cases.manage_employees import (
    CreateEmployeeCommand,
    EmployeeValidationError,
    ManageEmployeesUseCase,
    UpdateEmployeeCommand,
    serialize_employee,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id
from payroll_copilot.presentation.api.routes.employees import EmployeeUpdateRequest


ENCRYPTION_KEY = "test-employee-profile-encryption-key"


class _Employees:
    def __init__(self) -> None:
        self.by_number: dict[tuple, Employee] = {}
        self.by_nid_hash: dict[tuple, Employee] = {}
        self.encrypted: dict = {}

    async def get_by_id(self, employee_id):
        for emp in self.by_number.values():
            if emp.id == employee_id:
                return emp
        return None

    async def get_by_number(self, organization_id, employee_number):
        return self.by_number.get((organization_id, employee_number))

    async def get_by_national_id_hash(self, organization_id, national_id_hash):
        return self.by_nid_hash.get((organization_id, national_id_hash))

    async def list(self, filters):
        return [
            emp
            for (org, _), emp in self.by_number.items()
            if org == filters.organization_id
        ]

    async def save(self, employee):
        self.by_number[(employee.organization_id, employee.employee_number)] = employee
        return employee

    async def save_with_national_id(self, employee, *, national_id_encrypted):
        self.by_number[(employee.organization_id, employee.employee_number)] = employee
        nid_hash = (employee.metadata or {}).get("national_id_hash")
        if nid_hash:
            self.by_nid_hash[(employee.organization_id, nid_hash)] = employee
        if national_id_encrypted is not None:
            self.encrypted[employee.id] = national_id_encrypted
        return employee

    async def get_national_id_encrypted(self, employee_id):
        return self.encrypted.get(employee_id)


class _Audit:
    async def append(self, entry):
        return entry

    async def list_recent(self, **kwargs):
        return []


def _use_case(repo: _Employees | None = None) -> tuple[ManageEmployeesUseCase, _Employees]:
    employees = repo or _Employees()
    return ManageEmployeesUseCase(employees, _Audit(), encryption_key=ENCRYPTION_KEY), employees


@pytest.mark.asyncio
async def test_serialize_exposes_email_and_masked_national_id() -> None:
    emp = Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="E-1",
        first_name="Ada",
        last_name="Lovelace",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        metadata={
            "email": "ada@example.com",
            "national_id_masked": "****0018",
            "national_id_hash": "abc",
        },
    )
    payload = serialize_employee(emp)
    assert payload["email"] == "ada@example.com"
    assert payload["national_id_masked"] == "****0018"
    assert "national_id_hash" not in payload["metadata"]
    assert "national_id" not in payload


def test_employee_update_request_accepts_email() -> None:
    body = EmployeeUpdateRequest.model_validate(
        {
            "first_name": "Updated",
            "email": "new-address@example.com",
        }
    )
    assert body.email == "new-address@example.com"


def test_employee_update_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EmployeeUpdateRequest.model_validate({"not_a_field": 1})


@pytest.mark.asyncio
async def test_update_email_normalizes_and_persists() -> None:
    uc, repo = _use_case()
    org = uuid4()
    created = await uc.create(
        CreateEmployeeCommand(
            organization_id=org,
            employee_number="E-1",
            first_name="Ada",
            last_name="Lovelace",
            department_id=uuid4(),
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2024, 1, 1),
            email="Ada@Example.COM",
        )
    )
    assert created["email"] == "ada@example.com"

    updated = await uc.update(
        UpdateEmployeeCommand(
            organization_id=org,
            employee_number="E-1",
            email="  New.Person@Example.COM ",
        )
    )
    assert updated["email"] == "new.person@example.com"
    stored = await repo.get_by_number(org, "E-1")
    assert stored is not None
    assert stored.metadata["email"] == "new.person@example.com"


@pytest.mark.asyncio
async def test_update_rejects_invalid_email() -> None:
    uc, _ = _use_case()
    org = uuid4()
    await uc.create(
        CreateEmployeeCommand(
            organization_id=org,
            employee_number="E-1",
            first_name="Ada",
            last_name="Lovelace",
            department_id=uuid4(),
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2024, 1, 1),
            email="ada@example.com",
        )
    )
    with pytest.raises(EmployeeValidationError) as exc:
        await uc.update(
            UpdateEmployeeCommand(
                organization_id=org,
                employee_number="E-1",
                email="not-an-email",
            )
        )
    assert exc.value.code == "invalid_email"
    assert "not-an-email" not in exc.value.message


@pytest.mark.asyncio
async def test_update_national_id_and_reject_invalid() -> None:
    uc, repo = _use_case()
    org = uuid4()
    await uc.create(
        CreateEmployeeCommand(
            organization_id=org,
            employee_number="E-1",
            first_name="Ada",
            last_name="Lovelace",
            department_id=uuid4(),
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2024, 1, 1),
        )
    )
    updated = await uc.update(
        UpdateEmployeeCommand(
            organization_id=org,
            employee_number="E-1",
            national_id="313366783",
        )
    )
    assert updated["national_id_masked"] == "****6783"
    stored = await repo.get_by_number(org, "E-1")
    assert stored is not None
    assert "national_id" not in (stored.metadata or {})

    with pytest.raises(EmployeeValidationError) as exc:
        await uc.update(
            UpdateEmployeeCommand(
                organization_id=org,
                employee_number="E-1",
                national_id="123456789",
            )
        )
    assert exc.value.code == "national_id_checksum"
    assert "123456789" not in exc.value.message

    with pytest.raises(EmployeeValidationError) as exc_len:
        await uc.update(
            UpdateEmployeeCommand(
                organization_id=org,
                employee_number="E-1",
                national_id="12345",
            )
        )
    assert exc_len.value.code == "national_id_length"


@pytest.mark.asyncio
async def test_national_id_leading_zero_preserved() -> None:
    uc, repo = _use_case()
    org = uuid4()
    await uc.create(
        CreateEmployeeCommand(
            organization_id=org,
            employee_number="E-1",
            first_name="Ada",
            last_name="Lovelace",
            department_id=uuid4(),
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2024, 1, 1),
            national_id="000000018",
        )
    )
    employee = await repo.get_by_number(org, "E-1")
    assert employee is not None
    encrypted = await repo.get_national_id_encrypted(employee.id)
    plaintext = decrypt_national_id(encrypted, encryption_key=ENCRYPTION_KEY)
    assert plaintext == "000000018"
    assert (employee.metadata or {}).get("national_id_masked") == "****0018"


@pytest.mark.asyncio
async def test_partial_update_preserves_unrelated_fields() -> None:
    uc, _ = _use_case()
    org = uuid4()
    dept = uuid4()
    await uc.create(
        CreateEmployeeCommand(
            organization_id=org,
            employee_number="E-1",
            first_name="Ada",
            last_name="Lovelace",
            department_id=dept,
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2024, 1, 1),
            email="ada@example.com",
            national_id="313366783",
            metadata={"department_label": "Engineering"},
        )
    )
    updated = await uc.update(
        UpdateEmployeeCommand(
            organization_id=org,
            employee_number="E-1",
            first_name="Augusta",
        )
    )
    assert updated["first_name"] == "Augusta"
    assert updated["last_name"] == "Lovelace"
    assert updated["email"] == "ada@example.com"
    assert updated["national_id_masked"] == "****6783"
    assert updated["metadata"]["department_label"] == "Engineering"
    assert updated["employment_type"] == EmploymentType.FULL_TIME.value


@pytest.mark.asyncio
async def test_update_is_scoped_to_organization() -> None:
    uc, _ = _use_case()
    org_a = uuid4()
    org_b = uuid4()
    await uc.create(
        CreateEmployeeCommand(
            organization_id=org_a,
            employee_number="E-1",
            first_name="Ada",
            last_name="Lovelace",
            department_id=uuid4(),
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2024, 1, 1),
            email="ada@example.com",
        )
    )
    from payroll_copilot.application.use_cases.manage_employees import EmployeeNotFoundError

    with pytest.raises(EmployeeNotFoundError):
        await uc.update(
            UpdateEmployeeCommand(
                organization_id=org_b,
                employee_number="E-1",
                email="other@example.com",
            )
        )
