"""Unit tests for validation taxonomy derive-on-read mapping."""

from __future__ import annotations

from payroll_copilot.application.services.validation_taxonomy import (
    ValidationTaxonomy,
    bound_rule_ids_for_field,
    taxonomy_for_gate_field,
    taxonomy_for_rule_id,
    ui_group_for_taxonomy,
)
from payroll_copilot.domain.enums import RuleCategory


def test_executing_legal_rules_map_to_law() -> None:
    assert taxonomy_for_rule_id("legal.overtime.daily_limit") == ValidationTaxonomy.LAW
    assert taxonomy_for_rule_id("legal.minimum_wage") == ValidationTaxonomy.LAW


def test_department_rules_map_to_contract() -> None:
    assert (
        taxonomy_for_rule_id("department.intern.weekly_hours_limit")
        == ValidationTaxonomy.CONTRACT
    )


def test_category_fallback() -> None:
    assert taxonomy_for_rule_id("unknown.rule", RuleCategory.LEGAL.value) == ValidationTaxonomy.LAW
    assert (
        taxonomy_for_rule_id("unknown.rule", RuleCategory.HISTORICAL.value)
        == ValidationTaxonomy.EMPLOYEE
    )


def test_contract_surfaces_under_employee_checks_ui() -> None:
    assert ui_group_for_taxonomy(ValidationTaxonomy.CONTRACT) == "employee_checks"
    assert ui_group_for_taxonomy(ValidationTaxonomy.LAW) == "law_checks"
    assert ui_group_for_taxonomy(ValidationTaxonomy.SANITY) == "digital"


def test_gate_fields_are_employee() -> None:
    assert taxonomy_for_gate_field("national_id") == ValidationTaxonomy.EMPLOYEE
    assert taxonomy_for_gate_field("pay_period") == ValidationTaxonomy.EMPLOYEE


def test_field_bindings_are_explicit_only() -> None:
    assert "legal.overtime.daily_limit" in bound_rule_ids_for_field("overtime_hours")
    assert "sanity.required.base_salary" in bound_rule_ids_for_field("base_salary")
    assert "sanity.national_id.checksum" in bound_rule_ids_for_field("national_id")
    assert bound_rule_ids_for_field("messages") == frozenset()


def test_sanity_prefix_maps_to_sanity() -> None:
    assert taxonomy_for_rule_id("sanity.national_id.length") == ValidationTaxonomy.SANITY
    assert taxonomy_for_rule_id("sanity.required.employee_name") == ValidationTaxonomy.SANITY
