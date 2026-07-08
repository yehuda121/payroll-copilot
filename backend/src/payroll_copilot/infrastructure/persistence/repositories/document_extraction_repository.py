"""SQLAlchemy document extraction repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.repositories import DocumentExtractionRepository
from payroll_copilot.domain.entities import DocumentExtraction
from payroll_copilot.infrastructure.persistence.mappers.document_extraction_mapper import (
    extraction_to_entity,
    extraction_to_model,
)
from payroll_copilot.infrastructure.persistence.models import DocumentExtractionModel


class SqlAlchemyDocumentExtractionRepository(DocumentExtractionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, extraction_id: UUID) -> DocumentExtraction | None:
        result = await self._session.execute(
            select(DocumentExtractionModel).where(DocumentExtractionModel.id == extraction_id)
        )
        model = result.scalar_one_or_none()
        return extraction_to_entity(model) if model else None

    async def get_latest_for_document(self, document_id: UUID) -> DocumentExtraction | None:
        result = await self._session.execute(
            select(DocumentExtractionModel)
            .where(DocumentExtractionModel.document_id == document_id)
            .order_by(
                DocumentExtractionModel.extraction_version.desc(),
                DocumentExtractionModel.created_at.desc(),
            )
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return extraction_to_entity(model) if model else None

    async def save(self, extraction: DocumentExtraction) -> DocumentExtraction:
        model = extraction_to_model(extraction)
        await self._session.merge(model)
        await self._session.flush()
        return extraction
