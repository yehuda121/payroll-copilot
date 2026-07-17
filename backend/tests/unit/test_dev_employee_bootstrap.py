"""Dev employee bootstrap creates the bound employee record."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from payroll_copilot.domain.dev_employee_binding import (
    DEMO_ORGANIZATION_ID,
    DEV_EMPLOYEE_NUMBER,
    get_dev_bound_employee_id,
)
from payroll_copilot.domain.enums import EmployeeStatus
from payroll_copilot.presentation.api import security


@pytest.mark.asyncio
async def test_ensure_dev_employee_creates_missing_employee(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    employee_id = get_dev_bound_employee_id()
    saved: list = []

    class FakeEmployees:
        async def get_by_id(self, _id):
            return None

        async def save_with_national_id(self, employee, *, national_id_encrypted):
            saved.append((employee, national_id_encrypted))
            return employee

    class FakeUsers:
        async def get_by_id(self, _id):
            return None

        async def save(self, user):
            return user

    class FakeBootstrap:
        async def ensure_default_department(self, organization_id):
            assert organization_id == DEMO_ORGANIZATION_ID
            return uuid4()

    monkeypatch.setattr(security, "get_employee_repository", lambda: FakeEmployees())
    monkeypatch.setattr(security, "get_user_store", lambda: FakeUsers())
    monkeypatch.setattr(security, "get_workspace_bootstrap", lambda: FakeBootstrap())
    monkeypatch.setattr(security, "cognito_configured", lambda _settings: False)
    settings = MagicMock()
    settings.app_env = "development"
    settings.encryption_key = "0" * 64
    monkeypatch.setattr(security, "get_settings", lambda: settings)

    user = await security.ensure_dev_employee_user()
    assert user.employee_id == employee_id
    assert len(saved) == 1
    employee, encrypted = saved[0]
    assert employee.id == employee_id
    assert employee.employee_number == DEV_EMPLOYEE_NUMBER
    assert employee.status == EmployeeStatus.ACTIVE
    assert encrypted
