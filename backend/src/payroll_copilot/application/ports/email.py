"""Email delivery port — outbound notifications (Amazon SES in production)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True, slots=True)
class EmailAddress:
    email: str
    name: str | None = None

    def formatted(self) -> str:
        address = self.email.strip()
        if self.name and self.name.strip():
            return f"{self.name.strip()} <{address}>"
        return address


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """Outbound email payload. Callers never depend on SES-specific types."""

    to: Sequence[EmailAddress]
    subject: str
    text_body: str
    html_body: str | None = None
    cc: Sequence[EmailAddress] = field(default_factory=tuple)
    bcc: Sequence[EmailAddress] = field(default_factory=tuple)
    reply_to: Sequence[EmailAddress] = field(default_factory=tuple)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    message_id: str
    provider: str


class EmailDeliveryError(Exception):
    """Raised when the email provider rejects or fails a send."""


class EmailService(ABC):
    """Outbound email delivery abstraction.

    Production: Amazon SES. Local/dev: console logger when SES is not configured.
    """

    @abstractmethod
    async def send(self, message: EmailMessage) -> EmailSendResult:
        ...
