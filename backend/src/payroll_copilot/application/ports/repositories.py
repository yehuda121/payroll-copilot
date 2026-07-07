"""Repository port interfaces for persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from payroll_copilot.application.dto.validation_run import ValidationFindingRecord, ValidationRunRecord
from payroll_copilot.domain.entities import Document


class DocumentRepository(ABC):
    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> Document | None:
        ...

    @abstractmethod
    async def save(self, document: Document) -> Document:
        ...


class ValidationRunRepository(ABC):
    @abstractmethod
    async def save(self, run: ValidationRunRecord) -> ValidationRunRecord:
        ...

    @abstractmethod
    async def get_by_id(self, run_id: UUID) -> ValidationRunRecord | None:
        ...


class ValidationFindingRepository(ABC):
    @abstractmethod
    async def save_all(
        self,
        run_id: UUID,
        findings: list[ValidationFindingRecord],
    ) -> list[ValidationFindingRecord]:
        ...

    @abstractmethod
    async def list_by_run_id(self, run_id: UUID) -> list[ValidationFindingRecord]:
        ...
