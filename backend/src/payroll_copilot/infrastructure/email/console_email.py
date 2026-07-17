"""Local/dev email adapter — logs messages instead of sending."""

from __future__ import annotations

import logging
import uuid

from payroll_copilot.application.ports.email import (
    EmailDeliveryError,
    EmailMessage,
    EmailSendResult,
    EmailService,
)

logger = logging.getLogger(__name__)


class ConsoleEmailService(EmailService):
    """No-op sender for local development when SES is not configured."""

    async def send(self, message: EmailMessage) -> EmailSendResult:
        if not message.to:
            raise EmailDeliveryError("EmailMessage.to must include at least one recipient.")
        message_id = f"console-{uuid.uuid4()}"
        recipients = ", ".join(addr.email for addr in message.to)
        logger.info(
            "Console email (not sent via SES) id=%s to=%s subject=%r",
            message_id,
            recipients,
            message.subject,
        )
        if message.text_body:
            logger.debug("Console email text body:\n%s", message.text_body[:2000])
        return EmailSendResult(message_id=message_id, provider="console")
