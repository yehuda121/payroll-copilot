"""primary_company extraction profile — configuration only."""

from __future__ import annotations

from payroll_copilot.application.services.company_payslip_extraction.companies.primary_company import fields, labels, markers, value_rules
from payroll_copilot.application.services.company_payslip_extraction.core.profile import CompanyProfile

COMPANY_KEY = "primary_company"

PROFILE = CompanyProfile(
    key=COMPANY_KEY,
    start_markers=markers.START_MARKERS,
    end_markers=markers.END_MARKERS,
    title_markers=markers.TITLE_MARKERS,
    logical_label_hints=labels.LOGICAL_LABEL_HINTS,
    visual_label_hints=labels.VISUAL_LABEL_HINTS,
    label_aliases=labels.LABEL_ALIASES,
    apostrophe_label_allow=labels.APOSTROPHE_LABEL_ALLOW,
    yes_no_value_aliases=value_rules.YES_NO_VALUE_ALIASES,
    employment_type_tokens=value_rules.EMPLOYMENT_TYPE_TOKENS,
    name_reject_substrings=labels.NAME_REJECT_SUBSTRINGS,
    footer_label_hints=labels.FOOTER_LABEL_HINTS,
    footer_label_exceptions=labels.FOOTER_LABEL_EXCEPTIONS,
    structural_label_bigrams=labels.STRUCTURAL_LABEL_BIGRAMS,
    incomplete_standalone_labels=labels.INCOMPLETE_STANDALONE_LABELS,
    extendable_partial_labels=labels.EXTENDABLE_PARTIAL_LABELS,
    complete_short_labels=labels.COMPLETE_SHORT_LABELS,
    helper_labels=labels.HELPER_LABELS,
    summary_field_names=fields.SUMMARY_FIELD_NAMES,
    deduction_field_names=fields.DEDUCTION_FIELD_NAMES,
    deduction_row_labels=fields.DEDUCTION_ROW_LABELS,
    employment_scope_label=fields.EMPLOYMENT_SCOPE_LABEL,
)


def get_profile() -> CompanyProfile:
    return PROFILE
