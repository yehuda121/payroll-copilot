"""Repository port interfaces for persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from payroll_copilot.application.dto.validation_run import ValidationFindingRecord, ValidationRunRecord
from payroll_copilot.domain.entities import Document, DocumentExtraction


class DocumentRepository(ABC):
    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> Document | None:
        ...

    @abstractmethod
    async def save(self, document: Document) -> Document:
        ...

    async def list_for_employee(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
    ) -> list[Document]:
        """Optional listing API — default empty for stubs; SQLAlchemy overrides."""
        raise NotImplementedError

    async def find_payslip_for_period(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        period_year: int,
        period_month: int,
    ) -> Document | None:
        """Find an existing payslip for employee+selected period if any."""
        raise NotImplementedError

    async def list_by_dataset_id(self, *, dataset_id: str) -> list[Document]:
        raise NotImplementedError

    async def delete_by_ids(self, document_ids: list[UUID]) -> int:
        raise NotImplementedError

class DocumentExtractionRepository(ABC):
    @abstractmethod
    async def get_by_id(self, extraction_id: UUID) -> DocumentExtraction | None:
        ...

    @abstractmethod
    async def get_latest_for_document(self, document_id: UUID) -> DocumentExtraction | None:
        ...

    @abstractmethod
    async def save(self, extraction: DocumentExtraction) -> DocumentExtraction:
        ...

    async def delete_for_document_ids(self, document_ids: list[UUID]) -> int:
        raise NotImplementedError


class ValidationRunRepository(ABC):
    @abstractmethod
    async def save(self, run: ValidationRunRecord) -> ValidationRunRecord:
        ...

    @abstractmethod
    async def get_by_id(self, run_id: UUID) -> ValidationRunRecord | None:
        ...

    async def list_latest_by_document_ids(
        self, document_ids: list[UUID]
    ) -> dict[UUID, ValidationRunRecord]:
        """Return the latest validation run per document_id (empty default for stubs)."""
        return {}

    async def list_for_document(self, document_id: UUID) -> list[ValidationRunRecord]:
        """Return validation runs for a document, newest first."""
        return []


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
