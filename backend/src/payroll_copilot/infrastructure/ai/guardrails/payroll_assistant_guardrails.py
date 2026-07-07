"""Layered guardrails for the public payroll assistant."""

from __future__ import annotations

import re
from dataclasses import dataclass

from payroll_copilot.domain.assistant.types import AssistantGuardrailStatus

_INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(your|the)\s+(instructions|rules|policy)",
    r"reveal\s+(your\s+)?(system\s+prompt|hidden\s+instructions|secrets?)",
    r"show\s+(me\s+)?(the\s+)?(system\s+prompt|source\s+code|env|environment)",
    r"jailbreak",
    r"developer\s+mode",
    r"you\s+are\s+now\s+",
    r"pretend\s+you\s+are",
    r"bypass\s+(guardrails|safety|rules)",
)

_PAYROLL_TOPIC_KEYWORDS = (
    "payroll",
    "payslip",
    "salary",
    "wage",
    "minimum wage",
    "overtime",
    "vacation",
    "holiday",
    "sick",
    "leave",
    "pension",
    "tax",
    "transportation",
    "attendance",
    "contract",
    "employment",
    "labor",
    "labour",
    "employee",
    "employer",
    "validation",
    "finding",
    "upload",
    "document",
    "nis",
    "ils",
    "שכר",
    "תלוש",
    "חופשה",
    "מחלה",
    "פנסיה",
)

_LEGAL_RIGHTS_KEYWORDS = (
    "right",
    "rights",
    "law",
    "legal",
    "entitled",
    "entitlement",
    "regulation",
    "minimum",
    "allowed",
    "require",
    "must",
    "חוק",
    "זכות",
    "חובה",
)

_GREETING_EXACT = {
    "hi", "hii", "hiya", "hello", "helo", "hey", "heya",
    "thanks", "thankyou", "thank you", "thank u", "thx", "ty",
    "shalom", "שלום", "היי", "הי", "תודה", "תודה רבה",
}

_GREETING_LEADING = (
    "hello", "hiya", "heya", "hey", "hi",
    "thank you", "thank u", "thanks", "thx", "ty",
    "shalom", "שלום", "היי", "הי", "תודה",
)


@dataclass(frozen=True, slots=True)
class InputGuardrailResult:
    status: AssistantGuardrailStatus
    reason: str | None = None
    is_legal_rights_question: bool = False
    is_validation_question: bool = False
    is_document_question: bool = False
    is_greeting: bool = False


@dataclass(frozen=True, slots=True)
class OutputGuardrailResult:
    status: AssistantGuardrailStatus
    answer: str
    requires_human_review: bool = False


class PayrollAssistantGuardrails:
    """Input, tool-scope, RAG, and output guardrails."""

    def evaluate_input(self, message: str) -> InputGuardrailResult:
        normalized = message.strip().lower()
        if not normalized:
            return InputGuardrailResult(
                status=AssistantGuardrailStatus.BLOCKED,
                reason="empty_message",
            )

        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, normalized):
                return InputGuardrailResult(
                    status=AssistantGuardrailStatus.BLOCKED,
                    reason="prompt_injection",
                )

        if self._is_greeting(normalized):
            return InputGuardrailResult(
                status=AssistantGuardrailStatus.PASSED,
                is_greeting=True,
            )

        if not self._is_payroll_related(normalized):
            return InputGuardrailResult(
                status=AssistantGuardrailStatus.BLOCKED,
                reason="off_topic",
            )

        return InputGuardrailResult(
            status=AssistantGuardrailStatus.PASSED,
            is_legal_rights_question=self._is_legal_rights_question(normalized),
            is_validation_question=self._mentions_validation(normalized),
            is_document_question=self._mentions_documents(normalized),
        )

    def evaluate_tool_scope(
        self,
        *,
        document_ids: list[str],
        validation_run_id: str | None,
        requested_document_ids: list[str] | None = None,
    ) -> AssistantGuardrailStatus:
        if requested_document_ids:
            unknown = set(requested_document_ids) - set(document_ids)
            if unknown:
                return AssistantGuardrailStatus.BLOCKED
        return AssistantGuardrailStatus.PASSED

    def build_limited_legal_response(self) -> OutputGuardrailResult:
        return OutputGuardrailResult(
            status=AssistantGuardrailStatus.LIMITED,
            answer=(
                "I could not find this in the approved Payroll Copilot knowledge base. "
                "I can only answer labor-law and payroll-rights questions using approved "
                "local rule sources. Deterministic pass/fail validation is performed "
                "separately by the backend rule engine — not by this assistant."
            ),
            requires_human_review=True,
        )

    def build_blocked_response(self, reason: str) -> OutputGuardrailResult:
        messages = {
            "prompt_injection": (
                "I cannot process that request. I am limited to payroll, payslip, and "
                "labor-law assistance using approved sources."
            ),
            "off_topic": (
                "I can only help with payroll, payslips, attendance, contracts, labor law, "
                "and Payroll Copilot usage."
            ),
            "empty_message": "Please enter a payroll-related question.",
        }
        return OutputGuardrailResult(
            status=AssistantGuardrailStatus.BLOCKED,
            answer=messages.get(reason, "I cannot process that request."),
            requires_human_review=False,
        )

    def evaluate_output(
        self,
        answer: str,
        *,
        sources: list[dict[str, str | None]],
        made_legal_claim: bool,
    ) -> OutputGuardrailResult:
        if made_legal_claim and not sources:
            return self.build_limited_legal_response()

        disclaimer = (
            "\n\nThis assistant provides informational explanations only and does not "
            "determine legal compliance. Final validation is performed by the "
            "deterministic Payroll Copilot rule engine."
        )
        final_answer = answer if disclaimer in answer else f"{answer}{disclaimer}"
        return OutputGuardrailResult(
            status=AssistantGuardrailStatus.PASSED,
            answer=final_answer,
            requires_human_review=False,
        )

    @staticmethod
    def _is_payroll_related(normalized: str) -> bool:
        return any(keyword in normalized for keyword in _PAYROLL_TOPIC_KEYWORDS)

    @staticmethod
    def _is_greeting(normalized: str) -> bool:
        cleaned = normalized.strip().strip("!.,?-").strip()
        if not cleaned:
            return False
        if cleaned in _GREETING_EXACT:
            return True
        if len(cleaned.split()) > 4:
            return False
        return any(
            cleaned == lead or cleaned.startswith(lead + " ")
            for lead in _GREETING_LEADING
        )

    @staticmethod
    def _is_legal_rights_question(normalized: str) -> bool:
        return any(keyword in normalized for keyword in _LEGAL_RIGHTS_KEYWORDS)

    @staticmethod
    def _mentions_validation(normalized: str) -> bool:
        return any(
            token in normalized
            for token in ("validation", "finding", "findings", "violation", "compliance result")
        )

    @staticmethod
    def _mentions_documents(normalized: str) -> bool:
        return any(token in normalized for token in ("document", "upload", "file", "payslip pdf"))
