"""Manual approval (override) layer for validation findings/checks.

Does not rewrite deterministic FAIL into PASS. Stores an audit override that
the UI may display as MANUALLY_APPROVED while retaining the original
deterministic outcome on the ValidationRun / rule_outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from payroll_copilot.application.exceptions import DocumentNotFoundError, DocumentNotOwnedError
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository
from payroll_copilot.application.ports.repositories import (
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import FindingSeverity, UserRole

REASON_MAX_LEN = 500
APPROVABLE_DETERMINISTIC = frozenset({"failed", "uncertain", "not_run", "skipped"})


class ManualApprovalError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_reason(reason: str | None, *, required: bool) -> str | None:
    cleaned = (reason or "").strip()
    if required and not cleaned:
        raise ManualApprovalError(
            "approval_reason_required",
            "A short reason is required to manually approve this check.",
        )
    if len(cleaned) > REASON_MAX_LEN:
        raise ManualApprovalError(
            "approval_reason_too_long",
            f"Reason must be at most {REASON_MAX_LEN} characters.",
        )
    return cleaned or None


@dataclass(frozen=True, slots=True)
class ManualApprovalRecord:
    finding_id: str | None
    rule_id: str
    original_severity: str | None
    original_deterministic_status: str
    approved_by: str
    approved_at: str
    reason: str | None
    validation_run_id: str
    role: str
    review_status: str = "manually_approved"


def approvals_from_document_metadata(metadata: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw = (metadata or {}).get("manual_approvals")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def apply_approvals_to_display(
    *,
    findings: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Annotate finding dicts with display_status without mutating severity."""
    by_finding = {str(a.get("finding_id")): a for a in approvals if a.get("finding_id")}
    by_rule = {str(a.get("rule_id")): a for a in approvals if a.get("rule_id")}
    out: list[dict[str, Any]] = []
    for finding in findings:
        row = dict(finding)
        approval = by_finding.get(str(row.get("id"))) or by_rule.get(str(row.get("rule_id")))
        severity = str(row.get("severity") or "").lower()
        if approval and severity in {
            FindingSeverity.WARNING.value,
            FindingSeverity.CRITICAL.value,
            FindingSeverity.INFO.value,
            "uncertain",
        }:
            row["display_status"] = "manually_approved"
            row["manual_approval"] = approval
        else:
            row["display_status"] = severity or "unchecked"
        out.append(row)
    return out


def approval_for_rule(
    approvals: list[dict[str, Any]],
    rule_id: str,
) -> dict[str, Any] | None:
    rid = (rule_id or "").strip()
    if not rid:
        return None
    for row in approvals:
        if str(row.get("rule_id") or "").strip() == rid and not row.get("revoked_at"):
            return row
    return None


class ApproveValidationFindingUseCase:
    """Authorize employee (own finding) or accountant check-level override."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        validation_runs: ValidationRunRepository,
        validation_findings: ValidationFindingRepository | None = None,
        audit_logs: AuditLogRepository | None = None,
    ) -> None:
        self._documents = documents
        self._runs = validation_runs
        self._findings = validation_findings
        self._audit = audit_logs

    async def execute(
        self,
        *,
        document_id: UUID,
        validation_run_id: UUID,
        finding_id: UUID,
        employee: Employee,
        actor_user_id: UUID,
        actor_role: UserRole | str,
        acknowledgement: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Legacy finding-based approval (employee/accountant). Deterministic severity preserved."""
        if not acknowledgement:
            raise ManualApprovalError(
                "approval_acknowledgement_required",
                "Explicit acknowledgement of override risk is required.",
            )

        role_value = actor_role.value if isinstance(actor_role, UserRole) else str(actor_role)
        if role_value not in {UserRole.EMPLOYEE.value, UserRole.ACCOUNTANT.value, UserRole.ADMIN.value}:
            raise ManualApprovalError(
                "approval_forbidden",
                "This role cannot manually approve validation findings.",
            )

        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if document.employee_id != employee.id or document.organization_id != employee.organization_id:
            raise DocumentNotOwnedError(document_id)

        run = await self._runs.get_by_id(validation_run_id)
        if run is None or run.document_id != document_id:
            raise ManualApprovalError("validation_run_not_found", "Validation run not found.")

        findings = list(run.findings or [])
        if not findings and self._findings is not None:
            findings = await self._findings.list_by_run_id(validation_run_id)
        finding = next((f for f in findings if f.id == finding_id), None)
        if finding is None:
            raise ManualApprovalError("finding_not_found", "Finding not found on validation run.")

        if finding.severity not in {FindingSeverity.WARNING, FindingSeverity.CRITICAL}:
            raise ManualApprovalError(
                "finding_not_eligible",
                "Only failed or uncertain (warning/critical) findings can be approved.",
            )

        cleaned_reason = _normalize_reason(reason, required=False)
        approval = {
            "finding_id": str(finding.id),
            "rule_id": finding.rule_id,
            "original_severity": finding.severity.value,
            "original_deterministic_status": "failed",
            "deterministic_status": "failed",
            "review_status": "manually_approved",
            "approved_by": str(actor_user_id),
            "approved_at": _utcnow().isoformat(),
            "reason": cleaned_reason,
            "validation_run_id": str(validation_run_id),
            "role": role_value,
        }
        await self._persist_approval(
            document=document,
            approval=approval,
            organization_id=employee.organization_id,
            actor_user_id=actor_user_id,
            audit_action="validation.manual_approval_created",
        )
        return {
            "document_id": str(document_id),
            "validation_run_id": str(validation_run_id),
            "finding_id": str(finding_id),
            "rule_id": finding.rule_id,
            "manual_approval": approval,
            "original_severity": finding.severity.value,
            "deterministic_status": "failed",
            "review_status": "manually_approved",
        }

    async def execute_check(
        self,
        *,
        document_id: UUID,
        validation_run_id: UUID,
        rule_id: str,
        finding_id: UUID | None,
        organization_id: UUID,
        actor_user_id: UUID,
        actor_role: UserRole | str,
        acknowledgement: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Accountant/admin check-level approval. Never rewrites deterministic outcome."""
        if not acknowledgement:
            raise ManualApprovalError(
                "approval_acknowledgement_required",
                "Explicit acknowledgement of override risk is required.",
            )

        role_value = actor_role.value if isinstance(actor_role, UserRole) else str(actor_role)
        if role_value not in {UserRole.ACCOUNTANT.value, UserRole.ADMIN.value}:
            raise ManualApprovalError(
                "approval_forbidden",
                "Only accountants may create compliance manual approvals for checks.",
            )

        rid = (rule_id or "").strip()
        if not rid:
            raise ManualApprovalError("rule_id_required", "rule_id is required.")

        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if document.organization_id != organization_id:
            raise DocumentNotOwnedError(document_id)

        run = await self._runs.get_by_id(validation_run_id)
        if run is None or run.document_id != document_id:
            raise ManualApprovalError("validation_run_not_found", "Validation run not found.")

        outcomes = list((run.context_snapshot or {}).get("rule_outcomes") or [])
        outcome_row = next(
            (
                row
                for row in outcomes
                if isinstance(row, dict) and str(row.get("rule_id") or "").strip() == rid
            ),
            None,
        )
        deterministic = str((outcome_row or {}).get("outcome") or "").strip().lower()
        if deterministic == "skipped":
            deterministic = "not_run"
        if deterministic == "passed":
            # Allow approval for consistency but require reason; never change deterministic.
            pass
        elif deterministic not in APPROVABLE_DETERMINISTIC and finding_id is None:
            raise ManualApprovalError(
                "check_not_eligible",
                "Only FAILED, UNCERTAIN, or NOT_RUN checks can be manually approved.",
            )

        findings = list(run.findings or [])
        if not findings and self._findings is not None:
            findings = await self._findings.list_by_run_id(validation_run_id)
        finding = None
        if finding_id is not None:
            finding = next((f for f in findings if f.id == finding_id), None)
            if finding is None:
                raise ManualApprovalError("finding_not_found", "Finding not found on validation run.")
            if finding.rule_id != rid:
                raise ManualApprovalError("finding_rule_mismatch", "Finding does not match rule_id.")
        else:
            finding = next((f for f in findings if f.rule_id == rid), None)

        if not deterministic:
            if finding and finding.severity in {FindingSeverity.WARNING, FindingSeverity.CRITICAL}:
                deterministic = "failed"
            elif finding and finding.severity == FindingSeverity.INFO:
                deterministic = "uncertain"
            else:
                deterministic = "not_run"

        cleaned_reason = _normalize_reason(
            reason,
            required=deterministic in APPROVABLE_DETERMINISTIC,
        )

        approval = {
            "finding_id": str(finding.id) if finding else None,
            "rule_id": rid,
            "original_severity": finding.severity.value if finding else None,
            "original_deterministic_status": deterministic,
            "deterministic_status": deterministic,
            "review_status": "manually_approved",
            "approved_by": str(actor_user_id),
            "approved_at": _utcnow().isoformat(),
            "reason": cleaned_reason,
            "validation_run_id": str(validation_run_id),
            "role": role_value,
        }
        await self._persist_approval(
            document=document,
            approval=approval,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            audit_action="validation.manual_approval_created",
        )
        return {
            "document_id": str(document_id),
            "validation_run_id": str(validation_run_id),
            "finding_id": str(finding.id) if finding else None,
            "rule_id": rid,
            "manual_approval": approval,
            "deterministic_status": deterministic,
            "review_status": "manually_approved",
        }

    async def _persist_approval(
        self,
        *,
        document,
        approval: dict[str, Any],
        organization_id: UUID,
        actor_user_id: UUID,
        audit_action: str,
    ) -> None:
        meta = dict(document.metadata or {})
        approvals = approvals_from_document_metadata(meta)
        # Idempotent replace for same rule_id (and finding_id when present).
        approvals = [
            a
            for a in approvals
            if not (
                str(a.get("rule_id") or "") == approval["rule_id"]
                and (
                    not approval.get("finding_id")
                    or str(a.get("finding_id") or "") == str(approval.get("finding_id"))
                )
            )
        ]
        approvals.append(approval)
        meta["manual_approvals"] = approvals
        document.metadata = meta
        await self._documents.save(document)

        if self._audit is not None:
            await self._audit.append(
                AuditLogEntry(
                    action=audit_action,
                    resource_type="validation_check",
                    resource_id=UUID(approval["validation_run_id"]),
                    organization_id=organization_id,
                    user_id=actor_user_id,
                    details={
                        "document_id": str(document.id),
                        "validation_run_id": approval["validation_run_id"],
                        "rule_id": approval["rule_id"],
                        "deterministic_status": approval.get("deterministic_status"),
                        "review_status": approval.get("review_status"),
                        "reason_present": bool(approval.get("reason")),
                    },
                )
            )
