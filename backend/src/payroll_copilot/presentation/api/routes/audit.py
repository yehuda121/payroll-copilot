"""Audit log read API for accountant / admin portals."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.validation.demo_validation_context_builder import (
    DEMO_ORGANIZATION_ID,
)
from payroll_copilot.infrastructure.persistence.database import get_db_session
from payroll_copilot.infrastructure.persistence.repositories.audit_log_repository import (
    SqlAlchemyAuditLogRepository,
)

router = APIRouter()


@router.get("")
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    organization_id: UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    repo = SqlAlchemyAuditLogRepository(session)
    rows = await repo.list_recent(
        organization_id=organization_id or DEMO_ORGANIZATION_ID,
        limit=limit,
        offset=offset,
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": str(row.resource_id) if row.resource_id else None,
            "organization_id": str(row.organization_id) if row.organization_id else None,
            "user_id": str(row.user_id) if row.user_id else None,
            "details": row.details,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
