"""Employee-owned on-demand explanation for a deterministic validation finding."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from payroll_copilot.application.exceptions import DocumentNotOwnedError
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository
from payroll_copilot.application.ports.repositories import (
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import FindingSeverity


class FindingNotFoundError(Exception):
    def __init__(self, finding_id: UUID) -> None:
        self.finding_id = finding_id
        self.code = "finding_not_found"
        super().__init__(f"Finding {finding_id} not found")


class ValidationRunNotFoundError(Exception):
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self.code = "validation_run_not_found"
        super().__init__(f"Validation run {run_id} not found")


class ExplainEmployeeFindingUseCase:
    """Explain a finding using only persisted deterministic data (AI assist, never pass/fail)."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        validation_runs: ValidationRunRepository,
        validation_findings: ValidationFindingRepository,
        audit_logs: AuditLogRepository | None = None,
        assistant_runner: Any | None = None,
    ) -> None:
        self._documents = documents
        self._runs = validation_runs
        self._findings = validation_findings
        self._audit = audit_logs
        self._assistant = assistant_runner

    async def execute(
        self,
        *,
        employee: Employee,
        user_id: UUID,
        validation_run_id: UUID,
        finding_id: UUID,
        locale: str = "en",
    ) -> dict[str, Any]:
        run = await self._runs.get_by_id(validation_run_id)
        if run is None:
            raise ValidationRunNotFoundError(validation_run_id)

        document = await self._documents.get_by_id(run.document_id)
        if document is None:
            raise ValidationRunNotFoundError(validation_run_id)
        owned = (
            document.employee_id == employee.id
            and document.organization_id == employee.organization_id
        ) or (run.employee_id is not None and run.employee_id == employee.id)
        if not owned:
            raise DocumentNotOwnedError(run.document_id)

        findings = await self._findings.list_by_run_id(validation_run_id)
        finding = next((f for f in findings if f.id == finding_id), None)
        if finding is None:
            raise FindingNotFoundError(finding_id)

        severity = (
            finding.severity.value
            if hasattr(finding.severity, "value")
            else str(finding.severity)
        )
        status_map = {
            FindingSeverity.CRITICAL.value: "failed",
            FindingSeverity.WARNING.value: "warning",
            FindingSeverity.INFO.value: "info",
        }
        validation_status = status_map.get(severity, severity)

        # Green/info simple findings: policy allows limited or no AI by default.
        if severity == FindingSeverity.INFO.value:
            result = {
                "finding_id": str(finding.id),
                "validation_status": validation_status,
                "explanation_status": "not_applicable",
                "explanation": None,
                "recommended_action": None,
                "sources": [],
                "disclaimer_key": "employee.validation.aiExplanationDisclaimer",
            }
            await self._audit_event(employee, user_id, finding.id, result["explanation_status"])
            return result

        deterministic_summary = self._deterministic_summary(finding)
        sources: list[dict[str, str | None]] = []
        if finding.legal_reference:
            sources.append(
                {
                    "source_type": "labor_law_rule",
                    "source_id": finding.rule_id,
                    "title": finding.legal_reference,
                }
            )

        explanation = deterministic_summary
        recommended = self._recommended_action(finding, severity)
        explanation_status = "generated_from_finding"

        if self._assistant is not None:
            try:
                payload = await self._assistant.run(
                    message=(
                        "Explain this existing deterministic validation finding in plain language. "
                        "Do not change the result. Do not invent legal requirements or values. "
                        f"rule_id={finding.rule_id}; message_key={finding.message_key}; "
                        f"severity={severity}; expected={finding.expected_value}; "
                        f"actual={finding.actual_value}; legal_reference={finding.legal_reference}."
                    ),
                    session_id=f"employee-explain-{finding.id}",
                    document_ids=[str(run.document_id)],
                    validation_run_id=str(validation_run_id),
                    locale=locale,
                )
                answer = str(payload.get("answer") or "").strip()
                if answer:
                    explanation = answer
                    explanation_status = "generated"
                    for src in payload.get("sources") or []:
                        if isinstance(src, dict):
                            sources.append(
                                {
                                    "source_type": str(src.get("type") or src.get("source_type") or "assistant"),
                                    "source_id": str(src.get("id") or src.get("source_id") or ""),
                                    "title": src.get("title"),
                                }
                            )
            except Exception:  # noqa: BLE001 — AI optional; deterministic UX must remain
                explanation_status = "ai_unavailable"
                explanation = deterministic_summary

        result = {
            "finding_id": str(finding.id),
            "validation_status": validation_status,
            "explanation_status": explanation_status,
            "explanation": explanation,
            "recommended_action": recommended,
            "sources": sources,
            "disclaimer_key": "employee.validation.aiExplanationDisclaimer",
        }
        await self._audit_event(employee, user_id, finding.id, explanation_status)
        return result

    def _deterministic_summary(self, finding: Any) -> str:
        parts = [
            f"Check: {finding.message_key}",
            f"Status: {finding.severity.value if hasattr(finding.severity, 'value') else finding.severity}",
        ]
        if finding.expected_value is not None:
            parts.append(f"Expected: {finding.expected_value}")
        if finding.actual_value is not None:
            parts.append(f"Actual: {finding.actual_value}")
        if finding.legal_reference:
            parts.append(f"Rule reference: {finding.legal_reference}")
        return " | ".join(parts)

    def _recommended_action(self, finding: Any, severity: str) -> str:
        if finding.actual_value in (None, "", "missing") or "missing" in (
            finding.message_key or ""
        ).lower():
            return "Upload or complete the missing document or field, then confirm extraction and rerun validation."
        if severity == FindingSeverity.CRITICAL.value:
            return "Review the compared values, correct confirmed payslip fields if needed, then rerun validation."
        return "Review the warning details and confirm whether a correction or supporting document is required."

    async def _audit_event(
        self,
        employee: Employee,
        user_id: UUID,
        finding_id: UUID,
        explanation_status: str,
    ) -> None:
        if self._audit is None:
            return
        await self._audit.append(
            AuditLogEntry(
                action="employee_finding_explanation_requested",
                resource_type="validation_finding",
                resource_id=finding_id,
                organization_id=employee.organization_id,
                user_id=user_id,
                details={
                    "event": "finding_explanation",
                    "explanation_status": explanation_status,
                },
            )
        )
