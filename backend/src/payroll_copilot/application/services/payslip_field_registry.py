"""Payslip Field Registry — presentation metadata over existing canonical keys.

KEEP AS-IS:
  - DynamicDocumentEntry (extraction SoT)
  - PAYSLIP_FIELD_KEYS / resolve_canonical_key / projector behavior

This registry is additive metadata for Digital Payslip projection.
It does NOT change extraction, confirmation gates, or persistence blockers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_CANONICAL_EXTRA_KEYS,
    PAYSLIP_FIELD_KEYS,
)
from payroll_copilot.application.services.dynamic_document import resolve_canonical_key


class FieldRequirementCategory(StrEnum):
    REQUIRED = "required"
    EXPECTED = "expected"
    OTHER = "other"


class PayslipFieldSection(StrEnum):
    IDENTITY = "identity"
    EMPLOYER = "employer"
    PERIOD = "period"
    EARNINGS = "earnings"
    DEDUCTIONS = "deductions"
    PAYMENT = "payment"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class PayslipFieldDefinition:
    """Known payslip field presentation definition."""

    canonical_key: str
    label_i18n_key: str
    section: PayslipFieldSection
    display_order: int
    requirement_category: FieldRequirementCategory
    editable: bool = True
    # Reserved for future policy — NOT enforced as a new persistence gate.
    required_on_payslip: bool = False
    required_for_persistence: bool = False


# National ID is the government identity field (required_on_payslip).
# employee_id is the payroll/system employee identifier (expected) — never the same concept.
# employee_number remains the organization employee number.
_REQUIRED_KEYS: tuple[tuple[str, PayslipFieldSection, int], ...] = (
    ("employee_name", PayslipFieldSection.IDENTITY, 10),
    ("national_id", PayslipFieldSection.IDENTITY, 20),
    ("employer_name", PayslipFieldSection.EMPLOYER, 25),
    ("employer_id", PayslipFieldSection.EMPLOYER, 26),
    ("employer_address", PayslipFieldSection.EMPLOYER, 27),
    ("employment_start_date", PayslipFieldSection.IDENTITY, 28),
    ("employment_scope", PayslipFieldSection.IDENTITY, 29),
    ("pay_period", PayslipFieldSection.PERIOD, 30),
    ("base_salary", PayslipFieldSection.EARNINGS, 40),
    ("salary_calculation_basis", PayslipFieldSection.EARNINGS, 45),
    ("gross_salary", PayslipFieldSection.EARNINGS, 50),
    ("income_tax", PayslipFieldSection.DEDUCTIONS, 60),
    ("national_insurance", PayslipFieldSection.DEDUCTIONS, 70),
    ("total_deductions", PayslipFieldSection.DEDUCTIONS, 80),
    ("net_salary", PayslipFieldSection.PAYMENT, 90),
    ("amount_paid", PayslipFieldSection.PAYMENT, 95),
    ("payment_method", PayslipFieldSection.PAYMENT, 100),
    ("minimum_wage_monthly", PayslipFieldSection.OTHER, 105),
    ("minimum_wage_hourly", PayslipFieldSection.OTHER, 106),
)

_EXPECTED_KEYS: tuple[tuple[str, PayslipFieldSection, int], ...] = (
    ("employee_number", PayslipFieldSection.IDENTITY, 110),
    ("employee_id", PayslipFieldSection.IDENTITY, 115),  # payroll/system ID — not National ID
    ("employment_type", PayslipFieldSection.IDENTITY, 120),
    ("seniority_years", PayslipFieldSection.IDENTITY, 125),
    ("department", PayslipFieldSection.IDENTITY, 130),
    ("hourly_rate", PayslipFieldSection.EARNINGS, 140),
    ("regular_hours", PayslipFieldSection.EARNINGS, 150),
    ("overtime_hours", PayslipFieldSection.EARNINGS, 160),
    ("travel_expenses", PayslipFieldSection.EARNINGS, 170),
    ("health_tax", PayslipFieldSection.DEDUCTIONS, 180),
    ("pension_employee", PayslipFieldSection.DEDUCTIONS, 190),
    ("pension_employer", PayslipFieldSection.DEDUCTIONS, 200),
    ("severance", PayslipFieldSection.DEDUCTIONS, 210),
    ("training_fund", PayslipFieldSection.DEDUCTIONS, 220),
    ("bank_name", PayslipFieldSection.PAYMENT, 230),
    ("bank_branch", PayslipFieldSection.PAYMENT, 231),
    ("bank_account", PayslipFieldSection.PAYMENT, 232),
    ("vacation_balance", PayslipFieldSection.OTHER, 240),
    ("sick_leave_balance", PayslipFieldSection.OTHER, 250),
    ("messages", PayslipFieldSection.OTHER, 260),
)

# Persistence-critical candidates (metadata only — gates already enforce NID/period).
_PERSISTENCE_CRITICAL: frozenset[str] = frozenset(
    {
        "employee_name",
        "national_id",
        "employee_number",
        "pay_period",
    }
)


def _build_registry() -> dict[str, PayslipFieldDefinition]:
    defs: dict[str, PayslipFieldDefinition] = {}
    for key, section, order in _REQUIRED_KEYS:
        defs[key] = PayslipFieldDefinition(
            canonical_key=key,
            label_i18n_key=f"payroll.fields.{key}",
            section=section,
            display_order=order,
            requirement_category=FieldRequirementCategory.REQUIRED,
            editable=True,
            required_on_payslip=True,
            required_for_persistence=key in _PERSISTENCE_CRITICAL,
        )
    for key, section, order in _EXPECTED_KEYS:
        defs[key] = PayslipFieldDefinition(
            canonical_key=key,
            label_i18n_key=f"payroll.fields.{key}",
            section=section,
            display_order=order,
            requirement_category=FieldRequirementCategory.EXPECTED,
            editable=True,
            required_on_payslip=False,
            required_for_persistence=key in _PERSISTENCE_CRITICAL,
        )
    order_cursor = 900
    for key in (*PAYSLIP_FIELD_KEYS, *PAYSLIP_CANONICAL_EXTRA_KEYS):
        if key in defs:
            continue
        defs[key] = PayslipFieldDefinition(
            canonical_key=key,
            label_i18n_key=f"payroll.fields.{key}",
            section=PayslipFieldSection.OTHER,
            display_order=order_cursor,
            requirement_category=FieldRequirementCategory.OTHER,
            editable=True,
            required_on_payslip=False,
            required_for_persistence=False,
        )
        order_cursor += 10
    return defs


_REGISTRY: dict[str, PayslipFieldDefinition] = _build_registry()


def get_field_definition(key: str) -> PayslipFieldDefinition | None:
    normalized = (key or "").strip()
    if not normalized:
        return None
    if normalized in _REGISTRY:
        return _REGISTRY[normalized]
    canonical = resolve_canonical_key(normalized)
    if canonical and canonical in _REGISTRY:
        return _REGISTRY[canonical]
    return None


def list_field_definitions(
    *,
    categories: Iterable[FieldRequirementCategory] | None = None,
) -> list[PayslipFieldDefinition]:
    items = list(_REGISTRY.values())
    if categories is not None:
        allowed = set(categories)
        items = [item for item in items if item.requirement_category in allowed]
    return sorted(items, key=lambda item: (item.display_order, item.canonical_key))


def required_on_payslip_keys() -> frozenset[str]:
    return frozenset(
        item.canonical_key for item in _REGISTRY.values() if item.required_on_payslip
    )


def requirement_category_for_key(key: str) -> FieldRequirementCategory:
    definition = get_field_definition(key)
    if definition is None:
        return FieldRequirementCategory.OTHER
    return definition.requirement_category


def registry_snapshot_for_tests() -> dict[str, dict[str, object]]:
    """Stable dump for FE/BE sync tests."""
    return {
        key: {
            "canonical_key": item.canonical_key,
            "requirement_category": item.requirement_category.value,
            "section": item.section.value,
            "display_order": item.display_order,
            "required_on_payslip": item.required_on_payslip,
            "required_for_persistence": item.required_for_persistence,
            "editable": item.editable,
            "label_i18n_key": item.label_i18n_key,
        }
        for key, item in sorted(_REGISTRY.items())
    }
