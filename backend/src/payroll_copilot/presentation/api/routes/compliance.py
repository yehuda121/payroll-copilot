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


class ExternalLegalCandidateRequest(BaseModel):
    rule_id: str
    parameter_key: str
    proposed_value: Any
    legal_source: str
    effective_date: str | None = None
    explanation: str = ""
    rule_name: str | None = None


class CheckLegalUpdatesRequest(BaseModel):
    """Optional structured candidates (tests / MCP-normalized). Empty → text extract path."""

    candidates: list[ExternalLegalCandidateRequest] = Field(default_factory=list)
    external_text_by_source: dict[str, str] = Field(default_factory=dict)


class ApplyLegalUpdatesRequest(BaseModel):
    selected_change_ids: list[str] = Field(default_factory=list)
    effective_changes: list[dict[str, Any]] = Field(default_factory=list)
    future_changes: list[dict[str, Any]] = Field(default_factory=list)


def _parse_candidate(raw: ExternalLegalCandidateRequest):
    from datetime import date as date_cls

    from payroll_copilot.application.services.legal_update_check import (
        ExternalLegalCandidate,
    )

    eff = None
    if raw.effective_date:
        eff = date_cls.fromisoformat(raw.effective_date[:10])
    return ExternalLegalCandidate(
        rule_id=raw.rule_id,
        parameter_key=raw.parameter_key,
        proposed_value=raw.proposed_value,
        legal_source=raw.legal_source,
        effective_date=eff,
        explanation=raw.explanation,
        rule_name=raw.rule_name,
    )


@router.post("/check-legal-updates")
async def check_legal_updates(
    body: CheckLegalUpdatesRequest,
    _: AuthPrincipal = Depends(require_org_operator),
) -> dict[str, Any]:
    """Accountant-triggered legal update check. Never runs during payslip validation."""
    from payroll_copilot.application.services.legal_update_check import (
        LegalUpdateCheckService,
    )

    settings = get_settings()
    service = LegalUpdateCheckService(rules_path=settings.legal_rules_path)
    candidates = [_parse_candidate(item) for item in body.candidates]
    if candidates or body.external_text_by_source:
        result = service.check(
            external_candidates=candidates or None,
            external_text_by_source=body.external_text_by_source or None,
        )
    else:
        # Accountant button with no override payload: fetch configured legal sources.
        result = await service.check_from_configured_sources()
    return result.to_dict()


@router.post("/apply-legal-updates")
async def apply_legal_updates(
    body: ApplyLegalUpdatesRequest,
    principal: AuthPrincipal = Depends(require_org_operator),
) -> dict[str, Any]:
    """Apply selected effective legal changes as immutable new versions."""
    from payroll_copilot.application.services.legal_update_check import (
        LegalRuleDifference,
        LegalUpdateCheckService,
    )

    settings = get_settings()
    service = LegalUpdateCheckService(rules_path=settings.legal_rules_path)

    def _to_diff(raw: dict[str, Any]) -> LegalRuleDifference:
        return LegalRuleDifference(
            change_id=str(raw.get("change_id") or ""),
            rule_id=str(raw.get("rule_id") or ""),
            rule_name=str(raw.get("rule_name") or ""),
            parameter_key=str(raw.get("parameter_key") or ""),
            current_value=raw.get("current_value"),
            proposed_value=raw.get("proposed_value"),
            legal_source=str(raw.get("legal_source") or ""),
            effective_date=raw.get("effective_date"),
            explanation=str(raw.get("explanation") or ""),
            selectable=bool(raw.get("selectable")),
            kind=str(raw.get("kind") or "effective"),
        )

    changes = [_to_diff(item) for item in body.effective_changes] + [
        _to_diff(item) for item in body.future_changes
    ]
    result = service.apply_selected(
        changes=changes,
        selected_change_ids=list(body.selected_change_ids),
        approved_by=str(principal.user_id),
    )
    return result.to_dict()
