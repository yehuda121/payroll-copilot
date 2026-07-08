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
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DEMO_ORGANIZATION_ID,
)
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
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
            return PayPeriod(year=int(year), month=int(month))
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        match = re.search(r"(20\d{2})[^\d]?(0?[1-9]|1[0-2])", text)
        if match:
            try:
                return PayPeriod(year=int(match.group(1)), month=int(match.group(2)))
            except ValueError:
                return None
        match = re.search(r"(0?[1-9]|1[0-2])[^\d](20\d{2})", text)
        if match:
            try:
                return PayPeriod(year=int(match.group(2)), month=int(match.group(1)))
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


def _employment_type(value: Any) -> EmploymentType:
    if value is None:
        return EmploymentType.FULL_TIME
    text = str(value).strip().casefold()
    mapping = {
        "full_time": EmploymentType.FULL_TIME,
        "full-time": EmploymentType.FULL_TIME,
        "fulltime": EmploymentType.FULL_TIME,
        "part_time": EmploymentType.PART_TIME,
        "part-time": EmploymentType.PART_TIME,
        "parttime": EmploymentType.PART_TIME,
        "contractor": EmploymentType.CONTRACTOR,
        "hourly": EmploymentType.HOURLY,
        "intern": EmploymentType.INTERN,
    }
    return mapping.get(text, EmploymentType.FULL_TIME)


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
    parsed_period = coerce_pay_period(take("pay_period"))
    # Engine requires a PayPeriod handle; never invent payslip.period when missing.
    period = parsed_period or PayPeriod(year=date.today().year, month=date.today().month)
    if parsed_period is None:
        warnings.append("pay_period_missing")

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

    department_label = take("department")
    if department_label is not None:
        payslip_additional["department_label"] = department_label

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
        employment_type=_employment_type(take("employment_type")),
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
        employee_name=str(employee_name) if employee_name else employee.full_name,
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
