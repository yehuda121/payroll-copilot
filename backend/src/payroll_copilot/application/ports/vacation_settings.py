"""Organization vacation settings, OTP, pipeline counters, integration credentials."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class VacationMailboxSettings:
    organization_id: UUID
    monitored_email_verified: str | None = None
    monitored_email_pending: str | None = None
    notification_email_verified: str | None = None
    notification_email_pending: str | None = None
    notify_on_new_vacation: bool = True
    notify_on_error_or_attention: bool = True
    notify_on_new_sick_leave: bool = True
    notify_on_sick_leave_error_or_attention: bool = True
    # Dual-gate: active monitored is verified AND connected.
    active_monitored_email: str | None = None
    pending_monitored_verified_at: datetime | None = None
    mailbox_connection_status: str = "disconnected"  # disconnected|ok|error
    mailbox_last_check_at: datetime | None = None
    mailbox_last_processed_at: datetime | None = None
    mailbox_last_processed_message_id: str | None = None
    mailbox_last_error_code: str | None = None
    mailbox_last_error_message: str | None = None
    updated_at: datetime | None = None


@dataclass
class EmailOwnershipOtp:
    organization_id: UUID
    purpose: str  # monitored | notification
    email: str
    code_hash: str
    expires_at: datetime
    attempts: int = 0
    max_attempts: int = 5
    created_at: datetime | None = None


@dataclass
class IntegrationCredential:
    id: UUID
    organization_id: UUID
    key_hash: str
    key_prefix: str
    label: str = "n8n"
    created_at: datetime | None = None
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None


class VacationSettingsRepository(ABC):
    @abstractmethod
    async def get(self, organization_id: UUID) -> VacationMailboxSettings: ...

    @abstractmethod
    async def save(self, settings: VacationMailboxSettings) -> VacationMailboxSettings: ...


class EmailOwnershipOtpRepository(ABC):
    @abstractmethod
    async def save(self, otp: EmailOwnershipOtp) -> None: ...

    @abstractmethod
    async def get(
        self, organization_id: UUID, *, purpose: str, email: str
    ) -> EmailOwnershipOtp | None: ...

    @abstractmethod
    async def delete(self, organization_id: UUID, *, purpose: str, email: str) -> None: ...


class VacationPipelineAnalyticsRepository(ABC):
    @abstractmethod
    async def increment(
        self,
        organization_id: UUID,
        *,
        day: str,
        event_type: str,
        amount: int = 1,
    ) -> None: ...

    @abstractmethod
    async def try_claim_event(
        self,
        organization_id: UUID,
        *,
        event_id: str,
        ttl_epoch: int,
    ) -> bool:
        """Return True if this event_id is new (claimed); False if duplicate."""

    @abstractmethod
    async def get_counters(
        self, organization_id: UUID, *, year: int
    ) -> dict[str, dict[str, int]]:
        """day -> {event_type: count} for days in year."""


class IntegrationCredentialRepository(ABC):
    @abstractmethod
    async def get_by_key_hash(self, key_hash: str) -> IntegrationCredential | None: ...

    @abstractmethod
    async def list_for_org(self, organization_id: UUID) -> list[IntegrationCredential]: ...

    @abstractmethod
    async def save(self, credential: IntegrationCredential) -> IntegrationCredential: ...

    @abstractmethod
    async def revoke(self, organization_id: UUID, credential_id: UUID) -> None: ...
