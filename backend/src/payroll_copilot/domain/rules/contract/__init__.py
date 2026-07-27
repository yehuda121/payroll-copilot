"""CONTRACT rules: payslip ↔ confirmed employment terms.

Uses ConfirmedEmploymentTerms only. Never Employee.contract_start_date,
system create/onboarding dates, or unconfirmed OCR.
"""

from __future__ import annotations

from typing import Any

from payroll_copilot.domain.employment_terms import parse_iso_date, parse_money, parse_salary_basis
from payroll_copilot.domain.enums import FindingSeverity, RuleCategory
from payroll_copilot.domain.rules import BaseRule, ValidationContext, register_rule
from payroll_copilot.domain.value_objects import RuleFinding


def _additional(payslip_fields: dict[str, Any] | None, key: str) -> Any | None:
    raw = (payslip_fields or {}).get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict) and "value" in raw:
        value = raw.get("value")
        return None if value is None or value == "" else value
    return raw


def _has_confirmed_terms(context: ValidationContext) -> bool:
    terms = context.confirmed_employment_terms
    return bool(context.authorized_employee and terms and terms.has_any_terms)


def _insufficient(rule_id: str, field_name: str) -> RuleFinding:
    return BaseRule._missing_data(rule_id, RuleCategory.CONTRACT, field_name)


@register_rule
class ContractEmploymentCommencementMatchRule(BaseRule):
    rule_id = "contract.employment_commencement_date.match"
    category = RuleCategory.CONTRACT
    priority = 40
    input_fields = ("employment_start_date",)
    reference_dependencies = ("confirmed_employment_terms.employment_commencement_date",)

    def applies_to(self, context: ValidationContext) -> bool:
        return _has_confirmed_terms(context)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        terms = context.confirmed_employment_terms
        assert terms is not None
        payslip_raw = _additional(context.payslip.additional_fields, "employment_start_date")
        payslip_date = parse_iso_date(payslip_raw)
        ref = terms.employment_commencement_date
        if payslip_date is None:
            return _insufficient(self.rule_id, "employment_start_date")
        if ref is None:
            return _insufficient(self.rule_id, "employment_commencement_date")
        if payslip_date == ref:
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.contract.employment_commencement_date.mismatch",
            expected=ref.isoformat(),
            actual=payslip_date.isoformat(),
            confidence=context.field_confidence("employment_start_date"),
        )


@register_rule
class ContractSalaryBasisMatchRule(BaseRule):
    rule_id = "contract.salary_basis.match"
    category = RuleCategory.CONTRACT
    priority = 41
    input_fields = ("salary_calculation_basis",)
    reference_dependencies = ("confirmed_employment_terms.salary_basis",)

    def applies_to(self, context: ValidationContext) -> bool:
        return _has_confirmed_terms(context)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        terms = context.confirmed_employment_terms
        assert terms is not None
        # Prefer explicit payslip salary_calculation_basis; never map to EmploymentType.
        payslip_raw = _additional(context.payslip.additional_fields, "salary_calculation_basis")
        if payslip_raw is None:
            payslip_raw = _additional(context.payslip.additional_fields, "salary_basis")
        payslip_basis = parse_salary_basis(payslip_raw)
        ref = terms.salary_basis
        if payslip_basis is None:
            return _insufficient(self.rule_id, "salary_basis")
        if ref is None:
            return _insufficient(self.rule_id, "salary_basis")
        if payslip_basis == ref:
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.contract.salary_basis.mismatch",
            expected=ref,
            actual=payslip_basis,
            confidence=context.field_confidence("salary_calculation_basis"),
        )


@register_rule
class ContractHourlyRateMatchRule(BaseRule):
    """Compare payslip hourly rate to confirmed contractual hourly rate.

    Applies only when confirmed salary_basis is hourly (or hourly rate is the
    only contractual rate present with no conflicting monthly/daily amount).
    """

    rule_id = "contract.hourly_rate.match"
    category = RuleCategory.CONTRACT
    priority = 42
    input_fields = ("hourly_rate",)
    reference_dependencies = ("confirmed_employment_terms.contractual_hourly_rate",)

    def applies_to(self, context: ValidationContext) -> bool:
        if not _has_confirmed_terms(context):
            return False
        terms = context.confirmed_employment_terms
        assert terms is not None
        if terms.contractual_hourly_rate is None:
            return False
        if terms.salary_basis is not None and terms.salary_basis != "hourly":
            return False
        return True

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        terms = context.confirmed_employment_terms
        assert terms is not None
        payslip_raw = _additional(context.payslip.additional_fields, "hourly_rate")
        payslip_rate = parse_money(payslip_raw)
        ref = terms.contractual_hourly_rate
        if payslip_rate is None:
            return _insufficient(self.rule_id, "hourly_rate")
        if ref is None:
            return _insufficient(self.rule_id, "contractual_hourly_rate")
        if payslip_rate == ref:
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.contract.hourly_rate.mismatch",
            expected=str(ref),
            actual=str(payslip_rate),
            confidence=context.field_confidence("hourly_rate"),
        )


# Monthly contractual salary vs payslip base_salary is deferred: partial months /
# absences make exact equality unsafe without period-adjustment conventions.

