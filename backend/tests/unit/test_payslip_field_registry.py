"""Unit tests for payslip field registry (canonical completion train)."""

from __future__ import annotations

from payroll_copilot.application.ports.payslip_parser import (
    PAYSLIP_CANONICAL_EXTRA_KEYS,
    PAYSLIP_FIELD_KEYS,
)
from payroll_copilot.application.services.payslip_field_registry import (
    FieldRequirementCategory,
    get_field_definition,
    registry_snapshot_for_tests,
    required_on_payslip_keys,
    requirement_category_for_key,
)


def test_national_id_is_required_employee_id_is_expected() -> None:
    required = required_on_payslip_keys()
    assert "national_id" in required
    assert "employee_id" not in required
    assert requirement_category_for_key("employee_id") == FieldRequirementCategory.EXPECTED
    assert get_field_definition("national_id") is not None
    assert get_field_definition("national_id").required_on_payslip is True


def test_new_canonical_concepts_are_registered() -> None:
    for key in (
        "employer_name",
        "employer_id",
        "employer_address",
        "employment_start_date",
        "seniority_years",
        "employment_scope",
        "salary_calculation_basis",
        "amount_paid",
        "bank_name",
        "bank_branch",
        "bank_account",
        "minimum_wage_monthly",
        "minimum_wage_hourly",
    ):
        assert get_field_definition(key) is not None
        assert key in PAYSLIP_CANONICAL_EXTRA_KEYS


def test_amount_paid_distinct_from_net() -> None:
    paid = get_field_definition("amount_paid")
    net = get_field_definition("net_salary")
    assert paid is not None and net is not None
    assert paid.canonical_key != net.canonical_key
    assert paid.required_on_payslip is True


def test_required_for_persistence_unchanged_semantics() -> None:
    assert get_field_definition("gross_salary").required_for_persistence is False
    assert get_field_definition("national_id").required_for_persistence is True
    assert get_field_definition("employee_id").required_for_persistence is False


def test_every_payslip_field_key_has_definition() -> None:
    for key in PAYSLIP_FIELD_KEYS:
        assert get_field_definition(key) is not None


def test_registry_snapshot_national_id_semantics() -> None:
    snap = registry_snapshot_for_tests()
    assert snap["national_id"]["required_on_payslip"] is True
    assert snap["employee_id"]["required_on_payslip"] is False
    assert snap["employee_id"]["requirement_category"] == "expected"
    assert snap["employer_name"]["section"] == "employer"
    assert snap["minimum_wage_monthly"]["required_on_payslip"] is True
