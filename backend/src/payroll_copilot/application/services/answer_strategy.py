"""Lightweight answer strategy — decides answer type and context needs only.

Reuses existing intent detection (`analyze_employee_context_intent`) and shared
assistant intent helpers. Does not generate text or replace prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from payroll_copilot.application.services.assistant_intent import (
    contains_any,
    is_personal_payroll_message,
    parse_message_period,
)
from payroll_copilot.application.services.employee_ai_context_builder import (
    EmployeeContextIntent,
    analyze_employee_context_intent,
)

_CALCULATION_TERMS = (
    "calculate",
    "calculation",
    "compare",
    "difference",
    "between",
    "versus",
    " vs ",
    "total over",
    "sum of",
    "חישוב",
    "חשב",
    "השווה",
    "השוואה",
    "הפרש",
    "בין החודשים",
    "احسب",
    "حساب",
    "قارن",
    "الفرق",
)

_CONVERSATION_HISTORY_TERMS = (
    "what did i ask",
    "what did we discuss",
    "previous question",
    "earlier",
    "our conversation",
    "remind me",
    "מה שאלתי",
    "מה דיברנו",
    "השיחה הקודמת",
    "קודם לכן",
    "תזכיר לי",
    "ماذا سألت",
    "ماذا ناقشنا",
    "المحادثة",
)

_REFERENTIAL_PERIOD_TERMS = (
    "same month",
    "that month",
    "the same period",
    "that period",
    "that payslip",
    "same payslip",
    "אותו חודש",
    "באותו חודש",
    "אותו תלוש",
    "באותו תלוש",
    "אותה תקופה",
    "نفس الشهر",
    "ذلك الشهر",
    "نفس كشف الراتب",
)

_REFERENTIAL_DOCUMENT_TERMS = (
    "that document",
    "the previous document",
    "same document",
    "אותו מסמך",
    "המסמך הקודם",
    "ذلك المستند",
    "المستند السابق",
)

_LABOR_LAW_TERMS = (
    "law",
    "legal",
    "right",
    "rights",
    "entitled",
    "regulation",
    "minimum wage",
    "vacation",
    "sick leave",
    "pension",
    "חוק",
    "זכות",
    "זכויות",
    "תקנה",
    "שכר מינימום",
    "חופשה",
    "מחלה",
    "פנסיה",
    "قانون",
    "حق",
    "حقوق",
    "إجازة",
)


class AnswerStrategy(str, Enum):
    LABOR_LAW = "labor_law"
    PERSONAL_PAYSLIP = "personal_payslip"
    PAYROLL_CALCULATION = "payroll_calculation"
    VALIDATION = "validation"
    CONVERSATION_HISTORY = "conversation_history"
    DOCUMENT_EXPLANATION = "document_explanation"
    GENERAL_PAYROLL = "general_payroll"


@dataclass(frozen=True, slots=True)
class ContextNeeds:
    """Which context packages the strategy requires."""

    labor_law: bool = False
    payslip: bool = False
    multi_payslip: bool = False
    validation: bool = False
    documents: bool = False
    conversation_summary: bool = False
    profile: bool = False


@dataclass(frozen=True, slots=True)
class AnswerStrategyPlan:
    strategy: AnswerStrategy
    needs: ContextNeeds
    year: int | None = None
    month: int | None = None
    intent: EmployeeContextIntent | None = None
    uses_referential_period: bool = False

    @property
    def period_key(self) -> str | None:
        if self.year is None or self.month is None:
            return None
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def period_label(self) -> str | None:
        return self.period_key


def resolve_answer_strategy(
    message: str,
    *,
    today: date | None = None,
    summary_period: str | None = None,
    has_conversation_summary: bool = False,
) -> AnswerStrategyPlan:
    """Build a strategy plan from existing intent detection + light follow-up cues."""
    current_date = today or date.today()
    normalized = " ".join(message.lower().split())
    intent = analyze_employee_context_intent(message, today=current_date)
    year, month = intent.year, intent.month
    uses_referential = False

    if month is None and contains_any(normalized, _REFERENTIAL_PERIOD_TERMS):
        parsed = parse_period_key(summary_period)
        if parsed is not None:
            year, month = parsed
            uses_referential = True
            # Treat as personal payroll follow-up when period is recovered.
            intent = EmployeeContextIntent(
                profile=intent.profile,
                payroll=True,
                validation=intent.validation,
                documents=intent.documents,
                year=year,
                month=month,
            )

    if contains_any(normalized, _CONVERSATION_HISTORY_TERMS) and has_conversation_summary:
        return AnswerStrategyPlan(
            strategy=AnswerStrategy.CONVERSATION_HISTORY,
            needs=ContextNeeds(conversation_summary=True),
            year=year,
            month=month,
            intent=intent,
            uses_referential_period=uses_referential,
        )

    if contains_any(normalized, _REFERENTIAL_DOCUMENT_TERMS) and has_conversation_summary:
        return AnswerStrategyPlan(
            strategy=AnswerStrategy.DOCUMENT_EXPLANATION,
            needs=ContextNeeds(documents=True, conversation_summary=True),
            year=year,
            month=month,
            intent=intent,
            uses_referential_period=uses_referential,
        )

    # Pure labor-law question: in-domain labor terms without personal payroll load.
    if (
        contains_any(normalized, _LABOR_LAW_TERMS)
        and not intent.payroll
        and not intent.validation
        and not intent.documents
        and not intent.profile
    ):
        return AnswerStrategyPlan(
            strategy=AnswerStrategy.LABOR_LAW,
            needs=ContextNeeds(labor_law=True, conversation_summary=has_conversation_summary),
            year=year,
            month=month,
            intent=intent,
            uses_referential_period=uses_referential,
        )

    if intent.validation:
        return AnswerStrategyPlan(
            strategy=AnswerStrategy.VALIDATION,
            needs=ContextNeeds(
                validation=True,
                payslip=True,
                labor_law=contains_any(normalized, _LABOR_LAW_TERMS),
                conversation_summary=has_conversation_summary,
            ),
            year=year,
            month=month,
            intent=intent,
            uses_referential_period=uses_referential,
        )

    if intent.documents and not intent.payroll:
        return AnswerStrategyPlan(
            strategy=AnswerStrategy.DOCUMENT_EXPLANATION,
            needs=ContextNeeds(
                documents=True,
                conversation_summary=has_conversation_summary,
            ),
            year=year,
            month=month,
            intent=intent,
            uses_referential_period=uses_referential,
        )

    if intent.payroll or is_personal_payroll_message(normalized):
        if contains_any(normalized, _CALCULATION_TERMS):
            return AnswerStrategyPlan(
                strategy=AnswerStrategy.PAYROLL_CALCULATION,
                needs=ContextNeeds(
                    payslip=True,
                    multi_payslip=True,
                    conversation_summary=has_conversation_summary,
                ),
                year=year,
                month=month,
                intent=intent,
                uses_referential_period=uses_referential,
            )
        return AnswerStrategyPlan(
            strategy=AnswerStrategy.PERSONAL_PAYSLIP,
            needs=ContextNeeds(
                payslip=True,
                profile=intent.profile,
                conversation_summary=has_conversation_summary,
            ),
            year=year,
            month=month,
            intent=intent,
            uses_referential_period=uses_referential,
        )

    if intent.profile:
        return AnswerStrategyPlan(
            strategy=AnswerStrategy.GENERAL_PAYROLL,
            needs=ContextNeeds(profile=True, conversation_summary=has_conversation_summary),
            year=year,
            month=month,
            intent=intent,
            uses_referential_period=uses_referential,
        )

    if contains_any(normalized, _LABOR_LAW_TERMS):
        return AnswerStrategyPlan(
            strategy=AnswerStrategy.LABOR_LAW,
            needs=ContextNeeds(labor_law=True, conversation_summary=has_conversation_summary),
            year=year,
            month=month,
            intent=intent,
            uses_referential_period=uses_referential,
        )

    return AnswerStrategyPlan(
        strategy=AnswerStrategy.GENERAL_PAYROLL,
        needs=ContextNeeds(
            labor_law=True,
            conversation_summary=has_conversation_summary,
        ),
        year=year,
        month=month,
        intent=intent,
        uses_referential_period=uses_referential,
    )


def parse_period_key(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    text = value.strip()
    if len(text) == 7 and text[4] == "-":
        try:
            year = int(text[:4])
            month = int(text[5:7])
        except ValueError:
            return None
        if 1 <= month <= 12:
            return year, month
    year, month = parse_message_period(text)
    if year is not None and month is not None:
        return year, month
    return None
