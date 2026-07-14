"""SQLAlchemy audit log repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.employee_audit import (
    AuditLogEntry,
    AuditLogRecord,
    AuditLogRepository,
)
from payroll_copilot.infrastructure.persistence.models import AuditLogModel


class SqlAlchemyAuditLogRepository(AuditLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, entry: AuditLogEntry) -> AuditLogRecord:
        model = AuditLogModel(
            organization_id=entry.organization_id,
            user_id=entry.user_id,
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            ip_address=entry.ip_address,
            user_agent=entry.user_agent,
            details=dict(entry.details or {}),
        )
        self._session.add(model)
        await self._session.flush()
        return AuditLogRecord(
            id=model.id,
            action=model.action,
            resource_type=model.resource_type,
            resource_id=model.resource_id,
            organization_id=model.organization_id,
            user_id=model.user_id,
            details=dict(model.details or {}),
            created_at=model.created_at,
        )

    async def list_recent(
        self,
        *,
        organization_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogRecord]:
        stmt = select(AuditLogModel).order_by(AuditLogModel.created_at.desc())
        if organization_id is not None:
            stmt = stmt.where(AuditLogModel.organization_id == organization_id)
        stmt = stmt.offset(max(0, offset)).limit(min(max(1, limit), 500))
        result = await self._session.execute(stmt)
        return [
            AuditLogRecord(
                id=model.id,
                action=model.action,
                resource_type=model.resource_type,
                resource_id=model.resource_id,
                organization_id=model.organization_id,
                user_id=model.user_id,
                details=dict(model.details or {}),
                created_at=model.created_at,
            )
            for model in result.scalars().all()
        ]

    async def delete_by_dataset_id(self, *, dataset_id: str) -> int:
        result = await self._session.execute(select(AuditLogModel))
        ids: list[int] = []
        for model in result.scalars().all():
            details = model.details or {}
            if details.get("dataset_id") == dataset_id:
                ids.append(model.id)
        if not ids:
            return 0
        deleted = await self._session.execute(
            delete(AuditLogModel).where(AuditLogModel.id.in_(ids))
        )
        await self._session.flush()
        return int(deleted.rowcount or 0)
