"""Helpers for EMPLOYEE payslip↔profile comparison rules.

Reuses identity-gate normalization helpers — does not invent alternate equality.

Employment start / seniority are NOT compared here: Employee.contract_start_date is
overloaded (often create/onboarding default) and is not confirmed contract
employment-commencement data. See CONTRACT train audit.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.payslip_identity_comparison import (
    names_share_comparable_language,
    normalize_employee_number,
    normalize_national_id_digits,
    person_name_tokens_equal,
)
from payroll_copilot.application.validation.structured_payslip_mapper import (
    coerce_employment_type,
)
from payroll_copilot.domain.entities import Employee, PayslipData
from payroll_copilot.domain.enums import EmploymentType
from payroll_copilot.domain.rules import ValidationContext


def has_authorized_employee(context: ValidationContext) -> bool:
    return bool(context.authorized_employee)


def additional_value(payslip: PayslipData, key: str) -> Any | None:
    raw = (payslip.additional_fields or {}).get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict) and "value" in raw:
        value = raw.get("value")
        return None if value is None or value == "" else value
    return raw


def payslip_national_id(payslip: PayslipData) -> Any | None:
    """Same preference order as identity gate: national_id, else digit-bearing employee_id."""
    nid = additional_value(payslip, "national_id")
    if normalize_national_id_digits(nid) is not None:
        return nid
    legacy = additional_value(payslip, "employee_id")
    if normalize_national_id_digits(legacy) is not None:
        return legacy
    return None


def trusted_employee_display_name(employee: Employee) -> str:
    meta = employee.metadata or {}
    verified = meta.get("verified_display_name")
    if isinstance(verified, str) and verified.strip():
        return verified.strip()
    return f"{employee.first_name} {employee.last_name}".strip()


def national_id_outcome(
    *,
    payslip: PayslipData,
    trusted_national_id: str | None,
) -> str:
    """Return match | mismatch | missing_payslip | missing_reference."""
    payslip_raw = payslip_national_id(payslip)
    payslip_digits = normalize_national_id_digits(payslip_raw)
    trusted_digits = normalize_national_id_digits(trusted_national_id)
    if payslip_digits is None:
        return "missing_payslip"
    if trusted_digits is None:
        return "missing_reference"
    return "match" if payslip_digits == trusted_digits else "mismatch"


def employee_number_outcome(*, payslip: PayslipData, employee: Employee) -> str:
    """Compare payroll/system employee number — never National ID."""
    payslip_raw = additional_value(payslip, "employee_number")
    if payslip_raw is None:
        cand = payslip.employee_number
        if cand and not str(cand).startswith("guest-"):
            nid_digits = normalize_national_id_digits(payslip_national_id(payslip))
            cand_digits = normalize_national_id_digits(cand)
            # If the only available "number" is the same as National ID, it is not a payroll number.
            if nid_digits and cand_digits == nid_digits and len(nid_digits) >= 8:
                payslip_raw = None
            else:
                payslip_raw = cand
    payslip_norm = normalize_employee_number(payslip_raw)
    trusted_norm = normalize_employee_number(employee.employee_number)
    if payslip_norm is None:
        return "missing_payslip"
    if trusted_norm is None:
        return "missing_reference"
    return "match" if payslip_norm == trusted_norm else "mismatch"


def employee_name_outcome(*, payslip: PayslipData, employee: Employee) -> str:
    payslip_name = (payslip.employee_name or "").strip() or None
    trusted = trusted_employee_display_name(employee)
    if not payslip_name:
        return "missing_payslip"
    if not trusted:
        return "missing_reference"
    if not names_share_comparable_language(payslip_name, trusted):
        return "cannot_compare"
    if person_name_tokens_equal(payslip_name, trusted):
        return "match"
    return "mismatch"


def employment_type_outcome(*, payslip: PayslipData, employee: Employee) -> str:
    raw = additional_value(payslip, "employment_type")
    if raw is None:
        return "missing_payslip"
    payslip_type = coerce_employment_type(raw)
    if payslip_type is None:
        # Unrecognized token is SANITY's job — not profile mismatch.
        return "missing_payslip"
    profile_type = employee.employment_type
    if profile_type is None or profile_type == EmploymentType.UNKNOWN:
        return "missing_reference"
    return "match" if payslip_type == profile_type else "mismatch"


def pay_period_vs_selected_outcome(context: ValidationContext) -> str:
    """Compare payslip period to selected workspace/document month (not a contract check)."""
    period = context.payslip.period
    selected_y = context.selected_period_year
    selected_m = context.selected_period_month
    if period is None:
        return "missing_payslip"
    if not selected_y or not selected_m:
        return "missing_reference"
    if period.year == int(selected_y) and period.month == int(selected_m):
        return "match"
    return "mismatch"
