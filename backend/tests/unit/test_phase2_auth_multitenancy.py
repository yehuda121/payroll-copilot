"""Phase 2+3 authentication and multi-tenancy unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from payroll_copilot.application.use_cases.manage_employees import _sanitize_employee_metadata_patch
from payroll_copilot.infrastructure.auth.cognito import (
    employee_id_from_cognito_claims,
    organization_id_from_cognito_claims,
)
from payroll_copilot.infrastructure.config.org_resolution import (
    OrganizationBindingRequiredError,
    allow_demo_organization_fallback,
    resolve_organization_id,
)
from payroll_copilot.presentation.api.security import upsert_user_from_cognito_claims


def test_organization_id_from_cognito_claims_reads_custom_attribute() -> None:
    org_id = uuid4()
    assert organization_id_from_cognito_claims({"custom:organization_id": str(org_id)}) == org_id


def test_employee_id_from_cognito_claims_reads_custom_attribute() -> None:
    employee_id = uuid4()
    assert employee_id_from_cognito_claims({"custom:employee_id": str(employee_id)}) == employee_id


def test_resolve_organization_id_requires_explicit_value_in_production() -> None:
    settings = SimpleNamespace(
        app_env="production",
        cognito_user_pool_id="pool",
        cognito_app_client_id="client",
    )
    assert not allow_demo_organization_fallback(settings)
    with pytest.raises(OrganizationBindingRequiredError):
        resolve_organization_id(None, settings=settings)


def test_resolve_organization_id_allows_demo_in_local_dev_without_cognito() -> None:
    settings = SimpleNamespace(
        app_env="development",
        cognito_user_pool_id="",
        cognito_app_client_id="",
    )
    org_id = resolve_organization_id(None, settings=settings)
    assert org_id == UUID("00000000-0000-4000-8000-000000000001")


def test_sanitize_employee_metadata_patch_strips_reserved_keys() -> None:
    sanitized = _sanitize_employee_metadata_patch(
        {
            "email": "hacker@example.com",
            "national_id": "123",
            "national_id_hash": "abc",
            "organization_id": str(uuid4()),
            "display_name_en": "Allowed",
        }
    )
    assert sanitized == {"display_name_en": "Allowed"}


@pytest.mark.asyncio
async def test_upsert_user_from_cognito_claims_rejects_missing_org_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        app_env="production",
        cognito_user_pool_id="pool",
        cognito_app_client_id="",
    )

    class _Store:
        async def get_by_id(self, _user_id):
            return None

        async def save(self, user):
            return user

    monkeypatch.setattr(
        "payroll_copilot.presentation.api.security.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.security.cognito_configured",
        lambda _settings=None: True,
    )
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.security.allow_demo_organization_fallback",
        lambda _settings=None: False,
    )
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.security.get_user_store",
        lambda: _Store(),
    )

    with pytest.raises(HTTPException) as exc:
        await upsert_user_from_cognito_claims(
            {"sub": str(uuid4()), "email": "user@example.com"},
        )
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "organization_binding_missing"
