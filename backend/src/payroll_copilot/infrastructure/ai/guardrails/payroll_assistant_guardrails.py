"""Layered guardrails for the public payroll assistant."""

from __future__ import annotations

import re
from dataclasses import dataclass

from payroll_copilot.domain.assistant.types import AssistantGuardrailStatus
from payroll_copilot.infrastructure.i18n import assistant_text

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

# Broad in-domain payroll / employee-rights intent (EN/HE/AR).
_PAYROLL_TOPIC_KEYWORDS = (
    "payroll",
    "payslip",
    "pay slip",
    "paystub",
    "pay stub",
    "salary",
    "wage",
    "wages",
    "minimum wage",
    "overtime",
    "vacation",
    "holiday",
    "sick",
    "leave",
    "pension",
    "tax",
    "taxes",
    "deduction",
    "deductions",
    "travel",
    "transportation",
    "expense",
    "expenses",
    "attendance",
    "contract",
    "employment",
    "labor",
    "labour",
    "employee",
    "employer",
    "employee-rights",
    "employee rights",
    "validation",
    "validate",
    "warning",
    "critical",
    "finding",
    "findings",
    "issue",
    "upload",
    "document",
    "documents",
    "nis",
    "ils",
    "שכר",
    "תלוש",
    "שעות נוספות",
    "חופשה",
    "מחלה",
    "פנסיה",
    "מס",
    "ניכוי",
    "ניכויים",
    "נסיעות",
    "בדיקה",
    "אזהרה",
    "קריטי",
    "מסמך",
    "מסמכים",
    "راتب",
    "رواتب",
    "كشف راتب",
    "ساعات إضافية",
    "إجازة",
    "مرض",
    "تقاعد",
    "ضريبة",
    "خصم",
    "مستند",
    "مستندات",
    "تحذير",
    "حرج",
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
    "required",
    "must",
    "eligib",
    "חוק",
    "זכות",
    "חובה",
    "قانون",
    "حق",
    "حقوق",
)

_GREETING_EXACT = {
    "hi", "hii", "hiya", "hello", "helo", "hey", "heya",
    "thanks", "thankyou", "thank you", "thank u", "thx", "ty",
    "shalom", "שלום", "היי", "הי", "תודה", "תודה רבה",
    "مرحبا", "أهلا", "اهلا", "السلام عليكم", "شكرا", "شكراً",
}

_GREETING_LEADING = (
    "hello", "hiya", "heya", "hey", "hi",
    "thank you", "thank u", "thanks", "thx", "ty",
    "shalom", "שלום", "היי", "הי", "תודה",
    "مرحبا", "أهلا", "اهلا", "السلام عليكم",
)


@dataclass(frozen=True, slots=True)
class InputGuardrailResult:
    status: AssistantGuardrailStatus
    reason: str | None = None
    is_legal_rights_question: bool = False
    is_validation_question: bool = False
    is_document_question: bool = False
    is_greeting: bool = False
    in_domain_intent: str | None = None


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
                status=AssistantGuardrailStatus.BLOCKED_SAFETY,
                reason="empty_message",
            )

        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, normalized):
                return InputGuardrailResult(
                    status=AssistantGuardrailStatus.BLOCKED_SAFETY,
                    reason="prompt_injection",
                )

        if self._is_greeting(normalized):
            return InputGuardrailResult(
                status=AssistantGuardrailStatus.PASSED,
                is_greeting=True,
            )

        if not self._is_payroll_related(normalized):
            return InputGuardrailResult(
                status=AssistantGuardrailStatus.BLOCKED_OFF_TOPIC,
                reason="off_topic",
            )

        return InputGuardrailResult(
            status=AssistantGuardrailStatus.PASSED,
            is_legal_rights_question=self._is_legal_rights_question(normalized),
            is_validation_question=self._mentions_validation(normalized),
            is_document_question=self._mentions_documents(normalized),
            in_domain_intent=self._classify_in_domain_intent(normalized),
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
                return AssistantGuardrailStatus.BLOCKED_SAFETY
        return AssistantGuardrailStatus.PASSED

    def build_limited_legal_response(
        self,
        *,
        locale: str = "en",
        intent: str | None = None,
    ) -> OutputGuardrailResult:
        """Helpful in-domain guidance when no exact approved source is available."""
        key = {
            "documents_needed": "limited_documents_needed",
            "overtime_payslip": "limited_overtime_payslip",
            "warning_vs_critical": "limited_warning_vs_critical",
        }.get(intent or "", "limited_full")
        return OutputGuardrailResult(
            status=AssistantGuardrailStatus.LIMITED_IN_DOMAIN,
            answer=assistant_text(key, locale),
            requires_human_review=True,
        )

    def build_blocked_response(self, reason: str, *, locale: str = "en") -> OutputGuardrailResult:
        key_by_reason = {
            "prompt_injection": "blocked_prompt_injection",
            "off_topic": "blocked_off_topic",
            "empty_message": "blocked_empty",
        }
        if reason == "off_topic":
            status = AssistantGuardrailStatus.BLOCKED_OFF_TOPIC
        else:
            status = AssistantGuardrailStatus.BLOCKED_SAFETY
        answer = assistant_text(key_by_reason.get(reason, "blocked_generic"), locale)
        return OutputGuardrailResult(
            status=status,
            answer=answer,
            requires_human_review=False,
        )

    def evaluate_output(
        self,
        answer: str,
        *,
        sources: list[dict[str, str | None]],
        made_legal_claim: bool,
        locale: str = "en",
        intent: str | None = None,
    ) -> OutputGuardrailResult:
        # Missing sources is an in-domain limitation, not an unsafe outcome.
        if not sources and made_legal_claim:
            return self.build_limited_legal_response(locale=locale, intent=intent)

        if sources:
            disclaimer = assistant_text("disclaimer", locale)
            final_answer = answer if disclaimer.strip() in answer else f"{answer}{disclaimer}"
            return OutputGuardrailResult(
                status=AssistantGuardrailStatus.ANSWERED_FROM_SOURCE,
                answer=final_answer,
                requires_human_review=False,
            )

        disclaimer = assistant_text("disclaimer", locale)
        final_answer = answer if disclaimer.strip() in answer else f"{answer}{disclaimer}"
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
            for token in (
                "validation",
                "validate",
                "finding",
                "findings",
                "violation",
                "compliance",
                "warning",
                "critical",
                "בדיקה",
                "אזהרה",
                "קריטי",
                "تحقق",
                "تحذير",
                "حرج",
            )
        )

    @staticmethod
    def _mentions_documents(normalized: str) -> bool:
        return any(
            token in normalized
            for token in (
                "document",
                "documents",
                "upload",
                "file",
                "needed",
                "require",
                "required",
                "מסמך",
                "מסמכים",
                "העלה",
                "נדרש",
                "مستند",
                "مستندات",
                "رفع",
            )
        )

    @staticmethod
    def _classify_in_domain_intent(normalized: str) -> str | None:
        docs = any(
            token in normalized
            for token in ("document", "documents", "מסמך", "מסמכים", "مستند", "مستندات", "needed", "נדרש")
        )
        validate = any(
            token in normalized for token in ("validate", "validation", "בדיקה", "تحقق", "payslip", "תלוש", "كشف")
        )
        if docs and validate:
            return "documents_needed"

        if any(token in normalized for token in ("overtime", "שעות נוספות", "ساعات إضافية")) and any(
            token in normalized for token in ("payslip", "pay stub", "paystub", "תלוש", "كشف", "reflect", "appear")
        ):
            return "overtime_payslip"

        if any(token in normalized for token in ("warning", "אזהרה", "تحذير")) and any(
            token in normalized for token in ("critical", "קריטי", "حرج")
        ):
            return "warning_vs_critical"

        return None
