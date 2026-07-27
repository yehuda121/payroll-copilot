"""Proposal approval/rejection — developer_admin only at API boundary."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Awaitable
from uuid import UUID

import yaml

from payroll_copilot.application.dto.legal_knowledge import (
    ApproveProposalRequest,
    ChangeClassification,
    LegalChangeProposal,
    ProposalStatus,
    RejectProposalRequest,
)
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository
from payroll_copilot.application.services.legal_rule_version_catalog import LegalRuleVersionCatalog
from payroll_copilot.application.services.rule_version_store import RuleVersionStore
from payroll_copilot.infrastructure.persistence.legal_knowledge_store import LegalKnowledgeStore
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader


class LegalProposalService:
    def __init__(
        self,
        *,
        store: LegalKnowledgeStore,
        catalog: LegalRuleVersionCatalog,
        rules_path: str,
        audit: AuditLogRepository | None = None,
        on_version_approved: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._store = store
        self._catalog = catalog
        self._rules_path = rules_path
        self._audit = audit
        self._on_version_approved = on_version_approved

    async def approve(
        self,
        proposal_id: str,
        body: ApproveProposalRequest,
        *,
        reviewer_user_id: UUID,
    ) -> LegalChangeProposal:
        proposal = self._store.get_proposal(proposal_id)
        if proposal is None:
            raise LookupError("proposal_not_found")
        if proposal.status != ProposalStatus.PENDING_REVIEW:
            raise ValueError("proposal_not_pending")
        if not body.confirm_effective_date:
            raise ValueError("confirm_effective_date_required")
        if body.effective_date is None:
            raise ValueError("effective_date_required")

        if proposal.classification == ChangeClassification.NEW_RELEVANT_LAW:
            return await self._approve_new_rule(proposal, body, reviewer_user_id=reviewer_user_id)

        return await self._approve_new_version(proposal, body, reviewer_user_id=reviewer_user_id)

    async def reject(
        self,
        proposal_id: str,
        body: RejectProposalRequest,
        *,
        reviewer_user_id: UUID,
    ) -> LegalChangeProposal:
        from datetime import datetime, timezone

        proposal = self._store.get_proposal(proposal_id)
        if proposal is None:
            raise LookupError("proposal_not_found")
        if proposal.status != ProposalStatus.PENDING_REVIEW:
            raise ValueError("proposal_not_pending")

        proposal.status = ProposalStatus.REJECTED
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.reviewed_by = str(reviewer_user_id)
        proposal.review_reason = body.reason
        self._store.save_proposal(proposal)

        if self._audit:
            await self._audit.append(
                AuditLogEntry(
                    action="legal_proposal.rejected",
                    resource_type="legal_change_proposal",
                    resource_id=None,
                    organization_id=None,
                    user_id=reviewer_user_id,
                    details={
                        "proposal_id": proposal_id,
                        "reason": body.reason,
                        "source_id": proposal.source_id,
                    },
                )
            )
        return proposal

    async def _approve_new_version(
        self,
        proposal: LegalChangeProposal,
        body: ApproveProposalRequest,
        *,
        reviewer_user_id: UUID,
    ) -> LegalChangeProposal:
        from datetime import datetime, timezone

        if not proposal.affected_rule_ids:
            raise ValueError("affected_rule_ids_required")

        rule_id = proposal.affected_rule_ids[0]
        loader = YamlLegalRulesLoader(self._rules_path)
        bundle = loader.load_merged_rules()
        rule_body: dict[str, Any] | None = body.rule_yaml_override
        source_file = None
        if rule_body is None:
            for key, rule in bundle.rules.items():
                if rule.rule_id == rule_id:
                    # reconstruct minimal body from current approved rule
                    rule_body = {
                        "id": rule.rule_id,
                        "description": rule.description,
                        "parameters": rule.parameters,
                        "legal_reference": rule.legal_reference,
                        "severity": rule.severity.value if hasattr(rule.severity, "value") else str(rule.severity),
                    }
                    # find source file
                    for name, file_bundle in loader.load_all().items():
                        if rule_id in {r.rule_id for r in file_bundle.rules.values()}:
                            source_file = f"{name}.yaml"
                            break
                    break
        if rule_body is None:
            raise ValueError("rule_body_unavailable")

        new_version = self._catalog.create_new_version(
            rule_id=rule_id,
            rule_body=rule_body,
            effective_date=body.effective_date,
            approved_by=str(reviewer_user_id),
            source_file=source_file,
            source_references=[
                {
                    "source_id": proposal.source_id,
                    "url": proposal.source_url or "",
                    "authority": proposal.authority_level.value,
                }
            ],
        )

        # Also version the YAML file content if override provided (does not auto-invent).
        if body.rule_yaml_override and source_file:
            store = RuleVersionStore(self._rules_path)
            # Merge override into file carefully — only replace matching rule key
            current = yaml.safe_load(store.read_current(source_file)) or {}
            rules = current.get("rules") or {}
            replaced = False
            for key, data in list(rules.items()):
                if str(data.get("id")) == rule_id:
                    rules[key] = body.rule_yaml_override
                    replaced = True
                    break
            if replaced:
                current["rules"] = rules
                store.write_with_version(
                    filename=source_file,
                    content=yaml.safe_dump(current, allow_unicode=True, sort_keys=False),
                    reason=f"Approved legal proposal {proposal.proposal_id}",
                    actor_user_id=reviewer_user_id,
                )

        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.reviewed_by = str(reviewer_user_id)
        self._store.save_proposal(proposal)

        if self._audit:
            await self._audit.append(
                AuditLogEntry(
                    action="legal_proposal.approved_new_version",
                    resource_type="legal_change_proposal",
                    resource_id=None,
                    organization_id=None,
                    user_id=reviewer_user_id,
                    details={
                        "proposal_id": proposal.proposal_id,
                        "rule_id": rule_id,
                        "old_version": new_version.version - 1,
                        "new_version": new_version.version,
                        "valid_from": new_version.valid_from,
                        "source_id": proposal.source_id,
                        "source_hash": proposal.new_content_hash,
                    },
                )
            )

        if self._on_version_approved:
            await self._on_version_approved(rule_id, str(new_version.version))
        return proposal

    async def _approve_new_rule(
        self,
        proposal: LegalChangeProposal,
        body: ApproveProposalRequest,
        *,
        reviewer_user_id: UUID,
    ) -> LegalChangeProposal:
        from datetime import datetime, timezone

        if not body.new_rule_id or not body.new_rule_body:
            raise ValueError(
                "new_rule_requires_fields:new_rule_id,new_rule_body,effective_date,confirm_effective_date"
            )
        if body.new_rule_body.get("id") and body.new_rule_body.get("id") != body.new_rule_id:
            raise ValueError("new_rule_id_mismatch")
        body.new_rule_body["id"] = body.new_rule_id

        existing = self._catalog.get_active(body.new_rule_id)
        if existing is not None:
            raise ValueError("rule_already_exists")

        new_version = self._catalog.create_new_version(
            rule_id=body.new_rule_id,
            rule_body=body.new_rule_body,
            effective_date=body.effective_date,
            approved_by=str(reviewer_user_id),
            source_file="new_rules.yaml",
            source_references=[
                {
                    "source_id": proposal.source_id,
                    "url": proposal.source_url or "",
                    "authority": proposal.authority_level.value,
                }
            ],
        )

        # Persist as a new optional YAML file — does not remove existing packs.
        from pathlib import Path

        path = Path(self._rules_path) / "new_rules.yaml"
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        else:
            data = {
                "version": "2026.1.0",
                "effective_from": body.effective_date.isoformat(),
                "rules": {},
            }
        rules = data.setdefault("rules", {})
        key = body.new_rule_id.replace(".", "_")
        rules[key] = body.new_rule_body
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

        proposal.status = ProposalStatus.APPROVED
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.reviewed_by = str(reviewer_user_id)
        self._store.save_proposal(proposal)

        if self._audit:
            await self._audit.append(
                AuditLogEntry(
                    action="legal_proposal.approved_new_rule",
                    resource_type="legal_change_proposal",
                    resource_id=None,
                    organization_id=None,
                    user_id=reviewer_user_id,
                    details={
                        "proposal_id": proposal.proposal_id,
                        "rule_id": body.new_rule_id,
                        "version": new_version.version,
                        "valid_from": new_version.valid_from,
                    },
                )
            )
        if self._on_version_approved:
            await self._on_version_approved(body.new_rule_id, str(new_version.version))
        return proposal
