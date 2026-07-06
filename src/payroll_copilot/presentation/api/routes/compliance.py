"""Compliance and MCP legal rule sync routes."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader

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


@router.get("/legal-rules", response_model=list[LegalRuleFileInfo])
async def list_legal_rules() -> list[LegalRuleFileInfo]:
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


@router.get("/diff-proposals", response_model=list[DiffProposalResponse])
async def list_diff_proposals() -> list[DiffProposalResponse]:
    return []


@router.post("/diff-proposals/{proposal_id}/approve")
async def approve_diff_proposal(proposal_id: str) -> dict[str, str]:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Diff proposal {proposal_id} not found",
    )


@router.post("/diff-proposals/{proposal_id}/reject")
async def reject_diff_proposal(proposal_id: str) -> dict[str, str]:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Diff proposal {proposal_id} not found",
    )


@router.post("/sync-check", status_code=202)
async def trigger_sync_check() -> dict[str, str]:
    from payroll_copilot.infrastructure.tasks.celery_app import sync_legal_rules_mcp

    task = sync_legal_rules_mcp.delay()
    return {"status": "queued", "task_id": task.id}
