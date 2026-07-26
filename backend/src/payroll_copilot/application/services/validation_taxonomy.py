"""Validation taxonomy tags for UI grouping — does not change verdicts.

Maps existing rule_id / RuleCategory to SANITY | EMPLOYEE | CONTRACT | LAW.
Old validation runs remain compatible via derive-on-read.
"""

from __future__ import annotations

from enum import StrEnum

from payroll_copilot.application.services.payslip_field_registry import (
    required_on_payslip_keys,
)
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
    "sanity.national_id.length": ValidationTaxonomy.SANITY,
    "sanity.national_id.checksum": ValidationTaxonomy.SANITY,
    "sanity.employee_name.structure": ValidationTaxonomy.SANITY,
    "sanity.pay_period.parseable": ValidationTaxonomy.SANITY,
    "sanity.pay_period.calendar": ValidationTaxonomy.SANITY,
    "sanity.employment_start_date.calendar": ValidationTaxonomy.SANITY,
    "sanity.net_salary.not_exceed_gross": ValidationTaxonomy.SANITY,
    "sanity.employment_type.recognized": ValidationTaxonomy.SANITY,
    "employee.national_id.match": ValidationTaxonomy.EMPLOYEE,
    "employee.name.match": ValidationTaxonomy.EMPLOYEE,
    "employee.employee_number.match": ValidationTaxonomy.EMPLOYEE,
    "employee.employment_type.match": ValidationTaxonomy.EMPLOYEE,
    "employee.pay_period.match": ValidationTaxonomy.EMPLOYEE,
    "contract.employment_commencement_date.match": ValidationTaxonomy.CONTRACT,
    "contract.salary_basis.match": ValidationTaxonomy.CONTRACT,
    "contract.hourly_rate.match": ValidationTaxonomy.CONTRACT,
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
    RuleCategory.EMPLOYEE: ValidationTaxonomy.EMPLOYEE,
    RuleCategory.SANITY: ValidationTaxonomy.SANITY,
}

# Identity / period confirmation gates (not rule-engine findings).
_GATE_TAXONOMY: dict[str, ValidationTaxonomy] = {
    "national_id": ValidationTaxonomy.EMPLOYEE,
    "employee_number": ValidationTaxonomy.EMPLOYEE,
    "employee_name": ValidationTaxonomy.EMPLOYEE,
    "pay_period": ValidationTaxonomy.EMPLOYEE,
}


def _build_field_rule_bindings() -> dict[str, frozenset[str]]:
    bindings: dict[str, set[str]] = {
        "overtime_hours": {"legal.overtime.daily_limit"},
        "gross_salary": {
            "legal.pension.contribution",
            "historical.salary_drift",
            "sanity.net_salary.not_exceed_gross",
        },
        "pension_employee": {"legal.pension.contribution"},
        "regular_hours": {"department.intern.weekly_hours_limit"},
        "employee_id": set(),  # payroll ID — gates/SANITY use national_id
        "national_id": {
            "sanity.national_id.length",
            "sanity.national_id.checksum",
            "employee.national_id.match",
        },
        "employee_name": {
            "sanity.employee_name.structure",
            "employee.name.match",
        },
        "employee_number": {"employee.employee_number.match"},
        "pay_period": {
            "sanity.pay_period.parseable",
            "sanity.pay_period.calendar",
            "employee.pay_period.match",
        },
        "employment_start_date": {
            "sanity.employment_start_date.calendar",
            "contract.employment_commencement_date.match",
        },
        "hourly_rate": {
            "legal.minimum_wage",
            "contract.hourly_rate.match",
        },
        "salary_calculation_basis": {"contract.salary_basis.match"},
        "salary_basis": {"contract.salary_basis.match"},
        "net_salary": {"sanity.net_salary.not_exceed_gross"},
        "employment_type": {
            "sanity.employment_type.recognized",
            "employee.employment_type.match",
        },
    }
    for key in required_on_payslip_keys():
        bindings.setdefault(key, set()).add(f"sanity.required.{key}")
    return {key: frozenset(rules) for key, rules in bindings.items()}


_FIELD_RULE_BINDINGS: dict[str, frozenset[str]] = _build_field_rule_bindings()

# Required presence rules share taxonomy via prefix + explicit registration.
for _required_key in required_on_payslip_keys():
    _RULE_ID_TAXONOMY[f"sanity.required.{_required_key}"] = ValidationTaxonomy.SANITY


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
    if lower.startswith("sanity."):
        return ValidationTaxonomy.SANITY
    if lower.startswith("employee."):
        return ValidationTaxonomy.EMPLOYEE
    if lower.startswith("contract."):
        return ValidationTaxonomy.CONTRACT
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


def bound_rule_ids_for_field(field_key: str) -> frozenset[str]:
    return _FIELD_RULE_BINDINGS.get((field_key or "").strip(), frozenset())
