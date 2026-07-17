"""Amazon SES email delivery adapter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

import boto3
from botocore.exceptions import ClientError

from payroll_copilot.application.ports.email import (
    EmailAddress,
    EmailDeliveryError,
    EmailMessage,
    EmailSendResult,
    EmailService,
)

logger = logging.getLogger(__name__)


def _format_addresses(addresses: Sequence[EmailAddress]) -> list[str]:
    return [addr.formatted() for addr in addresses if addr.email and addr.email.strip()]


class SesEmailService(EmailService):
    """Send email via Amazon SES ``SendEmail`` (default credential chain / IAM)."""

    def __init__(
        self,
        *,
        region: str,
        from_email: str,
        from_name: str | None = None,
        configuration_set: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        if not from_email or not from_email.strip():
            raise ValueError("SES_FROM_EMAIL is required when using Amazon SES.")
        self._from = EmailAddress(email=from_email.strip(), name=(from_name or "").strip() or None)
        self._configuration_set = (configuration_set or "").strip() or None
        kwargs: dict[str, Any] = {"region_name": region.strip() or "us-east-1"}
        if endpoint_url and endpoint_url.strip():
            kwargs["endpoint_url"] = endpoint_url.strip()
        self._client = boto3.client("ses", **kwargs)
        self._region = kwargs["region_name"]

    async def send(self, message: EmailMessage) -> EmailSendResult:
        to_addresses = _format_addresses(message.to)
        if not to_addresses:
            raise EmailDeliveryError("EmailMessage.to must include at least one recipient.")
        if not (message.subject or "").strip():
            raise EmailDeliveryError("EmailMessage.subject is required.")
        if not (message.text_body or "").strip() and not (message.html_body or "").strip():
            raise EmailDeliveryError("EmailMessage requires text_body and/or html_body.")

        body: dict[str, Any] = {}
        if message.text_body:
            body["Text"] = {"Data": message.text_body, "Charset": "UTF-8"}
        if message.html_body:
            body["Html"] = {"Data": message.html_body, "Charset": "UTF-8"}

        destination: dict[str, Any] = {"ToAddresses": to_addresses}
        cc = _format_addresses(message.cc)
        bcc = _format_addresses(message.bcc)
        if cc:
            destination["CcAddresses"] = cc
        if bcc:
            destination["BccAddresses"] = bcc

        params: dict[str, Any] = {
            "Source": self._from.formatted(),
            "Destination": destination,
            "Message": {
                "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                "Body": body,
            },
        }
        reply_to = _format_addresses(message.reply_to)
        if reply_to:
            params["ReplyToAddresses"] = reply_to
        if self._configuration_set:
            params["ConfigurationSetName"] = self._configuration_set
        if message.tags:
            params["Tags"] = [
                {"Name": str(k)[:256], "Value": str(v)[:256]}
                for k, v in message.tags.items()
                if k and v is not None
            ]

        try:
            response = await asyncio.to_thread(self._client.send_email, **params)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "ClientError")
            detail = exc.response.get("Error", {}).get("Message", str(exc))
            logger.warning("SES send_email failed: %s — %s", code, detail)
            raise EmailDeliveryError(f"SES send failed ({code}): {detail}") from exc

        message_id = str(response.get("MessageId") or "")
        if not message_id:
            raise EmailDeliveryError("SES did not return a MessageId.")
        logger.info(
            "SES email sent message_id=%s region=%s to_count=%s",
            message_id,
            self._region,
            len(to_addresses),
        )
        return EmailSendResult(message_id=message_id, provider="ses")
