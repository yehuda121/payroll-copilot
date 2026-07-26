"""Map structured parser JSON → domain PayslipData / ValidationContext inputs.

Never feeds raw OCR text into validation. Never invents values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_FIELD_KEYS,
    ExtractedField,
    FieldExtractionStatus,
)
from payroll_copilot.application.use_cases.validation import RunValidationCommand
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.domain.seed_ids import DEMO_ORGANIZATION_ID
from payroll_copilot.domain.value_objects import Money, PayPeriod

_CORE_FIELDS = frozenset(
    {
        "employee_name",
        "employee_number",
        "pay_period",
        "base_salary",
        "gross_salary",
        "net_salary",
        "regular_hours",
        "overtime_hours",
        "income_tax",
        "pension_employee",
    }
)

_UNCERTAIN_CONFIDENCE_CAP = 0.55


@dataclass(frozen=True, slots=True)
class MappedValidationInputs:
    command: RunValidationCommand
    organization_id: UUID
    document_id: UUID
    extraction_connected: bool
    core_fields_usable: bool
    unused_fields: tuple[str, ...] = ()
    mapping_warnings: tuple[str, ...] = field(default_factory=tuple)


def _as_field(raw: Any) -> ExtractedField:
    if isinstance(raw, ExtractedField):
        return raw
    if not isinstance(raw, dict):
        return ExtractedField(status=FieldExtractionStatus.MISSING)
    try:
        return ExtractedField.model_validate(raw)
    except Exception:  # noqa: BLE001
        return ExtractedField(status=FieldExtractionStatus.MISSING)


def coerce_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value if value >= 0 else None
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip()
        cleaned = cleaned.replace("₪", "").replace("ILS", "").replace("NIS", "")
        cleaned = cleaned.replace(",", "").replace(" ", "")
        cleaned = re.sub(r"[^\d.\-]", "", cleaned)
        if not cleaned or cleaned in {".", "-", "-."}:
            return None
        try:
            number = Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
        if number < 0:
            return None
        return number
    return None


def coerce_money(value: Any) -> Money | None:
    amount = coerce_decimal(value)
    if amount is None:
        return None
    try:
        return Money(amount=amount, currency="ILS")
    except ValueError:
        return None


def coerce_pay_period(value: Any) -> PayPeriod | None:
    if value is None:
        return None
    if isinstance(value, dict):
        year = value.get("year")
        month = value.get("month")
        try:
            year_i, month_i = int(year), int(month)
            if not 1 <= month_i <= 12:
                return None
            return PayPeriod(year=year_i, month=month_i)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        # Anchored numeric patterns only — never substring-match (e.g. "13/2024"
        # must not become March 2024 via the trailing "3/2024").
        match = re.fullmatch(
            r"(?:(\d{1,2})[/\-.](\d{4})|(\d{4})[/\-.](\d{1,2}))",
            text,
        )
        if match is None:
            return None
        if match.group(1) is not None:
            month, year = int(match.group(1)), int(match.group(2))
        else:
            year, month = int(match.group(3)), int(match.group(4))
        if not 1 <= month <= 12:
            return None
        try:
            return PayPeriod(year=year, month=month)
        except ValueError:
            return None
    return None


def _usable_value(extracted: ExtractedField) -> Any | None:
    if extracted.status == FieldExtractionStatus.MISSING:
        return None
    if extracted.value is None or extracted.value == "":
        return None
    return extracted.value


def _confidence_for(extracted: ExtractedField) -> float | None:
    if extracted.edited_by_user:
        return 1.0
    if extracted.confidence is None:
        return None
    if extracted.status == FieldExtractionStatus.UNCERTAIN:
        return min(extracted.confidence, _UNCERTAIN_CONFIDENCE_CAP)
    return extracted.confidence


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if not parts:
        return ("Guest", "Employee")
    if len(parts) == 1:
        return (parts[0], "Employee")
    return (parts[0], " ".join(parts[1:]))


def coerce_employment_type(value: Any) -> EmploymentType | None:
    """Map recognized payslip employment-type tokens to EmploymentType.

    Returns None for missing or unrecognized values — never invents FULL_TIME.
    Does not map salary modes (hourly/monthly/daily); those are not EmploymentType.
    """
    if value is None or value == "":
        return None
    text = str(value).strip().casefold()
    if not text:
        return None
    mapping = {
        "full_time": EmploymentType.FULL_TIME,
        "full-time": EmploymentType.FULL_TIME,
        "fulltime": EmploymentType.FULL_TIME,
        "full time": EmploymentType.FULL_TIME,
        "part_time": EmploymentType.PART_TIME,
        "part-time": EmploymentType.PART_TIME,
        "parttime": EmploymentType.PART_TIME,
        "part time": EmploymentType.PART_TIME,
        "contractor": EmploymentType.CONTRACTOR,
        "intern": EmploymentType.INTERN,
        "pre_intern": EmploymentType.PRE_INTERN,
        "pre-intern": EmploymentType.PRE_INTERN,
        "preintern": EmploymentType.PRE_INTERN,
    }
    return mapping.get(text)


def _employment_type_for_validation_employee(value: Any) -> EmploymentType:
    """Employment type on the synthetic validation Employee — UNKNOWN when not recognized."""
    return coerce_employment_type(value) or EmploymentType.UNKNOWN


def map_structured_payslip_to_validation_inputs(
    *,
    document_id: UUID,
    structured_data: dict[str, Any],
    employee_id: UUID | None = None,
    organization_id: UUID | None = None,
    parser_completed: bool = True,
) -> MappedValidationInputs:
    """Build RunValidationCommand from parser structured fields only."""
    fields = {key: _as_field(structured_data.get(key)) for key in PAYSLIP_FIELD_KEYS}
    additional_raw = structured_data.get("additional_fields") or {}
    additional: dict[str, ExtractedField] = {}
    if isinstance(additional_raw, dict):
        for key, value in additional_raw.items():
            additional[str(key)] = _as_field(value)

    confidences: dict[str, float] = {}
    warnings: list[str] = []

    def take(key: str) -> Any | None:
        extracted = fields[key]
        value = _usable_value(extracted)
        conf = _confidence_for(extracted)
        if conf is not None and value is not None:
            confidences[key] = conf
        return value

    employee_name = take("employee_name")
    employee_number = take("employee_number") or take("employee_id")
    first_name, last_name = _split_name(str(employee_name) if employee_name else "Guest Employee")

    hourly_rate_raw = take("hourly_rate")
    hourly_rate = coerce_decimal(hourly_rate_raw)
    if hourly_rate_raw is not None and hourly_rate is None:
        warnings.append("hourly_rate_invalid")

    base_salary = coerce_money(take("base_salary"))
    gross_salary = coerce_money(take("gross_salary"))
    net_salary = coerce_money(take("net_salary"))
    tax_deducted = coerce_money(take("income_tax"))
    pension_employee = coerce_money(take("pension_employee"))
    pension_employer = coerce_money(take("pension_employer"))
    transportation = coerce_money(take("travel_expenses"))

    overtime_hours = coerce_decimal(take("overtime_hours"))
    work_hours = coerce_decimal(take("regular_hours"))
    pay_period_raw_value = take("pay_period")
    parsed_period = coerce_pay_period(pay_period_raw_value)
    # Engine requires a PayPeriod handle; never invent payslip.period when missing.
    period = parsed_period or PayPeriod(year=date.today().year, month=date.today().month)
    if parsed_period is None:
        warnings.append("pay_period_missing")
        if pay_period_raw_value is not None:
            warnings.append("pay_period_unparseable")

    deductions: dict[str, Money] = {}
    for ded_key in ("national_insurance", "health_tax", "severance", "training_fund"):
        money = coerce_money(take(ded_key))
        if money is not None:
            deductions[ded_key] = money

    # Balances stay additional only — never mapped as days_used.
    payslip_additional: dict[str, Any] = {}
    for balance_key in ("vacation_balance", "sick_leave_balance", "payment_method", "messages"):
        value = take(balance_key)
        if value is not None:
            payslip_additional[balance_key] = value
    for key, extracted in additional.items():
        value = _usable_value(extracted)
        if value is not None:
            payslip_additional[key] = value
            conf = _confidence_for(extracted)
            if conf is not None:
                confidences[key] = conf

    # Preserve payroll employee_id for legacy National ID SANITY fallback (8–9 digits).
    employee_id_value = _usable_value(fields["employee_id"])
    if employee_id_value is not None and "employee_id" not in payslip_additional:
        payslip_additional["employee_id"] = employee_id_value
        conf = _confidence_for(fields["employee_id"])
        if conf is not None:
            confidences.setdefault("employee_id", conf)

    if pay_period_raw_value is not None and parsed_period is None:
        payslip_additional["pay_period_raw"] = pay_period_raw_value

    department_label = take("department")
    if department_label is not None:
        payslip_additional["department_label"] = department_label

    employment_type_raw = take("employment_type")
    if employment_type_raw is not None and "employment_type" not in payslip_additional:
        # Preserve original extracted token for review / future SANITY; do not invent meaning.
        payslip_additional["employment_type"] = employment_type_raw
    employment_type = _employment_type_for_validation_employee(employment_type_raw)
    if employment_type_raw is not None and coerce_employment_type(employment_type_raw) is None:
        warnings.append("employment_type_unrecognized")

    # Preserve dedicated employee_number when present (distinct from employee_id / national_id).
    employee_number_dedicated = _usable_value(fields["employee_number"])
    if employee_number_dedicated is not None and "employee_number" not in payslip_additional:
        payslip_additional["employee_number"] = employee_number_dedicated

    salary_type = SalaryType.HOURLY if hourly_rate is not None else SalaryType.MONTHLY
    org_id = organization_id or DEMO_ORGANIZATION_ID
    department_id = uuid4()
    emp_id = employee_id or uuid4()

    employee = Employee(
        id=emp_id,
        organization_id=org_id,
        employee_number=str(employee_number) if employee_number else f"guest-{document_id.hex[:8]}",
        first_name=first_name,
        last_name=last_name,
        department_id=department_id,
        employment_type=employment_type,
        salary_type=salary_type,
        contract_start_date=(
            date(parsed_period.year, parsed_period.month, 1)
            if parsed_period is not None
            else date(period.year, period.month, 1)
        ),
        status=EmployeeStatus.ACTIVE,
        hourly_rate=hourly_rate,
        monthly_salary=base_salary.amount if base_salary and salary_type == SalaryType.MONTHLY else None,
        metadata={"guest_synthetic": True},
    )
    department = Department(
        id=department_id,
        organization_id=org_id,
        code="payroll",
        name={"he": "שכר", "en": "Payroll", "ar": "الرواتب"},
        rule_profile="payroll",
    )
    payslip = PayslipData(
        employee_number=employee.employee_number,
        # Do not invent a display name when extraction left the field empty.
        employee_name=str(employee_name).strip() if employee_name else None,
        period=parsed_period,
        gross_salary=gross_salary,
        net_salary=net_salary,
        base_salary=base_salary,
        overtime_hours=overtime_hours,
        tax_deducted=tax_deducted,
        pension_employee=pension_employee,
        pension_employer=pension_employer,
        transportation_allowance=transportation,
        work_hours=work_hours,
        deductions=deductions,
        additional_fields=payslip_additional,
    )

    if "regular_hours" in confidences and "work_hours" not in confidences:
        confidences["work_hours"] = confidences["regular_hours"]
    if "travel_expenses" in confidences and "transportation_allowance" not in confidences:
        confidences["transportation_allowance"] = confidences["travel_expenses"]
    if "income_tax" in confidences and "tax_deducted" not in confidences:
        confidences["tax_deducted"] = confidences["income_tax"]

    core_usable = 0
    for key in _CORE_FIELDS:
        extracted = fields[key]
        if _usable_value(extracted) is None:
            continue
        if key in {"base_salary", "gross_salary", "net_salary", "income_tax", "pension_employee"}:
            if coerce_money(extracted.value) is not None or extracted.edited_by_user:
                core_usable += 1
        elif key in {"regular_hours", "overtime_hours"}:
            if coerce_decimal(extracted.value) is not None or extracted.edited_by_user:
                core_usable += 1
        else:
            core_usable += 1

    command = RunValidationCommand(
        payslip=payslip,
        employee=employee,
        department=department,
        period=period,
        field_confidences=confidences,
    )
    return MappedValidationInputs(
        command=command,
        organization_id=org_id,
        document_id=document_id,
        extraction_connected=bool(parser_completed),
        core_fields_usable=core_usable >= 3,
        unused_fields=("vacation_balance", "sick_leave_balance"),
        mapping_warnings=tuple(warnings),
    )
