"""SQLAlchemy document repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
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

    async def list_for_employee(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
    ) -> list[Document]:
        result = await self._session.execute(
            select(DocumentModel)
            .where(
                DocumentModel.organization_id == organization_id,
                DocumentModel.employee_id == employee_id,
            )
            .order_by(DocumentModel.period_year.desc(), DocumentModel.period_month.desc())
        )
        return [document_to_entity(model) for model in result.scalars().all()]

    async def list_by_dataset_id(self, *, dataset_id: str) -> list[Document]:
        result = await self._session.execute(select(DocumentModel))
        matched: list[Document] = []
        for model in result.scalars().all():
            meta = model.metadata_ or {}
            if meta.get("dataset_id") == dataset_id:
                matched.append(document_to_entity(model))
        return matched

    async def delete_by_ids(self, document_ids: list[UUID]) -> int:
        if not document_ids:
            return 0
        result = await self._session.execute(
            delete(DocumentModel).where(DocumentModel.id.in_(document_ids))
        )
        await self._session.flush()
        return int(result.rowcount or 0)
