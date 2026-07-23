"""Safe tool adapters for the payroll assistant LangGraph agent."""

from __future__ import annotations

from payroll_copilot.application.ports.assistant import (
    ApprovedLaborLawSearchPort,
    DocumentSummaryPort,
    PayrollAssistantToolsPort,
    ValidationReportPort,
)
from payroll_copilot.domain.assistant.types import AssistantSource, AssistantSourceType, AssistantToolResult


class InMemoryDocumentSummaryStore(DocumentSummaryPort):
    """Guest-scoped document metadata store (placeholder until document service is wired)."""

    def __init__(self) -> None:
        self._documents: dict[str, dict[str, str]] = {}

    def register(self, document_id: str, *, session_id: str, summary: str, doc_type: str) -> None:
        self._documents[document_id] = {
            "session_id": session_id,
            "summary": summary,
            "document_type": doc_type,
        }

    def get_summaries(
        self,
        document_ids: list[str],
        *,
        session_id: str,
    ) -> list[dict[str, str]]:
        summaries: list[dict[str, str]] = []
        for document_id in document_ids:
            record = self._documents.get(document_id)
            if record is None or record["session_id"] != session_id:
                continue
            summaries.append(
                {
                    "document_id": document_id,
                    "document_type": record["document_type"],
                    "summary": record["summary"],
                }
            )
        return summaries


class PayrollAssistantTools(PayrollAssistantToolsPort):
    """Guest-safe assistant tools — never invent payroll or legal facts."""

    def __init__(
        self,
        labor_law_search: ApprovedLaborLawSearchPort,
        validation_reports: ValidationReportPort,
        document_summaries: DocumentSummaryPort,
    ) -> None:
        self._labor_law_search = labor_law_search
        self._validation_reports = validation_reports
        self._document_summaries = document_summaries
        # Set per request by the guest chat route when private IDs are present.
        self.request_owner_guest_id: str | None = None

    def set_request_owner(self, owner_guest_id: str | None) -> None:
        self.request_owner_guest_id = (owner_guest_id or "").strip() or None

    def search_approved_labor_law(self, query: str, *, locale: str = "en") -> AssistantToolResult:
        hits = self._labor_law_search.search(query, locale=locale)
        if not hits:
            return AssistantToolResult(
                tool_name="search_approved_labor_law",
                success=False,
                content="No matching labor-law reference was found for this question.",
                sources=[],
            )

        content_lines = [f"- {hit.title}: {hit.summary}" for hit in hits]
        sources = [
            AssistantSource(
                title=hit.title,
                type=AssistantSourceType.LEGAL_RULE,
                reference=hit.source_file,
            )
            for hit in hits
        ]
        return AssistantToolResult(
            tool_name="search_approved_labor_law",
            success=True,
            content="\n".join(content_lines),
            sources=sources,
        )

    def get_validation_report(self, validation_run_id: str | None) -> AssistantToolResult:
        if not validation_run_id:
            return AssistantToolResult(
                tool_name="get_validation_report",
                success=False,
                content="Validation report unavailable. No validation_run_id was provided.",
            )

        report = self._validation_reports.get_report(
            validation_run_id,
            owner_guest_id=self.request_owner_guest_id,
        )
        if report is None:
            return AssistantToolResult(
                tool_name="get_validation_report",
                success=False,
                content=(
                    f"Validation report '{validation_run_id}' was not found. "
                    "Run deterministic validation first."
                ),
            )

        findings = report.get("findings", [])
        content = (
            f"Deterministic validation report {validation_run_id} "
            f"with status '{report.get('status')}' and {len(findings)} findings."
        )
        return AssistantToolResult(
            tool_name="get_validation_report",
            success=True,
            content=content,
            sources=[
                AssistantSource(
                    title=f"Validation report {validation_run_id}",
                    type=AssistantSourceType.VALIDATION_REPORT,
                    reference=validation_run_id,
                )
            ],
        )

    def get_uploaded_document_summary(
        self,
        document_ids: list[str],
        *,
        session_id: str,
    ) -> AssistantToolResult:
        if not document_ids:
            return AssistantToolResult(
                tool_name="get_uploaded_document_summary",
                success=False,
                content="No document_ids were provided for this session.",
            )

        summaries = self._document_summaries.get_summaries(document_ids, session_id=session_id)
        if not summaries:
            return AssistantToolResult(
                tool_name="get_uploaded_document_summary",
                success=False,
                content="No approved document summaries are available for the provided document IDs.",
            )

        content_lines = [
            f"- {item['document_id']} ({item['document_type']}): {item['summary']}"
            for item in summaries
        ]
        sources = [
            AssistantSource(
                title=f"Document {item['document_id']}",
                type=AssistantSourceType.DOCUMENT,
                reference=item["document_id"],
            )
            for item in summaries
        ]
        return AssistantToolResult(
            tool_name="get_uploaded_document_summary",
            success=True,
            content="\n".join(content_lines),
            sources=sources,
        )

    def explain_validation_finding(
        self,
        validation_run_id: str | None,
        finding_rule_id: str | None,
    ) -> AssistantToolResult:
        report_result = self.get_validation_report(validation_run_id)
        if not report_result.success:
            return AssistantToolResult(
                tool_name="explain_validation_finding",
                success=False,
                content=report_result.content,
            )

        report = self._validation_reports.get_report(
            validation_run_id or "",
            owner_guest_id=self.request_owner_guest_id,
        )
        findings = report.get("findings", []) if report else []
        if finding_rule_id:
            findings = [f for f in findings if f.get("rule_id") == finding_rule_id]

        if not findings:
            return AssistantToolResult(
                tool_name="explain_validation_finding",
                success=False,
                content="No deterministic findings are available to explain.",
                requires_human_review=True,
            )

        lines = [
            (
                f"- Finding {item.get('rule_id')}: severity={item.get('severity')}, "
                f"message_key={item.get('message_key')}, "
                f"expected={item.get('expected_value')}, actual={item.get('actual_value')}"
            )
            for item in findings
        ]
        return AssistantToolResult(
            tool_name="explain_validation_finding",
            success=True,
            content="Existing deterministic findings:\n" + "\n".join(lines),
            sources=report_result.sources,
            requires_human_review=True,
        )

    def fallback_safe_response(self, reason: str) -> AssistantToolResult:
        return AssistantToolResult(
            tool_name="fallback_safe_response",
            success=True,
            content=reason,
            sources=[
                AssistantSource(
                    title="Payroll Copilot assistant policy",
                    type=AssistantSourceType.SYSTEM,
                )
            ],
        )
