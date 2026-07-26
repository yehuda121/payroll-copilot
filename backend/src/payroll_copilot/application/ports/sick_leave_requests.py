"""Sick leave request persistence port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from payroll_copilot.domain.entities import SickLeaveRequest


@dataclass(frozen=True, slots=True)
class SickLeaveListFilter:
    organization_id: UUID
    bucket: str | None = None  # current|upcoming|past|pending_approval|requires_attention|approved
    range_start: date | None = None
    range_end: date | None = None
    employee_id: UUID | None = None
    query: str | None = None
    limit: int = 200
    offset: int = 0


class SickLeaveRequestRepository(ABC):
    @abstractmethod
    async def get_by_id(
        self, organization_id: UUID, sick_leave_id: UUID
    ) -> SickLeaveRequest | None: ...

    @abstractmethod
    async def get_by_provider_message(
        self,
        organization_id: UUID,
        *,
        provider: str,
        provider_message_id: str,
    ) -> SickLeaveRequest | None: ...

    @abstractmethod
    async def list(self, filters: SickLeaveListFilter) -> list[SickLeaveRequest]: ...

    @abstractmethod
    async def list_for_employee(
        self, organization_id: UUID, employee_id: UUID
    ) -> list[SickLeaveRequest]: ...

    @abstractmethod
    async def save(self, vacation: SickLeaveRequest) -> SickLeaveRequest: ...

    @abstractmethod
    async def create_inbound(
        self, sick_leave: SickLeaveRequest
    ) -> tuple[SickLeaveRequest, bool]:
        """Atomically create an inbound leave + idempotency marker.

        Returns ``(entity, created)``. When ``created`` is False, ``entity`` is the
        existing leave for the same org/provider/message (duplicate).
        """
        ...

    @abstractmethod
    async def delete(self, organization_id: UUID, sick_leave_id: UUID) -> None: ...

    @abstractmethod
    async def count_unseen(self, organization_id: UUID) -> int: ...

    @abstractmethod
    async def mark_seen(
        self,
        organization_id: UUID,
        *,
        sick_leave_ids: list[UUID] | None = None,
        seen_before: datetime | None = None,
        seen_at: datetime,
    ) -> int: ...
