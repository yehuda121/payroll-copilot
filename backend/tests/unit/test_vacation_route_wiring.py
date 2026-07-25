"""Regression: vacation route factories must pass settings into create_email_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from payroll_copilot.application.ports.vacation_settings import VacationMailboxSettings
from payroll_copilot.infrastructure.email.factory import create_email_service
from payroll_copilot.presentation.api.routes import integrations, vacations
from payroll_copilot.presentation.api.routes.vacations import _serialize_settings


def _patch_dynamo_and_storage():
    return (
        patch(
            "payroll_copilot.infrastructure.storage.factory.create_object_storage",
            return_value=MagicMock(),
        ),
        patch(
            "payroll_copilot.infrastructure.persistence.dynamodb.get_vacation_request_repository",
            return_value=MagicMock(),
        ),
        patch(
            "payroll_copilot.infrastructure.persistence.dynamodb.get_vacation_settings_repository",
            return_value=MagicMock(),
        ),
        patch(
            "payroll_copilot.infrastructure.persistence.dynamodb.get_email_ownership_otp_repository",
            return_value=MagicMock(),
        ),
        patch(
            "payroll_copilot.infrastructure.persistence.dynamodb.get_vacation_pipeline_analytics_repository",
            return_value=MagicMock(),
        ),
        patch(
            "payroll_copilot.infrastructure.persistence.dynamodb.get_employee_repository",
            return_value=MagicMock(),
        ),
        patch(
            "payroll_copilot.infrastructure.persistence.dynamodb.get_audit_log_repository",
            return_value=MagicMock(),
        ),
        patch(
            "payroll_copilot.infrastructure.persistence.dynamodb.get_integration_credential_repository",
            return_value=MagicMock(),
        ),
    )


def test_create_email_service_rejects_missing_settings() -> None:
    try:
        create_email_service()  # type: ignore[call-arg]
        raise AssertionError("expected TypeError when settings omitted")
    except TypeError as exc:
        assert "settings" in str(exc)


def test_vacations_use_case_factory_passes_settings_to_email_service() -> None:
    email = MagicMock(name="email_service")
    patches = _patch_dynamo_and_storage()
    with (
        patch(
            "payroll_copilot.presentation.api.routes.vacations.create_email_service",
            return_value=email,
        ) as mocked,
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        uc = vacations._use_case()
        assert uc is not None
        mocked.assert_called_once()
        assert hasattr(mocked.call_args.args[0], "ses_from_email")


def test_integrations_use_case_factory_passes_settings_to_email_service() -> None:
    email = MagicMock(name="email_service")
    patches = _patch_dynamo_and_storage()
    with (
        patch(
            "payroll_copilot.presentation.api.routes.integrations.create_email_service",
            return_value=email,
        ) as mocked,
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        uc = integrations._use_case()
        assert uc is not None
        mocked.assert_called_once()
        assert len(mocked.call_args.args) == 1
        assert hasattr(mocked.call_args.args[0], "ses_from_email")


@pytest.mark.asyncio
async def test_vacation_settings_defaults_serialize_without_persisted_row() -> None:
    """Orgs without a VAC_SETTINGS item still produce a usable settings payload."""
    payload = await _serialize_settings(
        VacationMailboxSettings(organization_id=uuid4()),
        email_automation_status="not_configured",
    )
    assert payload["email_automation_status"] == "not_configured"
    assert payload["notify_on_new_vacation"] is True
    assert payload["active_monitored_email"] is None
