"""Document-only accessors for payslip SANITY rules.

Reads confirmed canonical PayslipData / additional_fields only — never employee
profile, contract, or law thresholds.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.employee_document_form_schemas import (
    normalize_birth_date,
)
from payroll_copilot.application.services.employee_fixed_document_extractor import (
    is_valid_israeli_id,
)
from payroll_copilot.application.services.parser_evidence import (
    employee_name_implausible_reason,
    pay_period_implausible_reason,
    pay_period_looks_structured,
)
from payroll_copilot.application.services.payslip_identity_comparison import (
    normalize_national_id_digits,
)
from payroll_copilot.application.validation.structured_payslip_mapper import (
    coerce_employment_type,
)
from payroll_copilot.domain.entities import PayslipData
from payroll_copilot.domain.value_objects import Money, PayPeriod

# Same calendar window already used by extraction plausibility (parser_evidence).
_PAY_PERIOD_YEAR_MIN = 1990
_PAY_PERIOD_YEAR_MAX = 2100

# Legacy employee_id may hold a National ID only when digit length matches Israeli ID shape.
_LEGACY_NATIONAL_ID_DIGIT_LEN = frozenset({8, 9})


def additional_value(payslip: PayslipData, key: str) -> Any | None:
    raw = (payslip.additional_fields or {}).get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict) and "value" in raw:
        value = raw.get("value")
        return None if value is None or value == "" else value
    return raw


def resolve_national_id_raw(payslip: PayslipData) -> tuple[Any | None, str | None]:
    """Prefer ``national_id``; legacy ``employee_id`` only when 8–9 digit shaped."""
    nid = additional_value(payslip, "national_id")
    if nid is not None:
        return nid, "national_id"
    legacy = additional_value(payslip, "employee_id")
    digits = normalize_national_id_digits(legacy)
    if digits is not None and len(digits) in _LEGACY_NATIONAL_ID_DIGIT_LEN:
        return legacy, "employee_id"
    return None, None


def national_id_digits(raw: Any) -> str | None:
    return normalize_national_id_digits(raw)


def national_id_length_ok(digits: str) -> bool:
    """Israeli National ID is exactly 9 digits after normalization (FE form contract)."""
    return len(digits) == 9


def national_id_checksum_ok(digits: str) -> bool:
    return is_valid_israeli_id(digits)


def name_structure_fail_reason(value: Any) -> str | None:
    return employee_name_implausible_reason(value)


def pay_period_raw(payslip: PayslipData) -> Any | None:
    """Unparsed period text preserved by the mapper when coerce failed."""
    return additional_value(payslip, "pay_period_raw")


def pay_period_calendar_fail_reason(period: PayPeriod | None) -> str | None:
    if period is None:
        return None
    if not 1 <= period.month <= 12:
        return "implausible_pay_period_month"
    if period.year < _PAY_PERIOD_YEAR_MIN or period.year > _PAY_PERIOD_YEAR_MAX:
        return "implausible_pay_period_year"
    return None


def pay_period_raw_fail_reason(raw: Any) -> str | None:
    """When a period string matched a numeric pattern but is calendar-invalid."""
    return pay_period_implausible_reason(raw)


def pay_period_looks_numeric(raw: Any) -> bool:
    return pay_period_looks_structured(raw)


def employment_start_date_fail_reason(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if not text:
        return None
    if normalize_birth_date(text) is None:
        return "invalid_calendar_date"
    return None


def money_amount(value: Money | None) -> Any | None:
    return None if value is None else value.amount


def required_field_present(payslip: PayslipData, field_key: str) -> bool:
    """True when the canonical document field has a usable value."""
    key = (field_key or "").strip()
    if key == "employee_name":
        text = (payslip.employee_name or "").strip()
        return bool(text)
    if key == "pay_period":
        return payslip.period is not None
    if key == "base_salary":
        return payslip.base_salary is not None
    if key == "gross_salary":
        return payslip.gross_salary is not None
    if key == "net_salary":
        return payslip.net_salary is not None
    if key == "income_tax":
        return payslip.tax_deducted is not None
    if key == "national_insurance":
        return "national_insurance" in (payslip.deductions or {})
    if key == "national_id":
        raw, _ = resolve_national_id_raw(payslip)
        return raw is not None and national_id_digits(raw) is not None
    # Canonical extras and other required keys live in additional_fields.
    return additional_value(payslip, key) is not None


def employment_type_raw(payslip: PayslipData) -> Any | None:
    return additional_value(payslip, "employment_type")


def employment_type_recognized(raw: Any) -> bool:
    return coerce_employment_type(raw) is not None
