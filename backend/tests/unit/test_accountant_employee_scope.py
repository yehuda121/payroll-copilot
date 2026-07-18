from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from payroll_copilot.domain.enums import UserRole
from payroll_copilot.presentation.api import security
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    bind_accountant_selected_employee,
)


class _Employees:
    def __init__(self, organization_id):
        self.organization_id = organization_id
        self.requested_organization_id = None

    async def get_by_number(self, organization_id, employee_number):
        self.requested_organization_id = organization_id
        if organization_id != self.organization_id or employee_number != "E-1":
            return None
        return SimpleNamespace(id=uuid4(), organization_id=organization_id)

    async def get_national_id_encrypted(self, _employee_id):
        return b"encrypted"


@pytest.mark.asyncio
async def test_accountant_selected_employee_is_resolved_inside_principal_org(monkeypatch) -> None:
    organization_id = uuid4()
    employees = _Employees(organization_id)
    monkeypatch.setattr(security, "get_employee_repository", lambda: employees)
    principal = AuthPrincipal(
        user_id=uuid4(),
        role=UserRole.ACCOUNTANT.value,
        organization_id=organization_id,
        employee_id=None,
    )

    selected = await bind_accountant_selected_employee(
        employee_number="E-1",
        principal=principal,
    )

    assert selected.employee.organization_id == organization_id
    assert employees.requested_organization_id == organization_id


@pytest.mark.asyncio
async def test_accountant_selected_employee_hides_foreign_or_missing_employee(monkeypatch) -> None:
    principal_org = uuid4()
    employees = _Employees(uuid4())
    monkeypatch.setattr(security, "get_employee_repository", lambda: employees)
    principal = AuthPrincipal(
        user_id=uuid4(),
        role=UserRole.ACCOUNTANT.value,
        organization_id=principal_org,
        employee_id=None,
    )

    with pytest.raises(HTTPException) as exc:
        await bind_accountant_selected_employee(
            employee_number="E-1",
            principal=principal,
        )

    assert exc.value.status_code == 404
    assert employees.requested_organization_id == principal_org
