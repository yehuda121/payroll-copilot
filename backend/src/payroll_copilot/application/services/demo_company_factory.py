"""Fictional demo-company profiles and structured extraction payloads.

Development/demo only. No PDF/OCR. Values are deterministic and internally consistent.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL

from payroll_copilot.application.services.employee_fixed_document_extractor import (
    is_valid_israeli_id,
)
from payroll_copilot.domain.enums import EmploymentType, SalaryType
from payroll_copilot.domain.seed_ids import DEMO_ORGANIZATION_ID, deterministic_employee_id

DATASET_ID = "demo_company_v1"
DEMO_COMPANY_NAMESPACE = uuid5(NAMESPACE_URL, "payroll-copilot:demo-company-v1")

# Same user id as local `/auth/dev/accountant-session`.
DEMO_PAYROLL_ACCOUNTANT_USER_ID = UUID("00000000-0000-4000-8000-000000000201")

TARGET_EMPLOYEE_COUNT = 10

# Precomputed valid checksum IDs (fictional).
_DEMO_PROFILES_RAW: tuple[dict[str, Any], ...] = (
    {
        "slot": 1,
        "national_id": "123456782",
        "first_name": "נועה",
        "last_name": "כהן",
        "employee_number": "DEMO-01",
        "monthly_salary": "12500",
        "hire_year": 2022,
        "children": (("אורי", "2018-03-12"),),
        "raise_month": 4,
        "bonus_month": 6,
        "overtime_months": (2, 5, 7),
    },
    {
        "slot": 2,
        "national_id": "234567890",
        "first_name": "יוסי",
        "last_name": "לוי",
        "employee_number": "DEMO-02",
        "monthly_salary": "9800",
        "hire_year": 2023,
        "children": (),
        "raise_month": 3,
        "bonus_month": None,
        "overtime_months": (1, 8),
    },
    {
        "slot": 3,
        "national_id": "345678901",
        "first_name": "מיכל",
        "last_name": "אברהם",
        "employee_number": "DEMO-03",
        "monthly_salary": "15200",
        "hire_year": 2021,
        "children": (("תמר", "2016-07-01"), ("דניאל", "2019-11-20")),
        "raise_month": 5,
        "bonus_month": 12,
        "overtime_months": (3, 6, 9),
    },
    {
        "slot": 4,
        "national_id": "456789012",
        "first_name": "איתי",
        "last_name": "מזרחי",
        "employee_number": "DEMO-04",
        "monthly_salary": "11000",
        "hire_year": 2024,
        "children": (("נועם", "2022-01-15"),),
        "raise_month": 7,
        "bonus_month": None,
        "overtime_months": (4,),
    },
    {
        "slot": 5,
        "national_id": "567890123",
        "first_name": "שירה",
        "last_name": "דוד",
        "employee_number": "DEMO-05",
        "monthly_salary": "13400",
        "hire_year": 2020,
        "children": (),
        "raise_month": 2,
        "bonus_month": 6,
        "overtime_months": (2, 3, 10),
    },
    {
        "slot": 6,
        "national_id": "678901234",
        "first_name": "עמית",
        "last_name": "פרץ",
        "employee_number": "DEMO-06",
        "monthly_salary": "8700",
        "hire_year": 2023,
        "children": (("ליה", "2021-09-08"),),
        "raise_month": 6,
        "bonus_month": None,
        "overtime_months": (5, 11),
    },
    {
        "slot": 7,
        "national_id": "789012345",
        "first_name": "רוני",
        "last_name": "ביטון",
        "employee_number": "DEMO-07",
        "monthly_salary": "16700",
        "hire_year": 2019,
        "children": (("מאיה", "2014-04-22"), ("יונתן", "2017-08-30")),
        "raise_month": 1,
        "bonus_month": 6,
        "overtime_months": (1, 4, 7, 10),
    },
    {
        "slot": 8,
        "national_id": "890123456",
        "first_name": "הדס",
        "last_name": "שפירא",
        "employee_number": "DEMO-08",
        "monthly_salary": "12100",
        "hire_year": 2022,
        "children": (),
        "raise_month": 8,
        "bonus_month": None,
        "overtime_months": (6,),
    },
    {
        "slot": 9,
        "national_id": "901234567",
        "first_name": "תום",
        "last_name": "גרין",
        "employee_number": "DEMO-09",
        "monthly_salary": "10500",
        "hire_year": 2024,
        "children": (("עומר", "2023-02-14"),),
        "raise_month": 9,
        "bonus_month": 6,
        "overtime_months": (2, 8),
    },
    {
        "slot": 10,
        "national_id": "012345678",
        "first_name": "יעל",
        "last_name": "אוחיון",
        "employee_number": "DEMO-10",
        "monthly_salary": "14200",
        "hire_year": 2021,
        "children": (("אלה", "2015-12-03"), ("רם", "2018-05-19"), ("סול", "2021-10-11")),
        "raise_month": 4,
        "bonus_month": None,
        "overtime_months": (3, 5, 9),
    },
)


def _money(value: Decimal | float | int | str) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(amount, "f")


def _field(value: Any, *, confidence: float = 0.97) -> dict[str, Any]:
    if value in (None, "", [], {}):
        return {
            "value": None,
            "confidence": None,
            "source_text": None,
            "status": "MISSING",
            "edited_by_user": False,
            "original_value": None,
        }
    return {
        "value": value,
        "confidence": confidence,
        "source_text": str(value) if not isinstance(value, (list, dict)) else None,
        "status": "FOUND",
        "edited_by_user": False,
        "original_value": value,
    }


def demo_document_id(key: str) -> UUID:
    return uuid5(DEMO_COMPANY_NAMESPACE, f"document:{key}")


def demo_extraction_id(document_id: UUID) -> UUID:
    return uuid5(DEMO_COMPANY_NAMESPACE, f"extraction:{document_id}")


def ensure_valid_demo_ids() -> None:
    for row in _DEMO_PROFILES_RAW:
        nid = str(row["national_id"])
        if not is_valid_israeli_id(nid):
            # Repair check digit if catalog entry drifts.
            base = "".join(ch for ch in nid if ch.isdigit())[:8].zfill(8)
            fixed = None
            for check in range(10):
                candidate = base + str(check)
                if is_valid_israeli_id(candidate):
                    fixed = candidate
                    break
            if fixed is None:
                raise RuntimeError(f"Cannot build valid Israeli ID for slot {row['slot']}")
            row["national_id"] = fixed


ensure_valid_demo_ids()


@dataclass(frozen=True, slots=True)
class DemoEmployeeProfile:
    slot: int
    national_id: str
    first_name: str
    last_name: str
    employee_number: str
    monthly_salary: Decimal
    hire_date: date
    children: tuple[tuple[str, str], ...]
    raise_month: int
    bonus_month: int | None
    overtime_months: tuple[int, ...]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def employee_id(self) -> UUID:
        return deterministic_employee_id(self.national_id)


def all_demo_profiles(*, today: date | None = None) -> list[DemoEmployeeProfile]:
    current = today or date.today()
    profiles: list[DemoEmployeeProfile] = []
    for row in _DEMO_PROFILES_RAW:
        hire_year = int(row["hire_year"])
        profiles.append(
            DemoEmployeeProfile(
                slot=int(row["slot"]),
                national_id=str(row["national_id"]),
                first_name=str(row["first_name"]),
                last_name=str(row["last_name"]),
                employee_number=str(row["employee_number"]),
                monthly_salary=Decimal(str(row["monthly_salary"])),
                hire_date=date(hire_year, 3, 1),
                children=tuple(row["children"]),
                raise_month=int(row["raise_month"]),
                bonus_month=int(row["bonus_month"]) if row["bonus_month"] else None,
                overtime_months=tuple(int(m) for m in row["overtime_months"]),
            )
        )
    # Prefer profiles whose hire predates current year for a believable Jan start.
    return sorted(profiles, key=lambda p: (p.hire_date, p.slot))


def payslip_months_through_today(*, today: date | None = None) -> list[tuple[int, int]]:
    current = today or date.today()
    return [(current.year, month) for month in range(1, current.month + 1)]


def _noise(employee_id: UUID, year: int, month: int, salt: str) -> Decimal:
    digest = hashlib.sha256(f"{employee_id}:{year}:{month}:{salt}".encode()).hexdigest()
    # 0..99 → small shekel noise
    return Decimal(int(digest[:4], 16) % 100)


def base_salary_for_month(profile: DemoEmployeeProfile, *, year: int, month: int) -> Decimal:
    base = profile.monthly_salary
    if month >= profile.raise_month:
        base = (base * Decimal("1.03")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return base


def build_national_id_structured(profile: DemoEmployeeProfile) -> dict[str, Any]:
    birth_year = max(1970, profile.hire_date.year - 30)
    return {
        "full_name": _field(profile.full_name),
        "national_id": _field(profile.national_id),
        "birth_date": _field(f"{birth_year:04d}-06-15"),
    }


def build_appendix_structured(profile: DemoEmployeeProfile) -> dict[str, Any]:
    children = [
        {"name": name, "birth_date": birth} for name, birth in profile.children
    ]
    return {
        "children": _field(children) if children else _field(None),
    }


def build_contract_structured(profile: DemoEmployeeProfile) -> dict[str, Any]:
    salary = _money(profile.monthly_salary)
    start = profile.hire_date.isoformat()
    additional = {
        "employment_commencement_date": _field(start),
        "salary_basis": _field("monthly"),
        "contractual_monthly_salary": _field(salary),
        "contractual_hourly_rate": _field(None),
        "contractual_daily_rate": _field(None),
        "employment_scope": _field("100"),
        "employment_type": _field(EmploymentType.FULL_TIME.value),
        "effective_from": _field(start),
        "effective_to": _field(None),
    }
    return {"additional_fields": additional}


def build_payslip_structured(
    profile: DemoEmployeeProfile,
    *,
    employee_id: UUID,
    year: int,
    month: int,
) -> dict[str, Any]:
    base = base_salary_for_month(profile, year=year, month=month)
    overtime_hours = Decimal("12") if month in profile.overtime_months else Decimal("0")
    overtime_pay = (overtime_hours * Decimal("65")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    bonus = Decimal("1500") if profile.bonus_month == month else Decimal("0")
    travel = Decimal("220") + _noise(employee_id, year, month, "travel") / Decimal("10")
    gross = (base + overtime_pay + bonus + travel).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    income_tax = (gross * Decimal("0.14")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    national_insurance = (gross * Decimal("0.07")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    health_tax = (gross * Decimal("0.032")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    pension_employee = (gross * Decimal("0.06")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    pension_employer = (gross * Decimal("0.065")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_deductions = (
        income_tax + national_insurance + health_tax + pension_employee
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = (gross - total_deductions).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    vacation_balance = max(0, 18 - (month - 1) - (1 if month in {3, 8} else 0))
    sick_balance = max(0, 12 - (1 if month in {2, 11} else 0))
    regular_hours = Decimal("182")
    work_days = 22 if month not in {4, 9, 10} else 20

    return {
        "employee_name": _field(profile.full_name),
        "employee_id": _field(profile.national_id),
        "employee_number": _field(profile.employee_number),
        "pay_period": _field(f"{year:04d}-{month:02d}"),
        "employment_type": _field(EmploymentType.FULL_TIME.value),
        "department": _field("כללי"),
        "base_salary": _field(_money(base)),
        "travel_expenses": _field(_money(travel)),
        "regular_hours": _field(_money(regular_hours)),
        "overtime_hours": _field(_money(overtime_hours)),
        "gross_salary": _field(_money(gross)),
        "income_tax": _field(_money(income_tax)),
        "national_insurance": _field(_money(national_insurance)),
        "health_tax": _field(_money(health_tax)),
        "pension_employee": _field(_money(pension_employee)),
        "pension_employer": _field(_money(pension_employer)),
        "net_salary": _field(_money(net)),
        "vacation_balance": _field(str(vacation_balance)),
        "sick_leave_balance": _field(str(sick_balance)),
        "payment_method": _field("bank_transfer"),
        "additional_fields": {
            "national_id": _field(profile.national_id),
            "total_deductions": _field(_money(total_deductions)),
            "employer_name": _field("חברת הדגמה בע״מ"),
            "work_days": _field(str(work_days)),
            "work_hours": _field(_money(regular_hours + overtime_hours)),
            "bonus": _field(_money(bonus)) if bonus > 0 else _field(None),
        },
    }


def content_fingerprint(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "DATASET_ID",
    "DEMO_ORGANIZATION_ID",
    "DEMO_PAYROLL_ACCOUNTANT_USER_ID",
    "TARGET_EMPLOYEE_COUNT",
    "DemoEmployeeProfile",
    "SalaryType",
    "EmploymentType",
    "all_demo_profiles",
    "payslip_months_through_today",
    "build_national_id_structured",
    "build_appendix_structured",
    "build_contract_structured",
    "build_payslip_structured",
    "demo_document_id",
    "demo_extraction_id",
    "content_fingerprint",
    "deterministic_employee_id",
]
