"""Semantic Field Catalog for payslip extraction (semantic_v1).

Built from the Field Registry. Descriptions teach MEANING, not label synonyms.
"""

from __future__ import annotations

from dataclasses import dataclass

from payroll_copilot.application.services.payslip_field_registry import (
    FieldRequirementCategory,
    get_field_definition,
    requirement_category_for_key,
)
from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_CANONICAL_EXTRA_KEYS,
    PAYSLIP_FIELD_KEYS,
)

EXTRACTOR_VERSION = "semantic_v1"

# Concise concept descriptions for the LLM (English — works across HE/AR/EN docs).
_SEMANTIC_MEANINGS: dict[str, str] = {
    "employee_name": (
        "Full name of the employee/person who receives this salary payment. "
        "Often appears unlabeled in the personal-details or header region "
        "(no 'שם' / 'שם העובד' / 'Employee Name' required). "
        "Not the employer/company name, payroll provider, website, address, or organization."
    ),
    "national_id": (
        "Israeli national identity number (Teudat Zehut) of the employee. "
        "Usually 9 digits. Distinct from employer/payroll employee number."
    ),
    "employee_number": (
        "Employer or payroll-system employee number / personnel file number. "
        "Not the government national ID."
    ),
    "employee_id": (
        "Payroll/system employee identifier when distinct from national ID and employee number."
    ),
    "employer_name": (
        "Legal name of the employer / business issuing the payslip."
    ),
    "employer_id": (
        "Employer company ID / ח.פ. / company registration number."
    ),
    "employer_address": (
        "Employer business address as printed on the payslip."
    ),
    "employment_start_date": (
        "Original employment start / seniority start date printed on the payslip."
    ),
    "employment_scope": (
        "Employment scope / job percentage (e.g. full-time fraction or percent)."
    ),
    "employment_type": (
        "Employment type such as full-time, part-time, intern — as printed."
    ),
    "seniority_years": (
        "Seniority / tenure in years as explicitly printed (do not invent from start date)."
    ),
    "department": (
        "Employee department / unit / cost center printed on the payslip."
    ),
    "pay_period": (
        "Payroll period / month this payslip covers (e.g. 05/2026 or May 2026)."
    ),
    "salary_calculation_basis": (
        "How salary is calculated: monthly, hourly, or daily — when printed."
    ),
    "base_salary": (
        "Base / regular salary (שכר יסוד) for the period before overtime/bonuses."
    ),
    "hourly_rate": (
        "Contractual or printed hourly wage rate."
    ),
    "regular_hours": (
        "Regular hours worked in the period."
    ),
    "overtime_hours": (
        "Overtime hours in the period."
    ),
    "gross_salary": (
        "Total gross salary for this payroll period before deductions."
    ),
    "travel_expenses": (
        "Travel / commuting allowance amount."
    ),
    "income_tax": (
        "Income tax deduction amount for the period."
    ),
    "national_insurance": (
        "National Insurance (ביטוח לאומי) employee deduction."
    ),
    "health_tax": (
        "Health tax (מס בריאות) deduction."
    ),
    "pension_employee": (
        "Employee pension contribution amount."
    ),
    "pension_employer": (
        "Employer pension contribution amount when printed."
    ),
    "severance": (
        "Severance / פיצויים component when printed."
    ),
    "training_fund": (
        "Training fund (קרן השתלמות) contribution when printed."
    ),
    "total_deductions": (
        "Sum of all deductions for the period."
    ),
    "net_salary": (
        "Net salary after deductions (נטו לתשלום / משכורת נטו)."
    ),
    "amount_paid": (
        "Amount actually paid / transferred for this payslip."
    ),
    "payment_method": (
        "Payment method (bank transfer, check, cash, etc.)."
    ),
    "bank_name": "Bank name for salary deposit.",
    "bank_branch": "Bank branch number/name.",
    "bank_account": "Bank account number.",
    "vacation_balance": "Remaining vacation days balance.",
    "sick_leave_balance": "Remaining sick-leave days balance.",
    "minimum_wage_monthly": (
        "Monthly minimum wage amount printed on the document (if present)."
    ),
    "minimum_wage_hourly": (
        "Hourly minimum wage amount printed on the document (if present)."
    ),
    "messages": "Free-text messages / notes printed on the payslip.",
}


@dataclass(frozen=True, slots=True)
class CatalogField:
    canonical_key: str
    meaning: str
    priority: str  # required | expected


def build_payslip_field_catalog() -> list[CatalogField]:
    """Required first, then Expected — all Field Registry concepts with meanings."""
    keys: list[str] = []
    seen: set[str] = set()
    for key in list(PAYSLIP_FIELD_KEYS) + list(PAYSLIP_CANONICAL_EXTRA_KEYS):
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)

    required: list[CatalogField] = []
    expected: list[CatalogField] = []
    for key in keys:
        category = requirement_category_for_key(key)
        meaning = _SEMANTIC_MEANINGS.get(key) or (
            f"Payroll field '{key}' as printed on the payslip when present."
        )
        item = CatalogField(
            canonical_key=key,
            meaning=meaning,
            priority=(
                "required"
                if category == FieldRequirementCategory.REQUIRED
                else "expected"
                if category == FieldRequirementCategory.EXPECTED
                else "expected"
            ),
        )
        # Only include Required + Expected in the catalog (Other is free-form).
        definition = get_field_definition(key)
        if definition is None:
            continue
        if definition.requirement_category == FieldRequirementCategory.REQUIRED:
            required.append(item)
        elif definition.requirement_category == FieldRequirementCategory.EXPECTED:
            expected.append(item)

    def _order(key: str) -> int:
        d = get_field_definition(key)
        return d.display_order if d else 9999

    required.sort(key=lambda f: _order(f.canonical_key))
    expected.sort(key=lambda f: _order(f.canonical_key))
    return required + expected


def catalog_as_prompt_rows(catalog: list[CatalogField] | None = None) -> list[dict[str, str]]:
    rows = catalog or build_payslip_field_catalog()
    return [
        {
            "canonical_key": row.canonical_key,
            "priority": row.priority,
            "meaning": row.meaning,
        }
        for row in rows
    ]


def all_catalog_keys() -> frozenset[str]:
    return frozenset(f.canonical_key for f in build_payslip_field_catalog())
