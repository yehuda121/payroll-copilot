"""SQLAlchemy validation run repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.ports.repositories import ValidationRunRepository
from payroll_copilot.infrastructure.persistence.mappers.validation_mapper import (
    run_model_to_record,
    run_record_to_model,
)
from payroll_copilot.infrastructure.persistence.models import ValidationRunModel


class SqlAlchemyValidationRunRepository(ValidationRunRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, run: ValidationRunRecord) -> ValidationRunRecord:
        model = run_record_to_model(run)
        await self._session.merge(model)
        await self._session.flush()
        return run

    async def get_by_id(self, run_id: UUID) -> ValidationRunRecord | None:
        result = await self._session.execute(
            select(ValidationRunModel).where(ValidationRunModel.id == run_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return run_model_to_record(model)

    async def list_latest_by_document_ids(
        self, document_ids: list[UUID]
    ) -> dict[UUID, ValidationRunRecord]:
        if not document_ids:
            return {}
        result = await self._session.execute(
            select(ValidationRunModel)
            .where(ValidationRunModel.document_id.in_(document_ids))
            .order_by(
                ValidationRunModel.document_id,
                ValidationRunModel.completed_at.desc().nullslast(),
                ValidationRunModel.started_at.desc().nullslast(),
            )
        )
        latest: dict[UUID, ValidationRunRecord] = {}
        for model in result.scalars().all():
            if model.document_id in latest:
                continue
            latest[model.document_id] = run_model_to_record(model)
        return latest

    async def list_for_document(self, document_id: UUID) -> list[ValidationRunRecord]:
        result = await self._session.execute(
            select(ValidationRunModel)
            .where(ValidationRunModel.document_id == document_id)
            .order_by(
                ValidationRunModel.completed_at.desc().nullslast(),
                ValidationRunModel.started_at.desc().nullslast(),
            )
        )
        return [run_model_to_record(model) for model in result.scalars().all()]
