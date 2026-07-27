"""Canonical Validation Catalog — backend-authoritative check metadata + readiness.

Does not invent legal values. Readiness reflects actual Python implementation status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Outcome states (canonical for UI)
OUTCOME_PASSED = "passed"
OUTCOME_FAILED = "failed"
OUTCOME_UNCERTAIN = "uncertain"
OUTCOME_NOT_RUN = "not_run"

# NOT_RUN / skip reason codes
REASON_MISSING_PAYSLIP_DATA = "MISSING_PAYSLIP_DATA"
REASON_MISSING_PAY_PERIOD = "MISSING_PAY_PERIOD"
REASON_RULE_NOT_READY = "RULE_NOT_READY"
REASON_NO_APPLICABLE_LEGAL_VERSION = "NO_APPLICABLE_LEGAL_VERSION"
REASON_NOT_APPLICABLE = "NOT_APPLICABLE"
REASON_UNSUPPORTED_SCOPE = "UNSUPPORTED_SCOPE"
REASON_RULE_DISABLED = "RULE_DISABLED"
REASON_DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
REASON_EXECUTION_ERROR = "EXECUTION_ERROR"
REASON_EMPLOYEE_NOT_IDENTIFIED = "EMPLOYEE_NOT_IDENTIFIED"
REASON_NO_CONFIRMED_CONTRACT = "NO_CONFIRMED_CONTRACT"

READINESS_PRODUCTION_READY = "PRODUCTION_READY"
READINESS_CONDITIONAL = "CONDITIONAL"
READINESS_NOT_READY = "NOT_READY"


@dataclass(frozen=True, slots=True)
class CatalogCheck:
    rule_id: str
    display_name: str
    description: str
    category: str
    readiness: str
    readiness_reason: str
    required_fields: tuple[str, ...]
    applicability: str
    display_order: int
    ui_group: str  # employee_checks | law_checks
    currently_executed: str  # yes | no | conditional


# All 17 YAML labor-law rule IDs + other user-facing transparency checks.
LABOR_LAW_CATALOG: tuple[CatalogCheck, ...] = (
    CatalogCheck(
        rule_id="legal.minimum_wage",
        display_name="Hourly minimum wage",
        description="Hourly minimum wage",
        category="Compensation",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Applies when payslip/contract indicates hourly pay basis.",
        required_fields=("hourly_rate",),
        applicability="Hourly salary basis only",
        display_order=10,
        ui_group="law_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="legal.overtime.daily_limit",
        display_name="Daily overtime limit",
        description="Daily overtime limit",
        category="Working Hours",
        readiness=READINESS_CONDITIONAL,
        readiness_reason=(
            "Limited deterministic check vs payslip overtime_hours total for full/part-time; "
            "attendance-day reconstruction deferred."
        ),
        required_fields=("overtime_hours",),
        applicability="FULL_TIME / PART_TIME employment types",
        display_order=20,
        ui_group="law_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="legal.overtime.weekly_limit",
        display_name="Weekly overtime limit",
        description="Weekly overtime limit",
        category="Working Hours",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — YAML config only; no Python evaluator.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=21,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.overtime.rate_tier_1",
        display_name="Overtime rate - first two hours",
        description="Overtime rate - first two hours",
        category="Working Hours",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — YAML config only; no Python evaluator.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=22,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.overtime.rate_tier_2",
        display_name="Overtime rate - beyond two hours",
        description="Overtime rate - beyond two hours",
        category="Working Hours",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — YAML config only; no Python evaluator.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=23,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.vacation.annual_entitlement",
        display_name="Annual vacation entitlement",
        description="Annual vacation entitlement",
        category="Leave",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — requires tenure/balances; deferred.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=30,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.vacation.monthly_accrual",
        display_name="Monthly vacation accrual",
        description="Monthly vacation accrual",
        category="Leave",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — accrual conventions deferred.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=31,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.sick_leave.annual_entitlement",
        display_name="Annual sick leave entitlement",
        description="Annual sick leave entitlement",
        category="Leave",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — medical/payment schedule deferred.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=32,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.pension.contribution",
        display_name="Minimum pension contribution - employee",
        description="Minimum pension contribution - employee",
        category="Pension",
        readiness=READINESS_NOT_READY,
        readiness_reason=(
            "UNSAFE_EXECUTION_SEMANTICS — registered but applies_to=False; "
            "insured wage / eligibility ambiguous."
        ),
        required_fields=("pension_employee", "gross_salary"),
        applicability="Deferred until safe contribution base exists",
        display_order=40,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.pension.employer_contribution",
        display_name="Minimum pension contribution - employer",
        description="Minimum pension contribution - employer",
        category="Pension",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — YAML only; no safe evaluator.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=41,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.pension.severance",
        display_name="Severance component",
        description="Severance component",
        category="Pension",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — termination/severance context required.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=42,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.tax.income_brackets",
        display_name="Income tax brackets",
        description="Income tax brackets",
        category="Tax",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — full tax engine deferred.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=50,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.tax.credit_point",
        display_name="Tax credit point value",
        description="Tax credit point value",
        category="Tax",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — Form 101 answers required.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=51,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.transportation.max_allowance",
        display_name="Maximum transportation allowance",
        description="Maximum transportation allowance",
        category="Transportation",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — residence/route inputs deferred.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=60,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.transportation.public_transport",
        display_name="Public transport reimbursement",
        description="Public transport reimbursement",
        category="Transportation",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — YAML config only.",
        required_fields=(),
        applicability="Unknown until implemented",
        display_order=61,
        ui_group="law_checks",
        currently_executed="no",
    ),
    CatalogCheck(
        rule_id="legal.youth.minimum_age",
        display_name="Minimum age for youth employment",
        description="Minimum age for youth employment",
        category="Youth",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Applies only to INTERN / PRE_INTERN employment types.",
        required_fields=("age",),
        applicability="INTERN / PRE_INTERN only",
        display_order=70,
        ui_group="law_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="legal.youth.max_daily_hours",
        display_name="Daily hour limit for youth",
        description="Daily hour limit for youth",
        category="Youth",
        readiness=READINESS_NOT_READY,
        readiness_reason="MISSING_IMPLEMENTATION — YAML config only; no Python evaluator.",
        required_fields=(),
        applicability="Youth employment (when implemented)",
        display_order=71,
        ui_group="law_checks",
        currently_executed="no",
    ),
)

IDENTITY_CONTRACT_CATALOG: tuple[CatalogCheck, ...] = (
    CatalogCheck(
        rule_id="employee.national_id.match",
        display_name="National ID match",
        description="Payslip national ID vs authorized employee",
        category="Identity",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires authorized employee context.",
        required_fields=("national_id",),
        applicability="authorized_employee=True",
        display_order=1,
        ui_group="employee_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="employee.name.match",
        display_name="Employee name match",
        description="Payslip name vs authorized employee",
        category="Identity",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires authorized employee context.",
        required_fields=("employee_name",),
        applicability="authorized_employee=True",
        display_order=2,
        ui_group="employee_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="employee.employee_number.match",
        display_name="Employee number match",
        description="Payslip employee number vs profile",
        category="Identity",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires authorized employee context.",
        required_fields=("employee_number",),
        applicability="authorized_employee=True",
        display_order=3,
        ui_group="employee_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="employee.employment_type.match",
        display_name="Employment type match",
        description="Payslip employment type vs profile",
        category="Identity",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires authorized employee context.",
        required_fields=("employment_type",),
        applicability="authorized_employee=True",
        display_order=4,
        ui_group="employee_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="employee.pay_period.match",
        display_name="Pay period match",
        description="Payslip period vs expected period",
        category="Identity",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires authorized employee context.",
        required_fields=("pay_period",),
        applicability="authorized_employee=True",
        display_order=5,
        ui_group="employee_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="contract.employment_commencement_date.match",
        display_name="Employment commencement date",
        description="Payslip vs confirmed contract start",
        category="Contract",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires authorized employee and confirmed employment terms.",
        required_fields=("employment_commencement_date",),
        applicability="authorized_employee + confirmed contract",
        display_order=6,
        ui_group="employee_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="contract.salary_basis.match",
        display_name="Salary basis match",
        description="Payslip vs confirmed salary basis",
        category="Contract",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires authorized employee and confirmed employment terms.",
        required_fields=("salary_basis",),
        applicability="authorized_employee + confirmed contract",
        display_order=7,
        ui_group="employee_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="contract.hourly_rate.match",
        display_name="Hourly rate match",
        description="Payslip vs confirmed hourly rate",
        category="Contract",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires authorized employee and confirmed employment terms.",
        required_fields=("hourly_rate",),
        applicability="authorized_employee + confirmed contract",
        display_order=8,
        ui_group="employee_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="department.intern.weekly_hours_limit",
        display_name="Intern weekly hours limit",
        description="Department intern weekly hours",
        category="Department",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Applies when department rule_profile is interns/pre_interns.",
        required_fields=("weekly_hours",),
        applicability="department.rule_profile in interns/pre_interns",
        display_order=80,
        ui_group="law_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="department.lawyers.overtime_cap",
        display_name="Lawyers overtime cap",
        description="Department lawyers overtime cap",
        category="Department",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Applies when department rule_profile is lawyers.",
        required_fields=("overtime_hours",),
        applicability="department.rule_profile == lawyers",
        display_order=81,
        ui_group="law_checks",
        currently_executed="conditional",
    ),
    CatalogCheck(
        rule_id="historical.salary_drift",
        display_name="Historical salary drift",
        description="Salary drift vs prior periods",
        category="Historical",
        readiness=READINESS_CONDITIONAL,
        readiness_reason="Requires historical payslips in context.",
        required_fields=("gross_salary",),
        applicability="When historical payslips present",
        display_order=90,
        ui_group="law_checks",
        currently_executed="conditional",
    ),
)


def all_catalog_checks() -> tuple[CatalogCheck, ...]:
    return tuple(sorted((*IDENTITY_CONTRACT_CATALOG, *LABOR_LAW_CATALOG), key=lambda c: c.display_order))


def labor_law_rule_ids() -> tuple[str, ...]:
    return tuple(c.rule_id for c in LABOR_LAW_CATALOG)


def catalog_by_rule_id() -> dict[str, CatalogCheck]:
    return {c.rule_id: c for c in all_catalog_checks()}


def reason_message(reason_code: str | None) -> str:
    messages = {
        REASON_MISSING_PAYSLIP_DATA: (
            "This check was not conclusive because required payslip data was unavailable."
        ),
        REASON_MISSING_PAY_PERIOD: (
            "This check was not run because the payslip pay period is missing or could not be "
            "parsed, so no historical legal version could be selected."
        ),
        REASON_RULE_NOT_READY: (
            "This check was not run because it is not currently ready for production validation."
        ),
        REASON_NO_APPLICABLE_LEGAL_VERSION: (
            "This check was not run because no applicable approved legal version was available."
        ),
        REASON_NOT_APPLICABLE: (
            "This check was not run because the rule does not apply to this employee or payslip."
        ),
        REASON_UNSUPPORTED_SCOPE: (
            "This check was not run because the payslip is outside the supported rule scope."
        ),
        REASON_RULE_DISABLED: "This check was not run because the rule is disabled.",
        REASON_DEPENDENCY_UNAVAILABLE: (
            "This check was not run because a required dependency was unavailable."
        ),
        REASON_EXECUTION_ERROR: (
            "This check was not run because an unexpected execution error occurred."
        ),
        REASON_EMPLOYEE_NOT_IDENTIFIED: (
            "This check was not run because the employee was not identified for this validation."
        ),
        REASON_NO_CONFIRMED_CONTRACT: (
            "This check was not run because no confirmed employment terms were available."
        ),
        "employee_not_identified": (
            "This check was not run because the employee was not identified for this validation."
        ),
        "no_confirmed_contract": (
            "This check was not run because no confirmed employment terms were available."
        ),
    }
    if not reason_code:
        return "This check was not run."
    return messages.get(reason_code, "This check was not run.")


def map_legacy_skip_to_reason(skip_reason: str | None, *, not_ready: bool = False) -> str:
    if not_ready:
        return REASON_RULE_NOT_READY
    if skip_reason == "employee_not_identified":
        return REASON_EMPLOYEE_NOT_IDENTIFIED
    if skip_reason == "no_confirmed_contract":
        return REASON_NO_CONFIRMED_CONTRACT
    if skip_reason:
        return skip_reason.upper() if skip_reason.isupper() else REASON_NOT_APPLICABLE
    return REASON_NOT_APPLICABLE


def catalog_as_dicts() -> list[dict[str, Any]]:
    return [
        {
            "rule_id": c.rule_id,
            "display_name": c.display_name,
            "description": c.description,
            "category": c.category,
            "readiness": c.readiness,
            "readiness_reason": c.readiness_reason,
            "required_fields": list(c.required_fields),
            "applicability": c.applicability,
            "display_order": c.display_order,
            "ui_group": c.ui_group,
            "currently_executed": c.currently_executed,
        }
        for c in all_catalog_checks()
    ]
