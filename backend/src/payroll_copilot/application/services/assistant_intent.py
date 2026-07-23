"""Shared payroll-assistant intent terms and period parsing.

Single catalog used by input guardrails and the employee context builder so
domain detection stays consistent without duplicated keyword lists.
"""

from __future__ import annotations

import re
from datetime import date

# Personal payroll / payslip terms — load employee payroll facts when matched.
PERSONAL_PAYROLL_TERMS: tuple[str, ...] = (
    "payroll",
    "payslip",
    "pay slip",
    "paystub",
    "pay stub",
    "salary",
    "wage",
    "wages",
    "deduction",
    "deductions",
    "overtime",
    "earn",
    "earned",
    "income",
    "net pay",
    "gross",
    "nis",
    "ils",
    "שכר",
    "תלוש",
    "ניכוי",
    "ניכויים",
    "שעות נוספות",
    "הרווחתי",
    "הרווחת",
    "קיבלתי",
    "נטו",
    "ברוטו",
    "راتب",
    "رواتب",
    "كشف راتب",
    "خصم",
    "ساعات إضافية",
    "كم ربحت",
    "كم حصلت",
)

# Broader in-domain labor / platform terms — guardrail allowlist only.
LABOR_AND_PLATFORM_TERMS: tuple[str, ...] = (
    "minimum wage",
    "vacation",
    "holiday",
    "sick",
    "leave",
    "pension",
    "tax",
    "taxes",
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
    "חופשה",
    "מחלה",
    "פנסיה",
    "מס",
    "נסיעות",
    "בדיקה",
    "אזהרה",
    "קריטי",
    "מסמך",
    "מסמכים",
    "إجازة",
    "مرض",
    "تقاعد",
    "ضريبة",
    "مستند",
    "مستندات",
    "تحذير",
    "حرج",
)

# Guardrails + any caller that needs "is this on-topic for Payroll Copilot".
PAYROLL_DOMAIN_TERMS: tuple[str, ...] = PERSONAL_PAYROLL_TERMS + LABOR_AND_PLATFORM_TERMS

_LAST_MONTH_TERMS: tuple[str, ...] = (
    "last month",
    "previous month",
    "חודש שעבר",
    "החודש הקודם",
    "الشهر الماضي",
    "الشهر السابق",
)

_CURRENT_MONTH_TERMS: tuple[str, ...] = (
    "current month",
    "this month",
    "החודש הנוכחי",
    "החודש הזה",
    "الشهر الحالي",
    "هذا الشهر",
)

# Longest names first so "september" wins over shorter overlaps.
_MONTH_NAME_TO_NUMBER: tuple[tuple[str, int], ...] = (
    ("september", 9),
    ("november", 11),
    ("december", 12),
    ("february", 2),
    ("january", 1),
    ("october", 10),
    ("august", 8),
    ("april", 4),
    ("march", 3),
    ("june", 6),
    ("july", 7),
    ("may", 5),
    ("jan", 1),
    ("feb", 2),
    ("mar", 3),
    ("apr", 4),
    ("jun", 6),
    ("jul", 7),
    ("aug", 8),
    ("sep", 9),
    ("oct", 10),
    ("nov", 11),
    ("dec", 12),
    ("ספטמבר", 9),
    ("נובמבר", 11),
    ("דצמבר", 12),
    ("פברואר", 2),
    ("אוקטובר", 10),
    ("אוגוסט", 8),
    ("ינואר", 1),
    ("אפריל", 4),
    ("יוני", 6),
    ("יולי", 7),
    ("מרץ", 3),
    ("מרס", 3),
    ("מאי", 5),
)


def contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def is_payroll_domain_message(normalized: str) -> bool:
    """True when the message is in-domain for the payroll assistant guardrail."""
    return contains_any(normalized, PAYROLL_DOMAIN_TERMS)


def is_personal_payroll_message(normalized: str) -> bool:
    """True when personal payslip/payroll facts may need to be loaded."""
    return contains_any(normalized, PERSONAL_PAYROLL_TERMS)


def parse_message_period(
    message: str,
    *,
    today: date | None = None,
) -> tuple[int | None, int | None]:
    """Extract (year, month) from numeric, relative, or natural month phrases."""
    normalized = " ".join(message.lower().split())
    current_date = today or date.today()

    period_match = re.search(r"\b(20\d{2})[-/.](0?[1-9]|1[0-2])\b", normalized)
    if period_match:
        return int(period_match.group(1)), int(period_match.group(2))

    named = _parse_named_month_year(normalized)
    if named is not None:
        return named

    if contains_any(normalized, _LAST_MONTH_TERMS):
        year = current_date.year
        month = current_date.month - 1
        if month == 0:
            month = 12
            year -= 1
        return year, month

    if contains_any(normalized, _CURRENT_MONTH_TERMS):
        return current_date.year, current_date.month

    return None, None


def _parse_named_month_year(normalized: str) -> tuple[int, int] | None:
    """Match 'May 2026', 'מאי 2026', '2026 May', '2026 מאי'."""
    for name, month in _MONTH_NAME_TO_NUMBER:
        # Name then year
        match = re.search(
            rf"(?<!\w){re.escape(name)}(?:\s+|[-/.])?(20\d{{2}})(?!\d)",
            normalized,
        )
        if match:
            return int(match.group(1)), month
        # Year then name
        match = re.search(
            rf"(?<!\d)(20\d{{2}})(?:\s+|[-/.])?{re.escape(name)}(?!\w)",
            normalized,
        )
        if match:
            return int(match.group(1)), month
    return None
