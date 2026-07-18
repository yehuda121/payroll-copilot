"""Audit log read API for accountant / admin portals."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_audit_log_repository,
)
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    require_org_operator,
)

router = APIRouter()


@router.get("")
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: AuthPrincipal = Depends(require_org_operator),
) -> list[dict[str, Any]]:
    """Return audit rows for the authenticated operator's organization only."""
    repo = get_audit_log_repository()
    rows = await repo.list_recent(
        organization_id=principal.organization_id,
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
