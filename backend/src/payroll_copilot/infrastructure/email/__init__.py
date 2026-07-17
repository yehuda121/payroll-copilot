"""Outbound email infrastructure (Amazon SES)."""

from payroll_copilot.infrastructure.email.console_email import ConsoleEmailService
from payroll_copilot.infrastructure.email.factory import create_email_service, ses_configured
from payroll_copilot.infrastructure.email.ses_email import SesEmailService

__all__ = [
    "ConsoleEmailService",
    "SesEmailService",
    "create_email_service",
    "ses_configured",
]
