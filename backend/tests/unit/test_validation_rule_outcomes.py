"""Orchestrator rule_outcomes are authoritative for PASS / NOT_RUN / UNCERTAIN."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import payroll_copilot.domain.rules.contract  # noqa: F401
import payroll_copilot.domain.rules.departments  # noqa: F401
import payroll_copilot.domain.rules.employee  # noqa: F401
import payroll_copilot.domain.rules.historical  # noqa: F401
import payroll_copilot.domain.rules.legal  # noqa: F401
import payroll_copilot.domain.rules.sanity  # noqa: F401
from payroll_copilot.application.services.validation_catalog import (
    LABOR_LAW_CATALOG,
    OUTCOME_FAILED,
    OUTCOME_NOT_RUN,
    OUTCOME_PASSED,
    OUTCOME_UNCERTAIN,
    REASON_EXECUTION_ERROR,
    REASON_NOT_APPLICABLE,
    REASON_RULE_NOT_READY,
    labor_law_rule_ids,
)
from payroll_copilot.application.validation.orchestrator import ValidationOrchestrator
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmploymentType, EmployeeStatus, RuleCategory, SalaryType
from payroll_copilot.domain.rules import LegalRulesBundle, ValidationContext, get_registered_rules
from payroll_copilot.domain.value_objects import Money, PayPeriod

_VALID_NATIONAL_ID = "313366783"


def _base_context(**overrides) -> ValidationContext:
    emp = Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="1",
        first_name="A",
        last_name="B",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 1, 1),
        status=EmployeeStatus.ACTIVE,
    )
    kwargs = dict(
        payslip=PayslipData(
            gross_salary=Money(Decimal("10000")),
            pension_employee=Money(Decimal("100")),
        ),
        employee=emp,
        department=Department(
            id=emp.department_id,
            organization_id=emp.organization_id,
            code="x",
            name={"en": "x"},
            rule_profile="payroll",
        ),
        period=PayPeriod(year=2026, month=6),
        legal_rules=LegalRulesBundle(version="1", effective_from="2026-01-01", rules={}),
        authorized_employee=False,
    )
    kwargs.update(overrides)
    return ValidationContext(**kwargs)


def test_catalog_contains_all_17_labor_law_rules():
    ids = labor_law_rule_ids()
    assert len(ids) == 17
    assert len(LABOR_LAW_CATALOG) == 17
    assert len(set(ids)) == 17


def test_orchestrator_emits_explicit_outcomes_including_catalog_law_rules():
    report = ValidationOrchestrator().run(_base_context())
    assert report.rule_outcomes
    outcomes = {item.rule_id: item for item in report.rule_outcomes}
    registered = get_registered_rules()
    for rule_id in registered:
        assert rule_id in outcomes
    for law_id in labor_law_rule_ids():
        assert law_id in outcomes
        assert outcomes[law_id].outcome in {
            OUTCOME_PASSED,
            OUTCOME_FAILED,
            OUTCOME_UNCERTAIN,
            OUTCOME_NOT_RUN,
        }

    employee_rules = [
        rid
        for rid, cls in registered.items()
        if getattr(cls, "category", None) == RuleCategory.EMPLOYEE
    ]
    assert employee_rules
    sample = employee_rules[0]
    assert outcomes[sample].outcome == OUTCOME_NOT_RUN
    assert outcomes[sample].reason_code in {
        "EMPLOYEE_NOT_IDENTIFIED",
        REASON_NOT_APPLICABLE,
    }
    assert report.rules_evaluated == sum(
        1
        for item in report.rule_outcomes
        if item.outcome in {OUTCOME_PASSED, OUTCOME_FAILED, OUTCOME_UNCERTAIN}
    )


def test_not_ready_law_rules_are_not_run():
    report = ValidationOrchestrator().run(_base_context())
    outcomes = {item.rule_id: item for item in report.rule_outcomes}
    assert outcomes["legal.overtime.weekly_limit"].outcome == OUTCOME_NOT_RUN
    assert outcomes["legal.overtime.weekly_limit"].reason_code == REASON_RULE_NOT_READY
    assert outcomes["legal.pension.contribution"].outcome == OUTCOME_NOT_RUN
    assert outcomes["legal.pension.contribution"].reason_code == REASON_RULE_NOT_READY


def test_youth_rule_not_applicable_for_adult_full_time():
    report = ValidationOrchestrator().run(_base_context())
    outcomes = {item.rule_id: item for item in report.rule_outcomes}
    youth = outcomes["legal.youth.minimum_age"]
    assert youth.outcome == OUTCOME_NOT_RUN
    assert youth.reason_code in {REASON_NOT_APPLICABLE, REASON_RULE_NOT_READY}


def test_execution_exception_is_not_run_not_failed(monkeypatch):
    from payroll_copilot.domain import rules as rules_mod
    from payroll_copilot.domain.rules import BaseRule

    class BoomRule(BaseRule):
        rule_id = "test.boom.isolation"
        category = RuleCategory.SANITY
        priority = 1

        def applies_to(self, context: ValidationContext) -> bool:
            return True

        def evaluate(self, context: ValidationContext):
            raise RuntimeError("boom")

    monkeypatch.setitem(rules_mod._RULE_REGISTRY, BoomRule.rule_id, BoomRule)

    report = ValidationOrchestrator().run(_base_context())
    outcomes = {item.rule_id: item for item in report.rule_outcomes}
    boom = outcomes[BoomRule.rule_id]
    assert boom.outcome == OUTCOME_NOT_RUN
    assert boom.reason_code == REASON_EXECUTION_ERROR
    # Independent rules still present
    assert "legal.minimum_wage" in outcomes
    assert boom.outcome != OUTCOME_FAILED


def test_missing_payslip_data_is_uncertain_not_failed():
    emp = Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="1",
        first_name="A",
        last_name="B",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 1, 1),
        status=EmployeeStatus.ACTIVE,
    )
    ctx = _base_context(
        payslip=PayslipData(),  # missing national_id
        employee=emp,
        authorized_employee=True,
        trusted_national_id=_VALID_NATIONAL_ID,
    )
    report = ValidationOrchestrator().run(ctx)
    outcomes = {item.rule_id: item for item in report.rule_outcomes}
    nid = outcomes["employee.national_id.match"]
    assert nid.outcome == OUTCOME_UNCERTAIN
    assert nid.outcome != OUTCOME_FAILED
    assert nid.outcome != OUTCOME_PASSED


def test_passed_only_from_actual_passed_outcome():
    report = ValidationOrchestrator().run(_base_context())
    for item in report.rule_outcomes:
        if item.outcome == OUTCOME_PASSED:
            assert item.reason_code is None or item.reason_code == ""
        if item.outcome == OUTCOME_FAILED:
            assert item.rule_id  # real failure path only via findings
