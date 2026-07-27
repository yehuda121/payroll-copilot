"""Developer-admin Legal Knowledge APIs — sync, proposals, versions, vector index."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from payroll_copilot.application.dto.legal_knowledge import (
    ApproveProposalRequest,
    LegalChangeProposal,
    LegalSyncRun,
    ProposalStatus,
    RejectProposalRequest,
    SyncTrigger,
    VectorIndexHealth,
)
from payroll_copilot.application.services.legal_knowledge_sync import LegalKnowledgeSyncService
from payroll_copilot.application.services.legal_proposal_service import LegalProposalService
from payroll_copilot.application.services.legal_rag_indexer import LegalRagIndexer
from payroll_copilot.application.services.legal_rule_version_catalog import LegalRuleVersionCatalog
from payroll_copilot.application.services.legal_source_registry import LegalSourceRegistry
from payroll_copilot.application.services.validation_catalog import catalog_by_rule_id, catalog_as_dicts
from payroll_copilot.application.ports.ai_capabilities import AICapability
from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb.factory import get_audit_log_repository
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import get_legal_knowledge_store
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader
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


class SyncRequest(BaseModel):
    content_overrides: dict[str, str] | None = None


class OverviewResponse(BaseModel):
    active_rules: int
    historical_versions: int
    watched_sources: int
    discovery_sources: int
    pending_changes: int
    last_sync: LegalSyncRun | None = None
    vector_index: VectorIndexHealth


@router.get("/overview", response_model=OverviewResponse)
async def legal_overview(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> OverviewResponse:
    settings = get_settings()
    catalog = LegalRuleVersionCatalog(settings.legal_rules_path)
    versions = catalog.ensure_seeded_from_yaml()
    registry = LegalSourceRegistry()
    sources = registry.load()
    store = get_legal_knowledge_store()
    runs = store.list_sync_runs(limit=1)
    pending = store.list_proposals(status=ProposalStatus.PENDING_REVIEW, limit=500)
    return OverviewResponse(
        active_rules=len([v for v in versions if v.status == "ACTIVE"]),
        historical_versions=len([v for v in versions if v.status == "SUPERSEDED"]),
        watched_sources=len([s for s in sources if s.source_type.value == "WATCHED_SOURCE"]),
        discovery_sources=len([s for s in sources if s.source_type.value == "DISCOVERY_SOURCE"]),
        pending_changes=len(pending),
        last_sync=runs[0] if runs else None,
        vector_index=store.vector_health(),
    )


@router.get("/rules")
async def list_rules(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> list[dict[str, Any]]:
    settings = get_settings()
    catalog = LegalRuleVersionCatalog(settings.legal_rules_path)
    versions = catalog.ensure_seeded_from_yaml()
    coverage = LegalSourceRegistry().rule_coverage_map()
    loader = YamlLegalRulesLoader(settings.legal_rules_path)
    bundle = loader.load_merged_rules()
    by_rule: dict[str, list] = {}
    for v in versions:
        by_rule.setdefault(v.rule_id, []).append(v)
    rows = []
    for rule_id, vers in sorted(by_rule.items()):
        active = next((v for v in vers if v.status == "ACTIVE" and v.valid_to is None), vers[-1])
        title = rule_id
        for rule in bundle.rules.values():
            if rule.rule_id == rule_id:
                title = (rule.description or {}).get("en") or (rule.description or {}).get("he") or rule_id
                break
        cov = coverage.get(rule_id, {})
        catalog_entry = catalog_by_rule_id().get(rule_id)
        rows.append(
            {
                "rule_id": rule_id,
                "title": title,
                "current_version": active.version,
                "valid_from": active.valid_from,
                "valid_to": active.valid_to,
                "scope": active.scope,
                "source_coverage": cov.get("coverage_status", "unconfigured"),
                "watched_sources": cov.get("watched_sources", []),
                "index_status": "unknown",
                "validation_readiness": (
                    catalog_entry.readiness if catalog_entry else "Unavailable"
                ),
                "validation_readiness_reason": (
                    catalog_entry.readiness_reason if catalog_entry else "Unavailable"
                ),
                "required_fields": (
                    list(catalog_entry.required_fields) if catalog_entry else []
                ),
                "currently_executed": (
                    catalog_entry.currently_executed if catalog_entry else "Unavailable"
                ),
            }
        )
    return rows


@router.get("/rules/{rule_id}")
async def get_rule_detail(
    rule_id: str,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    settings = get_settings()
    catalog = LegalRuleVersionCatalog(settings.legal_rules_path)
    versions = catalog.list_versions(rule_id)
    if not versions:
        raise HTTPException(status_code=404, detail="rule_not_found")
    validation_meta = catalog_by_rule_id().get(rule_id)
    coverage = LegalSourceRegistry().rule_coverage_map().get(rule_id)
    store = get_legal_knowledge_store()
    vector = store.vector_health()
    return {
        "rule_id": rule_id,
        "versions": [v.__dict__ for v in versions],
        "active": (catalog.get_active(rule_id).__dict__ if catalog.get_active(rule_id) else None),
        "coverage": coverage,
        "validation_readiness": validation_meta.readiness if validation_meta else "Unavailable",
        "validation_readiness_reason": (
            validation_meta.readiness_reason if validation_meta else "Unavailable"
        ),
        "required_fields": list(validation_meta.required_fields) if validation_meta else [],
        "applicability": validation_meta.applicability if validation_meta else "Unavailable",
        "currently_executed": (
            validation_meta.currently_executed if validation_meta else "Unavailable"
        ),
        "source_monitoring_status": (
            (coverage or {}).get("coverage_status") if coverage else "Unavailable"
        ),
        "vector_index_status": vector.status if vector else "Unavailable",
        "last_source_sync": (
            store.list_sync_runs(limit=1)[0].completed_at
            if store.list_sync_runs(limit=1)
            else None
        ),
    }


@router.get("/validation-catalog")
async def validation_catalog(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> list[dict[str, Any]]:
    """Backend-authoritative validation catalog with readiness metadata."""
    return catalog_as_dicts()


@router.get("/sources")
async def list_sources(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> list[dict[str, Any]]:
    store = get_legal_knowledge_store()
    out = []
    for source in LegalSourceRegistry().load():
        state = store.get_source_state(source.source_id)
        out.append(
            {
                **source.model_dump(mode="json"),
                "last_checked_at": state.get("updated_at"),
                "last_content_hash": state.get("last_content_hash"),
            }
        )
    return out


@router.get("/coverage")
async def rule_coverage(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    return LegalSourceRegistry().rule_coverage_map()


@router.post("/sync", response_model=LegalSyncRun)
async def sync_legal_sources(
    body: SyncRequest | None = None,
    principal: AuthPrincipal = Depends(require_developer_admin),
) -> LegalSyncRun:
    settings = get_settings()
    model = None
    try:
        model = AIProviderRouter(settings).provider_for(AICapability.ASSISTANT)
    except Exception:  # noqa: BLE001
        model = None
    from payroll_copilot.application.services.legal_change_analyzer import LegalChangeAnalyzer

    service = LegalKnowledgeSyncService(
        analyzer=LegalChangeAnalyzer(model),
        audit=get_audit_log_repository(),
        rules_path=settings.legal_rules_path,
        store=get_legal_knowledge_store(),
    )
    return await service.run_sync(
        trigger=SyncTrigger.MANUAL,
        triggered_by=str(principal.user_id),
        content_overrides=(body.content_overrides if body else None),
    )


@router.get("/sync/runs", response_model=list[LegalSyncRun])
async def list_sync_runs(
    _: AuthPrincipal = Depends(require_developer_admin),
    limit: int = 50,
) -> list[LegalSyncRun]:
    return get_legal_knowledge_store().list_sync_runs(limit=limit)


@router.get("/sync/runs/{run_id}", response_model=LegalSyncRun)
async def get_sync_run(
    run_id: str,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> LegalSyncRun:
    run = get_legal_knowledge_store().get_sync_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="sync_run_not_found")
    return run


@router.get("/proposals", response_model=list[LegalChangeProposal])
async def list_proposals(
    _: AuthPrincipal = Depends(require_developer_admin),
    status_filter: ProposalStatus | None = None,
) -> list[LegalChangeProposal]:
    return get_legal_knowledge_store().list_proposals(status=status_filter, limit=200)


@router.get("/proposals/{proposal_id}")
async def get_proposal(
    proposal_id: str,
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    store = get_legal_knowledge_store()
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal_not_found")
    old_text = store.read_snapshot(proposal.old_snapshot_ref) if proposal.old_snapshot_ref else None
    new_text = store.read_snapshot(proposal.new_snapshot_ref) if proposal.new_snapshot_ref else None
    return {
        "proposal": proposal.model_dump(mode="json"),
        "old_snapshot": old_text,
        "new_snapshot": new_text,
    }


@router.post("/proposals/{proposal_id}/approve", response_model=LegalChangeProposal)
async def approve_proposal(
    proposal_id: str,
    body: ApproveProposalRequest,
    principal: AuthPrincipal = Depends(require_developer_admin),
) -> LegalChangeProposal:
    settings = get_settings()
    store = get_legal_knowledge_store()

    async def _reindex(rule_id: str, version: str) -> None:
        try:
            model = AIProviderRouter(settings).provider_for(AICapability.ASSISTANT)
            indexer = LegalRagIndexer(
                rules_path=settings.legal_rules_path,
                model=model,
                store=store,
            )
            await indexer.reindex_rule_version(rule_id, version)
        except Exception:  # noqa: BLE001
            # Approval must not fail solely because reindex failed; health records error.
            store.set_vector_error(f"reindex_failed:{rule_id}@v{version}")

    service = LegalProposalService(
        store=store,
        catalog=LegalRuleVersionCatalog(settings.legal_rules_path),
        rules_path=settings.legal_rules_path,
        audit=get_audit_log_repository(),
        on_version_approved=_reindex,
    )
    try:
        return await service.approve(proposal_id, body, reviewer_user_id=principal.user_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/proposals/{proposal_id}/reject", response_model=LegalChangeProposal)
async def reject_proposal(
    proposal_id: str,
    body: RejectProposalRequest,
    principal: AuthPrincipal = Depends(require_developer_admin),
) -> LegalChangeProposal:
    settings = get_settings()
    service = LegalProposalService(
        store=get_legal_knowledge_store(),
        catalog=LegalRuleVersionCatalog(settings.legal_rules_path),
        rules_path=settings.legal_rules_path,
        audit=get_audit_log_repository(),
    )
    try:
        return await service.reject(proposal_id, body, reviewer_user_id=principal.user_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="proposal_not_found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/vector-index", response_model=VectorIndexHealth)
async def vector_index_health(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> VectorIndexHealth:
    return get_legal_knowledge_store().vector_health()


@router.post("/vector-index/rebuild")
async def rebuild_vector_index(
    _: AuthPrincipal = Depends(require_developer_admin),
) -> dict[str, Any]:
    settings = get_settings()
    model = AIProviderRouter(settings).provider_for(AICapability.ASSISTANT)
    indexer = LegalRagIndexer(
        rules_path=settings.legal_rules_path,
        model=model,
        store=get_legal_knowledge_store(),
        embedding_model_name=getattr(model, "embedding_model", None) or "configured_provider",
    )
    try:
        return await indexer.rebuild_all()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"rebuild_failed:{exc}") from exc
