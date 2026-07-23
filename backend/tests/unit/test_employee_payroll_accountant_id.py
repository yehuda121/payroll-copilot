"""Tests for optional Employee.payroll_accountant_id persistence."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from payroll_copilot.application.use_cases.manage_employees import serialize_employee
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.infrastructure.persistence.dynamodb.employees import (
    DynamoEmployeeRepository,
)


def _employee(**overrides: object) -> Employee:
    base = dict(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="E-100",
        first_name="Noa",
        last_name="Levi",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        payroll_accountant_id=None,
    )
    base.update(overrides)
    return Employee(**base)  # type: ignore[arg-type]


def test_payroll_accountant_id_defaults_to_none() -> None:
    employee = _employee()
    assert employee.payroll_accountant_id is None
    payload = serialize_employee(employee)
    assert payload["payroll_accountant_id"] is None


def test_payroll_accountant_id_round_trips_dynamo_item() -> None:
    accountant_id = uuid4()
    employee = _employee(payroll_accountant_id=accountant_id)
    repo = DynamoEmployeeRepository(table=object())  # type: ignore[arg-type]
    item = repo._to_item(employee, national_id_encrypted=None)
    assert item["payroll_accountant_id"] == str(accountant_id)
    restored = repo._to_entity(item)
    assert restored.payroll_accountant_id == accountant_id
    assert serialize_employee(restored)["payroll_accountant_id"] == str(accountant_id)


def test_legacy_dynamo_item_without_field_loads_as_none() -> None:
    employee = _employee()
    repo = DynamoEmployeeRepository(table=object())  # type: ignore[arg-type]
    item = repo._to_item(employee, national_id_encrypted=None)
    item.pop("payroll_accountant_id", None)
    restored = repo._to_entity(item)
    assert restored.payroll_accountant_id is None
