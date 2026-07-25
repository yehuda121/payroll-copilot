"""Developer-admin APIs for organization vacation email integration credentials."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from payroll_copilot.application.ports.vacation_settings import IntegrationCredential
from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.persistence import dynamodb as dynamo_persistence
from payroll_copilot.infrastructure.persistence.dynamodb.vacation_settings import (
    create_integration_api_key,
)
from payroll_copilot.presentation.api.security import AuthPrincipal, get_auth_principal

router = APIRouter()


async def require_developer_admin(
    principal: AuthPrincipal = Depends(get_auth_principal),  # noqa: B008
) -> AuthPrincipal:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_role_required",
                "message": "Developer admin role required.",
            },
        )
    return principal


class CreateOrgIntegrationCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(default="n8n", max_length=64)


@router.post(
    "/organizations/{organization_id}/integration-credentials",
    status_code=status.HTTP_201_CREATED,
)
async def create_org_integration_credential(
    organization_id: UUID,
    body: CreateOrgIntegrationCredentialRequest | None = None,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    """Create org-bound n8n API key. Plaintext returned once."""
    label = (body.label if body else "n8n") or "n8n"
    plaintext, key_hash, prefix = create_integration_api_key()
    repo = dynamo_persistence.get_integration_credential_repository()
    cred = IntegrationCredential(
        id=uuid4(),
        organization_id=organization_id,
        key_hash=key_hash,
        key_prefix=prefix,
        label=label.strip()[:64] or "n8n",
        created_at=datetime.now(UTC),
    )
    await repo.save(cred)
    return {
        "id": str(cred.id),
        "organization_id": str(organization_id),
        "api_key": plaintext,
        "key_prefix": prefix,
        "label": cred.label,
        "message": "Store this API key securely. It will not be shown again.",
    }


@router.get("/organizations/{organization_id}/integration-credentials")
async def list_org_integration_credentials(
    organization_id: UUID,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    repo = dynamo_persistence.get_integration_credential_repository()
    items = await repo.list_for_org(organization_id)
    return {
        "items": [
            {
                "id": str(c.id),
                "organization_id": str(c.organization_id),
                "key_prefix": c.key_prefix,
                "label": c.label,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
            }
            for c in items
        ]
    }


@router.post(
    "/organizations/{organization_id}/integration-credentials/{credential_id}/revoke"
)
async def revoke_org_integration_credential(
    organization_id: UUID,
    credential_id: UUID,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    repo = dynamo_persistence.get_integration_credential_repository()
    active = await repo.list_for_org(organization_id)
    if not any(c.id == credential_id for c in active):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    await repo.revoke(organization_id, credential_id)
    return {"id": str(credential_id), "revoked": True}
