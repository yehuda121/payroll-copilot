"""Document upload and retrieval use cases."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.repositories import DocumentRepository
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DEMO_ORGANIZATION_ID,
)
from payroll_copilot.domain.entities import Document
from payroll_copilot.domain.enums import DocumentStatus, DocumentType
from payroll_copilot.domain.value_objects import PayPeriod


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    content: bytes
    original_filename: str
    mime_type: str
    document_type: DocumentType
    employee_id: UUID | None = None
    period_year: int | None = None
    period_month: int | None = None
    uploaded_by_user_id: UUID | None = None


class UploadDocumentUseCase:
    """Upload a document to object storage and persist its metadata to PostgreSQL."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        object_storage: ObjectStoragePort,
        organization_bootstrap: OrganizationBootstrapPort,
    ) -> None:
        self._document_repository = document_repository
        self._object_storage = object_storage
        self._organization_bootstrap = organization_bootstrap

    async def execute(self, command: UploadDocumentCommand) -> Document:
        document_id = uuid4()
        checksum = hashlib.sha256(command.content).hexdigest()
        storage_key = f"documents/{document_id}/{command.original_filename or 'upload'}"

        await self._object_storage.upload(storage_key, command.content, command.mime_type)
        await self._organization_bootstrap.ensure_demo_organization(DEMO_ORGANIZATION_ID)

        period = None
        if command.period_year is not None and command.period_month is not None:
            period = PayPeriod(year=command.period_year, month=command.period_month)

        document = Document(
            id=document_id,
            document_type=command.document_type,
            storage_key=storage_key,
            original_filename=command.original_filename or "upload",
            mime_type=command.mime_type,
            file_size_bytes=len(command.content),
            checksum_sha256=checksum,
            status=DocumentStatus.UPLOADED,
            organization_id=DEMO_ORGANIZATION_ID,
            uploaded_by=command.uploaded_by_user_id,
            employee_id=command.employee_id,
            period=period,
            metadata={},
        )
        return await self._document_repository.save(document)


class GetDocumentUseCase:
    """Load a persisted document by ID."""

    def __init__(self, document_repository: DocumentRepository) -> None:
        self._document_repository = document_repository

    async def execute(self, document_id: UUID) -> Document | None:
        return await self._document_repository.get_by_id(document_id)
