"""Shared result / layout types re-exported from layout for a stable public surface."""

from __future__ import annotations

from payroll_copilot.application.services.company_payslip_extraction.core.layout import (
    FieldCandidate,
    LayoutTemplate,
    VisualRow,
    WordSpan,
    bbox_from_words,
)
from payroll_copilot.application.services.company_payslip_extraction.core.profile import CompanyProfile

__all__ = [
    "CompanyProfile",
    "FieldCandidate",
    "LayoutTemplate",
    "VisualRow",
    "WordSpan",
    "bbox_from_words",
]
