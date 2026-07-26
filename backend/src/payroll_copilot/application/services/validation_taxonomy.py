"""Validation taxonomy tags for UI grouping — does not change verdicts.

Maps existing rule_id / RuleCategory to SANITY | EMPLOYEE | CONTRACT | LAW.
Old validation runs remain compatible via derive-on-read.
"""

from __future__ import annotations

from enum import StrEnum

from payroll_copilot.domain.enums import RuleCategory


class ValidationTaxonomy(StrEnum):
    SANITY = "sanity"
    EMPLOYEE = "employee"
    CONTRACT = "contract"
    LAW = "law"


# Explicit rule_id overrides (executing Python rules).
_RULE_ID_TAXONOMY: dict[str, ValidationTaxonomy] = {
    "legal.overtime.daily_limit": ValidationTaxonomy.LAW,
    "legal.minimum_wage": ValidationTaxonomy.LAW,
    "legal.pension.contribution": ValidationTaxonomy.LAW,
    "legal.youth.minimum_age": ValidationTaxonomy.LAW,
    "department.intern.weekly_hours_limit": ValidationTaxonomy.CONTRACT,
    "department.lawyers.overtime_cap": ValidationTaxonomy.CONTRACT,
    "historical.salary_drift": ValidationTaxonomy.EMPLOYEE,
}

_CATEGORY_FALLBACK: dict[RuleCategory, ValidationTaxonomy] = {
    RuleCategory.LEGAL: ValidationTaxonomy.LAW,
    RuleCategory.TAX: ValidationTaxonomy.LAW,
    RuleCategory.PENSION: ValidationTaxonomy.LAW,
    RuleCategory.OVERTIME: ValidationTaxonomy.LAW,
    RuleCategory.VACATION: ValidationTaxonomy.LAW,
    RuleCategory.TRANSPORTATION: ValidationTaxonomy.LAW,
    RuleCategory.HOLIDAY: ValidationTaxonomy.LAW,
    RuleCategory.DEPARTMENT: ValidationTaxonomy.CONTRACT,
    RuleCategory.CONTRACT: ValidationTaxonomy.CONTRACT,
    RuleCategory.HISTORICAL: ValidationTaxonomy.EMPLOYEE,
    RuleCategory.COMPANY: ValidationTaxonomy.EMPLOYEE,
}

# Identity / period confirmation gates (not rule-engine findings).
_GATE_TAXONOMY: dict[str, ValidationTaxonomy] = {
    "national_id": ValidationTaxonomy.EMPLOYEE,
    "employee_number": ValidationTaxonomy.EMPLOYEE,
    "employee_name": ValidationTaxonomy.EMPLOYEE,
    "pay_period": ValidationTaxonomy.EMPLOYEE,
}


def taxonomy_for_rule_id(rule_id: str | None, category: str | None = None) -> ValidationTaxonomy | None:
    """Return taxonomy for a rule, or None if ambiguous."""
    rid = (rule_id or "").strip()
    if rid in _RULE_ID_TAXONOMY:
        return _RULE_ID_TAXONOMY[rid]
    if category:
        try:
            return _CATEGORY_FALLBACK[RuleCategory(str(category).strip().lower())]
        except ValueError:
            pass
    # Prefix heuristics for known families
    lower = rid.lower()
    if lower.startswith("legal.") or lower.startswith("validation.overtime") or "minimum_wage" in lower:
        return ValidationTaxonomy.LAW
    if lower.startswith("department."):
        return ValidationTaxonomy.CONTRACT
    if lower.startswith("historical."):
        return ValidationTaxonomy.EMPLOYEE
    return None


def taxonomy_for_gate_field(field_key: str) -> ValidationTaxonomy:
    return _GATE_TAXONOMY.get((field_key or "").strip(), ValidationTaxonomy.EMPLOYEE)


def ui_group_for_taxonomy(taxonomy: ValidationTaxonomy) -> str:
    """UI tab grouping: CONTRACT surfaces under employee checks."""
    if taxonomy in (ValidationTaxonomy.EMPLOYEE, ValidationTaxonomy.CONTRACT):
        return "employee_checks"
    if taxonomy == ValidationTaxonomy.LAW:
        return "law_checks"
    return "digital"  # SANITY → Digital Payslip field state


# Clear field ↔ rule bindings only (no guessing).
_FIELD_RULE_BINDINGS: dict[str, frozenset[str]] = {
    "overtime_hours": frozenset({"legal.overtime.daily_limit"}),
    "hourly_rate": frozenset({"legal.minimum_wage"}),
    "gross_salary": frozenset({"legal.pension.contribution", "historical.salary_drift"}),
    "pension_employee": frozenset({"legal.pension.contribution"}),
    "regular_hours": frozenset({"department.intern.weekly_hours_limit"}),
    "employee_id": frozenset(),  # gates only
    "national_id": frozenset(),
    "employee_name": frozenset(),
    "pay_period": frozenset(),
}


def bound_rule_ids_for_field(field_key: str) -> frozenset[str]:
    return _FIELD_RULE_BINDINGS.get((field_key or "").strip(), frozenset())
