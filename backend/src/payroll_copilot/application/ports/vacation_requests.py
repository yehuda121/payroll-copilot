"""Vacation request persistence port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from payroll_copilot.domain.entities import VacationRequest


@dataclass(frozen=True, slots=True)
class VacationListFilter:
    organization_id: UUID
    bucket: str | None = None  # current|upcoming|past|pending_approval|requires_attention|approved
    range_start: date | None = None
    range_end: date | None = None
    employee_id: UUID | None = None
    query: str | None = None
    limit: int = 200
    offset: int = 0


class VacationRequestRepository(ABC):
    @abstractmethod
    async def get_by_id(
        self, organization_id: UUID, vacation_id: UUID
    ) -> VacationRequest | None: ...

    @abstractmethod
    async def get_by_provider_message(
        self,
        organization_id: UUID,
        *,
        provider: str,
        provider_message_id: str,
    ) -> VacationRequest | None: ...

    @abstractmethod
    async def list(self, filters: VacationListFilter) -> list[VacationRequest]: ...

    @abstractmethod
    async def list_for_employee(
        self, organization_id: UUID, employee_id: UUID
    ) -> list[VacationRequest]: ...

    @abstractmethod
    async def save(self, vacation: VacationRequest) -> VacationRequest: ...

    @abstractmethod
    async def create_inbound(
        self, vacation: VacationRequest
    ) -> tuple[VacationRequest, bool]:
        """Atomically create an inbound leave + idempotency marker.

        Returns ``(entity, created)``. When ``created`` is False, ``entity`` is the
        existing leave for the same org/provider/message (duplicate).
        """
        ...

    @abstractmethod
    async def delete(self, organization_id: UUID, vacation_id: UUID) -> None: ...

    @abstractmethod
    async def count_unseen(self, organization_id: UUID) -> int: ...

    @abstractmethod
    async def mark_seen(
        self,
        organization_id: UUID,
        *,
        vacation_ids: list[UUID] | None = None,
        seen_before: datetime | None = None,
        seen_at: datetime,
    ) -> int: ...
