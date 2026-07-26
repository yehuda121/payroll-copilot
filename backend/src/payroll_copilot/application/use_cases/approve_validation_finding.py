"""Manual approval (override) layer for validation findings.

Does not rewrite deterministic FAIL into PASS. Stores an audit override that
the UI may display as MANUALLY_APPROVED (green) while retaining the original
finding severity/values on the ValidationRun.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.exceptions import DocumentNotFoundError, DocumentNotOwnedError
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository
from payroll_copilot.application.ports.repositories import DocumentRepository, ValidationFindingRepository, ValidationRunRepository
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import FindingSeverity, UserRole


class ManualApprovalError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True, slots=True)
class ManualApprovalRecord:
    finding_id: str
    rule_id: str
    original_severity: str
    approved_by: str
    approved_at: str
    reason: str | None
    validation_run_id: str
    role: str


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
            "uncertain",
        }:
            row["display_status"] = "manually_approved"
            row["manual_approval"] = approval
        else:
            row["display_status"] = severity or "unchecked"
        out.append(row)
    return out


class ApproveValidationFindingUseCase:
    """Authorize employee (own) or accountant override for a finding."""

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

        record = ManualApprovalRecord(
            finding_id=str(finding.id),
            rule_id=finding.rule_id,
            original_severity=finding.severity.value,
            approved_by=str(actor_user_id),
            approved_at=_utcnow().isoformat(),
            reason=(reason or "").strip() or None,
            validation_run_id=str(validation_run_id),
            role=role_value,
        )

        meta = dict(document.metadata or {})
        approvals = approvals_from_document_metadata(meta)
        approvals = [
            a
            for a in approvals
            if str(a.get("finding_id")) != record.finding_id
        ]
        approvals.append(
            {
                "finding_id": record.finding_id,
                "rule_id": record.rule_id,
                "original_severity": record.original_severity,
                "approved_by": record.approved_by,
                "approved_at": record.approved_at,
                "reason": record.reason,
                "validation_run_id": record.validation_run_id,
                "role": record.role,
            }
        )
        meta["manual_approvals"] = approvals
        document.metadata = meta
        await self._documents.save(document)

        if self._audit is not None:
            await self._audit.append(
                AuditLogEntry(
                    action="validation_finding_manually_approved",
                    resource_type="validation_finding",
                    resource_id=finding.id,
                    organization_id=employee.organization_id,
                    user_id=actor_user_id,
                    details={
                        "document_id": str(document_id),
                        "validation_run_id": str(validation_run_id),
                        "rule_id": finding.rule_id,
                        "original_severity": finding.severity.value,
                        "reason": record.reason,
                    },
                )
            )

        return {
            "document_id": str(document_id),
            "validation_run_id": str(validation_run_id),
            "finding_id": str(finding_id),
            "manual_approval": approvals[-1],
            "original_severity": finding.severity.value,
        }

