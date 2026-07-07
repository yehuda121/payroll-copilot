"""SQLAlchemy document repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.repositories import DocumentRepository
from payroll_copilot.domain.entities import Document
from payroll_copilot.infrastructure.persistence.mappers.document_mapper import (
    document_to_entity,
    document_to_model,
)
from payroll_copilot.infrastructure.persistence.models import DocumentModel


class SqlAlchemyDocumentRepository(DocumentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, document_id: UUID) -> Document | None:
        result = await self._session.execute(
            select(DocumentModel).where(DocumentModel.id == document_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return document_to_entity(model)

    async def save(self, document: Document) -> Document:
        model = document_to_model(document)
        await self._session.merge(model)
        await self._session.flush()
        return document
