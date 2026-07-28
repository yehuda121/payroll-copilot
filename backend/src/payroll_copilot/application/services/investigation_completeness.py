"""Completeness checks for payroll investigation snapshots.

Decides whether Dynamo structured data is sufficient or Scenario C enrichment
(S3 original → ephemeral OCR/parse) should be attempted.
"""

from __future__ import annotations

from payroll_copilot.application.services.payslip_line_item_diff import structured_field_value
from payroll_copilot.domain.investigation.types import (
    CompletenessReport,
    InvestigationFocus,
    PeriodSnapshot,
)

# Always required to explain period-over-period pay changes.
_ESSENTIAL_KEYS: tuple[str, ...] = (
    "gross_salary",
    "net_salary",
)

# Nice-to-have keys that can trigger ephemeral S3 enrichment when missing.
# GENERAL / NET_GROSS rely on essentials (gross/net); do not force S3 for optional detail.
_ENRICHMENT_KEYS_BY_FOCUS: dict[InvestigationFocus, tuple[str, ...]] = {
    InvestigationFocus.GENERAL: (),
    InvestigationFocus.NET_GROSS: (),
    InvestigationFocus.OVERTIME: ("overtime_hours",),
    InvestigationFocus.DEDUCTIONS: (
        "income_tax",
        "national_insurance",
        "health_tax",
        "total_deductions",
    ),
    InvestigationFocus.PENSION: ("pension_employee", "pension_employer"),
    InvestigationFocus.LEAVE: ("vacation_balance", "sick_leave_balance"),
    InvestigationFocus.BASE_SALARY: ("base_salary",),
}


def _missing_keys(snapshot: PeriodSnapshot, keys: tuple[str, ...]) -> tuple[str, ...]:
    missing: list[str] = []
    for key in keys:
        value = structured_field_value(snapshot.structured_fields, key)
        if value in (None, ""):
            missing.append(key)
    return tuple(missing)


def assess_completeness(
    snapshot: PeriodSnapshot,
    *,
    focus: InvestigationFocus = InvestigationFocus.GENERAL,
) -> CompletenessReport:
    essential_missing = _missing_keys(snapshot, _ESSENTIAL_KEYS)
    enrichment_keys = _ENRICHMENT_KEYS_BY_FOCUS.get(focus, _ENRICHMENT_KEYS_BY_FOCUS[InvestigationFocus.GENERAL])
    enrichment_missing = _missing_keys(snapshot, enrichment_keys)
    return CompletenessReport(
        is_complete=len(essential_missing) == 0 and len(enrichment_missing) == 0,
        missing_essential_keys=essential_missing,
        missing_enrichment_keys=enrichment_missing,
    )


def needs_s3_enrichment(report: CompletenessReport) -> bool:
    """Enrich when essentials exist but focus-specific detail is missing, or essentials missing with a storage key path available later."""
    if report.missing_essential_keys:
        return True
    return bool(report.missing_enrichment_keys)
