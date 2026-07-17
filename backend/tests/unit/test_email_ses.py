"""Unit tests for email delivery factory and console adapter."""

from __future__ import annotations

import pytest

from payroll_copilot.application.ports.email import EmailAddress, EmailMessage
from payroll_copilot.infrastructure.email.console_email import ConsoleEmailService
from payroll_copilot.infrastructure.email.factory import create_email_service, ses_configured
from payroll_copilot.infrastructure.email.ses_email import SesEmailService


class _FakeSettings:
    def __init__(self, *, from_email: str = "", region: str = "us-east-1") -> None:
        self.ses_from_email = from_email
        self.ses_from_name = "Payroll Copilot"
        self.ses_region = region
        self.ses_configuration_set = ""
        self.ses_endpoint = ""


def test_ses_configured_requires_from_email() -> None:
    assert ses_configured(_FakeSettings(from_email="")) is False
    assert ses_configured(_FakeSettings(from_email="noreply@example.com")) is True


def test_factory_uses_console_when_ses_unconfigured() -> None:
    service = create_email_service(_FakeSettings(from_email=""))
    assert isinstance(service, ConsoleEmailService)


def test_factory_uses_ses_when_from_email_set() -> None:
    service = create_email_service(_FakeSettings(from_email="noreply@example.com"))
    assert isinstance(service, SesEmailService)


@pytest.mark.asyncio
async def test_console_email_send_returns_message_id() -> None:
    service = ConsoleEmailService()
    result = await service.send(
        EmailMessage(
            to=[EmailAddress(email="user@example.com")],
            subject="Hello",
            text_body="Body",
        )
    )
    assert result.provider == "console"
    assert result.message_id.startswith("console-")
