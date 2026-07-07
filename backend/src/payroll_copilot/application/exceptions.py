"""Application-layer exceptions."""

from __future__ import annotations

from uuid import UUID


class DocumentNotFoundError(Exception):
    def __init__(self, document_id: UUID) -> None:
        self.document_id = document_id
        super().__init__(f"Document {document_id} not found")


class DocumentUploadRejectedError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
