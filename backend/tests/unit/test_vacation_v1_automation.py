"""V1 email automation status derivation and health/OTP regressions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from payroll_copilot.application.ports.vacation_settings import (
    IntegrationCredential,
    VacationMailboxSettings,
)
from payroll_copilot.application.services.vacation_rules import derive_email_automation_status
from payroll_copilot.application.use_cases.manage_vacations import ManageVacationsUseCase
from payroll_copilot.domain.enums import EmailAutomationStatus
from payroll_copilot.presentation.api.routes.vacations import _serialize_settings

from tests.unit.test_vacation_manage import (
    FakeAudit,
    FakeEmail,
    FakeEmployees,
    FakeOtp,
    FakePipeline,
    FakeSettings,
    FakeVacations,
    _employee,
)


class FakeCredentials:
    def __init__(self, items: list[IntegrationCredential] | None = None) -> None:
        self.items = list(items or [])

    async def get_by_key_hash(self, key_hash: str):
        return next((c for c in self.items if c.key_hash == key_hash and c.revoked_at is None), None)

    async def list_for_org(self, organization_id: UUID):
        return [
            c
            for c in self.items
            if c.organization_id == organization_id and c.revoked_at is None
        ]

    async def save(self, credential: IntegrationCredential):
        self.items = [c for c in self.items if c.id != credential.id] + [credential]
        return credential

    async def revoke(self, organization_id: UUID, credential_id: UUID) -> None:
        for c in self.items:
            if c.organization_id == organization_id and c.id == credential_id:
                c.revoked_at = datetime.now(UTC)


def _cred(org: UUID, *, revoked: bool = False) -> IntegrationCredential:
    return IntegrationCredential(
        id=uuid4(),
        organization_id=org,
        key_hash="hash",
        key_prefix="pcn8n_xxxx",
        created_at=datetime.now(UTC),
        revoked_at=datetime.now(UTC) if revoked else None,
    )


@pytest.fixture
def org_id() -> UUID:
    return uuid4()


def test_status_not_configured_without_credential() -> None:
    settings = VacationMailboxSettings(organization_id=uuid4())
    assert (
        derive_email_automation_status(settings, has_active_credential=False)
        == EmailAutomationStatus.NOT_CONFIGURED.value
    )


def test_status_active() -> None:
    org = uuid4()
    settings = VacationMailboxSettings(
        organization_id=org,
        active_monitored_email="hr@example.com",
        mailbox_connection_status="ok",
    )
    assert (
        derive_email_automation_status(settings, has_active_credential=True)
        == EmailAutomationStatus.ACTIVE.value
    )


def test_status_error() -> None:
    settings = VacationMailboxSettings(
        organization_id=uuid4(),
        active_monitored_email="hr@example.com",
        mailbox_connection_status="error",
    )
    assert (
        derive_email_automation_status(settings, has_active_credential=True)
        == EmailAutomationStatus.ERROR.value
    )


def test_status_disconnected() -> None:
    settings = VacationMailboxSettings(
        organization_id=uuid4(),
        mailbox_connection_status="disconnected",
    )
    assert (
        derive_email_automation_status(settings, has_active_credential=True)
        == EmailAutomationStatus.DISCONNECTED.value
    )


@pytest.mark.asyncio
async def test_health_ok_sets_active_monitored_without_otp(org_id: UUID) -> None:
    manage = ManageVacationsUseCase(
        vacations=FakeVacations(),
        settings_repo=FakeSettings(org_id),
        otp_repo=FakeOtp(),
        pipeline=FakePipeline(),
        employees=FakeEmployees([_employee(org_id, "ada@example.com")]),
        audit=FakeAudit(),
        email=FakeEmail(),
        credentials=FakeCredentials([_cred(org_id)]),
    )
    updated = await manage.apply_mailbox_health(
        org_id,
        monitored_email="inbox@example.com",
        status="ok",
        checked_at=datetime.now(UTC),
        last_processed_at=None,
        last_processed_message_id=None,
        error_code=None,
        error_message=None,
    )
    assert updated.active_monitored_email == "inbox@example.com"
    assert await manage.email_automation_status(org_id) == EmailAutomationStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_monitored_otp_retired(org_id: UUID) -> None:
    manage = ManageVacationsUseCase(
        vacations=FakeVacations(),
        settings_repo=FakeSettings(org_id),
        otp_repo=FakeOtp(),
        pipeline=FakePipeline(),
        employees=FakeEmployees([]),
        audit=FakeAudit(),
        email=FakeEmail(),
        credentials=FakeCredentials(),
    )
    with pytest.raises(ValueError, match="monitored_otp_retired"):
        await manage.start_email_verification(
            org_id, purpose="monitored", email="x@example.com", actor_user_id=None
        )


@pytest.mark.asyncio
async def test_notification_otp_still_works(org_id: UUID) -> None:
    email = FakeEmail()
    manage = ManageVacationsUseCase(
        vacations=FakeVacations(),
        settings_repo=FakeSettings(org_id),
        otp_repo=FakeOtp(),
        pipeline=FakePipeline(),
        employees=FakeEmployees([]),
        audit=FakeAudit(),
        email=email,
        credentials=FakeCredentials(),
    )
    await manage.start_email_verification(
        org_id, purpose="notification", email="notify@example.com", actor_user_id=None
    )
    code = email.sent[-1].text_body.split("is: ")[1].split()[0]
    settings = await manage.confirm_email_verification(
        org_id,
        purpose="notification",
        email="notify@example.com",
        code=code,
        actor_user_id=None,
    )
    assert settings.notification_email_verified == "notify@example.com"


@pytest.mark.asyncio
async def test_mailbox_config_simplified(org_id: UUID) -> None:
    manage = ManageVacationsUseCase(
        vacations=FakeVacations(),
        settings_repo=FakeSettings(org_id),
        otp_repo=FakeOtp(),
        pipeline=FakePipeline(),
        employees=FakeEmployees([]),
        audit=FakeAudit(),
        email=FakeEmail(),
        credentials=FakeCredentials([_cred(org_id)]),
    )
    settings = await manage.get_settings(org_id)
    settings.notification_email_verified = "hr@example.com"
    await manage._settings.save(settings)
    payload = await manage.mailbox_config_for_n8n(settings)
    assert set(payload.keys()) == {
        "organization_id",
        "email_automation_status",
        "notification_email",
        "prefs",
    }
    assert "monitored_email" not in payload
    assert "ownership" not in payload


@pytest.mark.asyncio
async def test_settings_payload_includes_status_and_support(org_id: UUID) -> None:
    settings = VacationMailboxSettings(organization_id=org_id)
    payload = await _serialize_settings(
        settings, email_automation_status=EmailAutomationStatus.NOT_CONFIGURED.value
    )
    assert payload["email_automation_status"] == "not_configured"
    assert "support_contact" in payload
    assert "ownership_status" not in payload
