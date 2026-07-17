"""Factory for the outbound email delivery adapter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from payroll_copilot.application.ports.email import EmailService
from payroll_copilot.infrastructure.email.console_email import ConsoleEmailService
from payroll_copilot.infrastructure.email.ses_email import SesEmailService

if TYPE_CHECKING:
    from payroll_copilot.infrastructure.config.settings import Settings

logger = logging.getLogger(__name__)


def ses_configured(settings: Settings) -> bool:
    """True when SES can send (verified from-address configured)."""
    return bool((settings.ses_from_email or "").strip())


def create_email_service(settings: Settings) -> EmailService:
    """Build the email adapter from settings.

    - ``SES_FROM_EMAIL`` set → Amazon SES (IAM / default credentials).
    - Otherwise → console logger (local/dev; no outbound mail).
    """
    if ses_configured(settings):
        endpoint = (settings.ses_endpoint or "").strip() or None
        logger.info(
            "Email delivery: provider=ses region=%s from=%s endpoint=%s",
            settings.ses_region,
            settings.ses_from_email,
            endpoint or "aws",
        )
        return SesEmailService(
            region=settings.ses_region.strip() or "us-east-1",
            from_email=settings.ses_from_email.strip(),
            from_name=(settings.ses_from_name or "").strip() or None,
            configuration_set=(settings.ses_configuration_set or "").strip() or None,
            endpoint_url=endpoint,
        )

    logger.info("Email delivery: provider=console (SES_FROM_EMAIL not set)")
    return ConsoleEmailService()
