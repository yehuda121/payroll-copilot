"""Delete employee-owned documents with scoped modes."""

from __future__ import annotations

import logging
from dataclasses import replace
from enum import StrEnum
from uuid import UUID

from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    is_employee_visible_document,
)
from payroll_copilot.domain.entities import Document

logger = logging.getLogger(__name__)


class DocumentDeleteScope(StrEnum):
    ORIGINAL = "original"
    DIGITAL = "digital"
    BOTH = "both"


class DocumentDeleteError(Exception):
    """Base error for scoped document delete."""


class DocumentDeleteNotFoundError(DocumentDeleteError):
    def __init__(self, document_id: UUID) -> None:
        super().__init__(f"Document not found: {document_id}")
        self.document_id = document_id


class DocumentDeleteConflictError(DocumentDeleteError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class DeleteEmployeeDocumentUseCase:
    """Single delete path with scope=original|digital|both."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        storage: ObjectStoragePort,
        validation_runs: object | None = None,
    ) -> None:
        self._documents = documents
        self._extractions = extractions
        self._storage = storage
        self._validation_runs = validation_runs

    async def execute(
        self,
        *,
        document_id: UUID,
        organization_id: UUID,
        employee_id: UUID,
        scope: DocumentDeleteScope,
        require_employee_visible: bool = False,
    ) -> dict:
        document = await self._documents.get_by_id(document_id)
        if (
            document is None
            or document.employee_id != employee_id
            or document.organization_id != organization_id
        ):
            raise DocumentDeleteNotFoundError(document_id)
        if require_employee_visible and not is_employee_visible_document(document):
            raise DocumentDeleteNotFoundError(document_id)

        deleted_original = False
        deleted_digital = False
        document_removed = False

        if scope in {DocumentDeleteScope.DIGITAL, DocumentDeleteScope.BOTH}:
            deleted_digital = await self._delete_digital(document_id)

        if scope in {DocumentDeleteScope.ORIGINAL, DocumentDeleteScope.BOTH}:
            deleted_original = await self._delete_original_file(document)

        if scope == DocumentDeleteScope.BOTH:
            await self._documents.delete_by_ids([document_id])
            document_removed = True
        elif scope == DocumentDeleteScope.ORIGINAL:
            extraction = await self._extractions.get_latest_for_document(document_id)
            if extraction is None:
                await self._documents.delete_by_ids([document_id])
                document_removed = True
            else:
                cleared = self._cleared_original_document(document)
                await self._documents.save(cleared)
        elif scope == DocumentDeleteScope.DIGITAL and not self._has_original_file(document):
            # Form-only shells with no real upload: removing digital leaves an empty shell.
            # Drop the document row so the type returns to a clean Missing state.
            try:
                if document.storage_key:
                    await self._storage.delete(document.storage_key)
            except Exception:
                logger.warning(
                    "Failed to delete storage for form-only document %s",
                    document_id,
                    exc_info=True,
                )
            await self._documents.delete_by_ids([document_id])
            document_removed = True
            deleted_original = True

        return {
            "document_id": str(document_id),
            "scope": scope.value,
            "deleted_original": deleted_original,
            "deleted_digital": deleted_digital,
            "document_removed": document_removed,
            "deleted": True,
        }

    async def _delete_digital(self, document_id: UUID) -> bool:
        deleted = await self._extractions.delete_for_document_ids([document_id])
        delete_runs = getattr(self._validation_runs, "delete_for_document_ids", None)
        if callable(delete_runs):
            await delete_runs([document_id])
        return deleted >= 0

    async def _delete_original_file(self, document: Document) -> bool:
        if not document.storage_key:
            return False
        try:
            await self._storage.delete(document.storage_key)
        except Exception:
            logger.warning(
                "Failed to delete storage object for document %s",
                document.id,
                exc_info=True,
            )
        return True

    @staticmethod
    def _has_original_file(document: Document) -> bool:
        meta = dict(document.metadata or {})
        if meta.get("form_only") or meta.get("original_removed"):
            return False
        return bool(document.storage_key) and int(document.file_size_bytes or 0) > 0

    @staticmethod
    def _cleared_original_document(document: Document) -> Document:
        meta = dict(document.metadata or {})
        meta["original_removed"] = True
        meta.pop("form_only", None)
        return replace(
            document,
            storage_key="",
            original_filename="",
            mime_type="application/octet-stream",
            file_size_bytes=0,
            checksum_sha256="",
            metadata=meta,
        )
