"""SQLAlchemy validation finding repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.dto.validation_run import ValidationFindingRecord
from payroll_copilot.application.ports.repositories import ValidationFindingRepository
from payroll_copilot.infrastructure.persistence.mappers.validation_mapper import (
    finding_model_to_record,
    finding_record_to_model,
)
from payroll_copilot.infrastructure.persistence.models import ValidationFindingModel


class SqlAlchemyValidationFindingRepository(ValidationFindingRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_all(
        self,
        run_id: UUID,
        findings: list[ValidationFindingRecord],
    ) -> list[ValidationFindingRecord]:
        saved: list[ValidationFindingRecord] = []
        for finding in findings:
            model = finding_record_to_model(finding)
            self._session.add(model)
            saved.append(finding)
        await self._session.flush()
        return saved

    async def list_by_run_id(self, run_id: UUID) -> list[ValidationFindingRecord]:
        result = await self._session.execute(
            select(ValidationFindingModel)
            .where(ValidationFindingModel.validation_run_id == run_id)
            .order_by(ValidationFindingModel.created_at)
        )
        models = result.scalars().all()
        return [finding_model_to_record(model) for model in models]
