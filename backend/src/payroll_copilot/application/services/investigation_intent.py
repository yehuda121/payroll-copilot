"""Intent helpers for payroll investigation / anomaly questions."""

from __future__ import annotations

from payroll_copilot.application.services.assistant_intent import contains_any
from payroll_copilot.domain.investigation.types import InvestigationFocus

INVESTIGATION_TERMS: tuple[str, ...] = (
    "why did",
    "why was",
    "why is",
    "what changed",
    "changed from",
    "difference from last",
    "compared to last",
    "anomaly",
    "unexpected",
    "suddenly",
    "dropped",
    "increased",
    "decreased",
    "lower than",
    "higher than",
    "missing deduction",
    "extra deduction",
    "למה",
    "מדוע",
    "מה השתנה",
    "מה השתנה בתלוש",
    "ירידה",
    "עלייה",
    "ירד לי",
    "עלה לי",
    "באופן חריג",
    "חריג",
    "לא צפוי",
    "השוואה לחודש",
    "לעומת חודש",
    "ביחס לחודש",
    "لماذا",
    "ما الذي تغير",
    "انخفض",
    "ارتفع",
    "غير متوقع",
)

_FOCUS_OVERTIME = (
    "overtime",
    "שעות נוספות",
    "שעות נוספת",
    "ساعات إضافية",
)
_FOCUS_PENSION = ("pension", "פנסיה", "تقاعد")
_FOCUS_DEDUCTIONS = (
    "deduction",
    "deductions",
    "tax",
    "ניכוי",
    "ניכויים",
    "מס",
    "خصم",
    "ضريبة",
)
_FOCUS_LEAVE = (
    "vacation",
    "sick",
    "leave",
    "חופשה",
    "מחלה",
    "إجازة",
)
_FOCUS_BASE = ("base salary", "שכר יסוד", "basic salary")
_FOCUS_NET_GROSS = ("net", "gross", "נטו", "ברוטו", "صافي", "إجمالي")


def is_investigation_message(message: str) -> bool:
    normalized = " ".join(message.lower().split())
    return contains_any(normalized, INVESTIGATION_TERMS)


def detect_investigation_focus(message: str) -> InvestigationFocus:
    normalized = " ".join(message.lower().split())
    if contains_any(normalized, _FOCUS_OVERTIME):
        return InvestigationFocus.OVERTIME
    if contains_any(normalized, _FOCUS_PENSION):
        return InvestigationFocus.PENSION
    if contains_any(normalized, _FOCUS_LEAVE):
        return InvestigationFocus.LEAVE
    if contains_any(normalized, _FOCUS_BASE):
        return InvestigationFocus.BASE_SALARY
    if contains_any(normalized, _FOCUS_DEDUCTIONS):
        return InvestigationFocus.DEDUCTIONS
    if contains_any(normalized, _FOCUS_NET_GROSS):
        return InvestigationFocus.NET_GROSS
    return InvestigationFocus.GENERAL
