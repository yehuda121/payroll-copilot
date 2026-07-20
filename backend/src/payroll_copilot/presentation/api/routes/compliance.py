"""Compliance and MCP legal rule sync routes."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from payroll_copilot.application.ports.employee_audit import AuditLogEntry
from payroll_copilot.application.services.rule_version_store import RuleVersionStore
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb.factory import get_audit_log_repository
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader
from payroll_copilot.presentation.api.security import AuthPrincipal, require_org_operator

router = APIRouter()


class LegalRuleFileInfo(BaseModel):
    filename: str
    version: str
    content_hash: str
    rules_count: int


class DiffProposalResponse(BaseModel):
    id: str
    rule_file: str
    external_source: str
    status: str
    diff_summary: str


class RuleContentResponse(BaseModel):
    filename: str
    content: str
    versions: list[dict[str, Any]] = Field(default_factory=list)


class RuleUpdateRequest(BaseModel):
    content: str = Field(min_length=1)
    reason: str = Field(min_length=3, max_length=500)


class RuleRollbackRequest(BaseModel):
    version_id: str
    reason: str = Field(min_length=3, max_length=500)


@router.get("/legal-rules", response_model=list[LegalRuleFileInfo])
async def list_legal_rules(
    _: AuthPrincipal = Depends(require_org_operator),
) -> list[LegalRuleFileInfo]:
    settings = get_settings()
    loader = YamlLegalRulesLoader(settings.legal_rules_path)
    bundles = loader.load_all()

    return [
        LegalRuleFileInfo(
            filename=f"{name}.yaml",
            version=bundle.version,
            content_hash=loader.get_file_hash(f"{name}.yaml"),
            rules_count=len(bundle.rules),
        )
        for name, bundle in bundles.items()
    ]


@router.get("/legal-rules/{filename}", response_model=RuleContentResponse)
async def get_legal_rule_file(
    filename: str,
    _: AuthPrincipal = Depends(require_org_operator),
) -> RuleContentResponse:
    settings = get_settings()
    store = RuleVersionStore(settings.legal_rules_path)
    try:
        content = store.read_current(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule file not found") from exc
    versions = [asdict(item) for item in store.list_versions(filename)]
    return RuleContentResponse(filename=filename, content=content, versions=versions)


@router.put("/legal-rules/{filename}", response_model=RuleContentResponse)
async def update_legal_rule_file(
    filename: str,
    body: RuleUpdateRequest,
    principal: AuthPrincipal = Depends(require_org_operator),
) -> RuleContentResponse:
    settings = get_settings()
    store = RuleVersionStore(settings.legal_rules_path)
    audit = get_audit_log_repository()
    try:
        record = store.write_with_version(
            filename=filename,
            content=body.content,
            reason=body.reason,
            actor_user_id=principal.user_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule file not found") from exc

    await audit.append(
        AuditLogEntry(
            action="rule.edited",
            resource_type="legal_rule_file",
            resource_id=None,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            details={
                "filename": filename,
                "version_id": record.version_id,
                "reason": body.reason,
                "previous_version_id": record.previous_version_id,
            },
        )
    )
    versions = [asdict(item) for item in store.list_versions(filename)]
    return RuleContentResponse(filename=filename, content=body.content, versions=versions)


@router.post("/legal-rules/{filename}/rollback", response_model=RuleContentResponse)
async def rollback_legal_rule_file(
    filename: str,
    body: RuleRollbackRequest,
    principal: AuthPrincipal = Depends(require_org_operator),
) -> RuleContentResponse:
    settings = get_settings()
    store = RuleVersionStore(settings.legal_rules_path)
    audit = get_audit_log_repository()
    try:
        record = store.rollback(
            filename=filename,
            version_id=body.version_id,
            reason=body.reason,
            actor_user_id=principal.user_id,
        )
        content = store.read_current(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    await audit.append(
        AuditLogEntry(
            action="rule.rollback",
            resource_type="legal_rule_file",
            resource_id=None,
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            details={
                "filename": filename,
                "version_id": record.version_id,
                "reason": body.reason,
                "rolled_back_to": body.version_id,
            },
        )
    )
    versions = [asdict(item) for item in store.list_versions(filename)]
    return RuleContentResponse(filename=filename, content=content, versions=versions)


@router.get("/diff-proposals", response_model=list[DiffProposalResponse])
async def list_diff_proposals(
    _: AuthPrincipal = Depends(require_org_operator),
) -> list[DiffProposalResponse]:
    return []


@router.post("/diff-proposals/{proposal_id}/approve")
async def approve_diff_proposal(
    proposal_id: str,
    _: AuthPrincipal = Depends(require_org_operator),
) -> dict[str, str]:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Diff proposal {proposal_id} not found",
    )


@router.post("/diff-proposals/{proposal_id}/reject")
async def reject_diff_proposal(
    proposal_id: str,
    _: AuthPrincipal = Depends(require_org_operator),
) -> dict[str, str]:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Diff proposal {proposal_id} not found",
    )


@router.post("/sync-check", status_code=202)
async def trigger_sync_check(
    _: AuthPrincipal = Depends(require_org_operator),
) -> dict[str, str]:
    from payroll_copilot.infrastructure.tasks.celery_app import sync_legal_rules_mcp

    task = sync_legal_rules_mcp.delay()
    return {"status": "queued", "task_id": task.id}
