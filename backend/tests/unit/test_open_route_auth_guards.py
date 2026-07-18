"""Regression coverage for previously unauthenticated audit/validation reads."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.domain.enums import UserRole, ValidationRunStatus
from payroll_copilot.presentation.api.routes.validation import (
    _authorize_validation_run_access,
)
from payroll_copilot.presentation.api.security import AuthPrincipal


@pytest.mark.asyncio
async def test_validation_run_access_rejects_cross_tenant_accountant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    foreign_organization_id = uuid4()
    document_id = uuid4()
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=foreign_organization_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=1,
        rules_failed=0,
    )
    document = SimpleNamespace(
        id=document_id,
        organization_id=foreign_organization_id,
        employee_id=uuid4(),
        metadata={"publication_status": "published"},
    )

    class _Documents:
        async def get_by_id(self, _document_id):
            return document

    monkeypatch.setattr(
        "payroll_copilot.presentation.api.routes.validation.get_document_repository",
        lambda: _Documents(),
    )

    with pytest.raises(HTTPException) as exc:
        await _authorize_validation_run_access(
            record=run,
            principal=AuthPrincipal(
                user_id=uuid4(),
                role=UserRole.ACCOUNTANT.value,
                organization_id=organization_id,
                employee_id=None,
            ),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_validation_run_access_hides_unpublished_employee_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=organization_id,
        employee_id=employee_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=1,
        rules_failed=0,
    )
    document = SimpleNamespace(
        id=document_id,
        organization_id=organization_id,
        employee_id=employee_id,
        metadata={
            "source": "accountant_bulk_upload",
            "publication_status": "draft",
        },
    )

    class _Documents:
        async def get_by_id(self, _document_id):
            return document

    monkeypatch.setattr(
        "payroll_copilot.presentation.api.routes.validation.get_document_repository",
        lambda: _Documents(),
    )

    with pytest.raises(HTTPException) as exc:
        await _authorize_validation_run_access(
            record=run,
            principal=AuthPrincipal(
                user_id=uuid4(),
                role=UserRole.EMPLOYEE.value,
                organization_id=organization_id,
                employee_id=employee_id,
            ),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_validation_run_access_allows_same_org_accountant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization_id = uuid4()
    document_id = uuid4()
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=organization_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=1,
        rules_failed=0,
    )
    document = SimpleNamespace(
        id=document_id,
        organization_id=organization_id,
        employee_id=uuid4(),
        metadata={"publication_status": "draft"},
    )

    class _Documents:
        async def get_by_id(self, _document_id):
            return document

    monkeypatch.setattr(
        "payroll_copilot.presentation.api.routes.validation.get_document_repository",
        lambda: _Documents(),
    )

    await _authorize_validation_run_access(
        record=run,
        principal=AuthPrincipal(
            user_id=uuid4(),
            role=UserRole.ACCOUNTANT.value,
            organization_id=organization_id,
            employee_id=None,
        ),
    )
