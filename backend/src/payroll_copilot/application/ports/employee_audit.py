"""Employee and audit persistence ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus


@dataclass(frozen=True, slots=True)
class EmployeeListFilter:
    organization_id: UUID
    query: str | None = None
    status: EmployeeStatus | None = None
    department_id: UUID | None = None
    include_disabled: bool = True
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    action: str
    resource_type: str
    resource_id: UUID | None = None
    organization_id: UUID | None = None
    user_id: UUID | None = None
    details: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class AuditLogRecord:
    id: int
    action: str
    resource_type: str
    resource_id: UUID | None
    organization_id: UUID | None
    user_id: UUID | None
    details: dict[str, Any]
    created_at: datetime


class EmployeeRepository(ABC):
    @abstractmethod
    async def get_by_id(self, employee_id: UUID) -> Employee | None: ...

    @abstractmethod
    async def get_by_number(self, organization_id: UUID, employee_number: str) -> Employee | None: ...

    @abstractmethod
    async def get_by_national_id_hash(
        self, organization_id: UUID, national_id_hash: str
    ) -> Employee | None: ...

    @abstractmethod
    async def list(self, filters: EmployeeListFilter) -> list[Employee]: ...

    @abstractmethod
    async def save(self, employee: Employee) -> Employee: ...

    async def save_with_national_id(
        self,
        employee: Employee,
        *,
        national_id_encrypted: bytes | None,
    ) -> Employee:
        """Persist employee and optional encrypted National ID. Default ignores NID bytes."""
        return await self.save(employee)

    async def get_national_id_encrypted(self, employee_id: UUID) -> bytes | None:
        """Return encrypted National ID bytes for server-side comparison only."""
        raise NotImplementedError

    async def list_by_dataset_id(self, *, dataset_id: str) -> list[Employee]:
        raise NotImplementedError

    async def delete_by_ids(self, employee_ids: list[UUID]) -> int:
        raise NotImplementedError


class AuditLogRepository(ABC):
    @abstractmethod
    async def append(self, entry: AuditLogEntry) -> AuditLogRecord: ...

    @abstractmethod
    async def list_recent(
        self,
        *,
        organization_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogRecord]: ...

    async def delete_by_dataset_id(self, *, dataset_id: str) -> int:
        raise NotImplementedError
