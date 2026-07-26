"""EMPLOYEE rules: compare confirmed payslip fields to authorized employee profile.

Guest / unresolved Batch: authorized_employee=False → rules do not apply.
Does not use contract or law. Does not invent reference data.
"""

from __future__ import annotations

from payroll_copilot.domain.enums import FindingSeverity, RuleCategory
from payroll_copilot.domain.rules import BaseRule, ValidationContext, register_rule
from payroll_copilot.domain.rules.employee import helpers as h
from payroll_copilot.domain.value_objects import RuleFinding


def _insufficient(rule_id: str, field_name: str) -> RuleFinding:
    return BaseRule._missing_data(rule_id, RuleCategory.EMPLOYEE, field_name)


@register_rule
class EmployeeNationalIdMatchRule(BaseRule):
    rule_id = "employee.national_id.match"
    category = RuleCategory.EMPLOYEE
    priority = 30

    def applies_to(self, context: ValidationContext) -> bool:
        return h.has_authorized_employee(context)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        outcome = h.national_id_outcome(
            payslip=context.payslip,
            trusted_national_id=context.trusted_national_id,
        )
        if outcome == "missing_payslip":
            return None
        if outcome == "missing_reference":
            return _insufficient(self.rule_id, "national_id")
        if outcome == "match":
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.CRITICAL,
            message_key="validation.employee.national_id.mismatch",
            expected="employee national id",
            actual="payslip national id",
            confidence=context.field_confidence("national_id"),
        )


@register_rule
class EmployeeNameMatchRule(BaseRule):
    rule_id = "employee.name.match"
    category = RuleCategory.EMPLOYEE
    priority = 31

    def applies_to(self, context: ValidationContext) -> bool:
        return h.has_authorized_employee(context)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        outcome = h.employee_name_outcome(
            payslip=context.payslip,
            employee=context.employee,
        )
        if outcome == "missing_payslip":
            return None
        if outcome in {"missing_reference", "cannot_compare"}:
            return _insufficient(self.rule_id, "employee_name")
        if outcome == "match":
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.employee.name.mismatch",
            expected=h.trusted_employee_display_name(context.employee),
            actual=context.payslip.employee_name,
            confidence=context.field_confidence("employee_name"),
        )


@register_rule
class EmployeeNumberMatchRule(BaseRule):
    rule_id = "employee.employee_number.match"
    category = RuleCategory.EMPLOYEE
    priority = 32

    def applies_to(self, context: ValidationContext) -> bool:
        return h.has_authorized_employee(context)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        outcome = h.employee_number_outcome(
            payslip=context.payslip,
            employee=context.employee,
        )
        if outcome == "missing_payslip":
            return None
        if outcome == "missing_reference":
            return _insufficient(self.rule_id, "employee_number")
        if outcome == "match":
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.employee.employee_number.mismatch",
            expected=context.employee.employee_number,
            actual=context.payslip.employee_number,
            confidence=context.field_confidence("employee_number"),
        )


@register_rule
class EmployeeEmploymentTypeMatchRule(BaseRule):
    """Compare only when payslip token maps to the same EmploymentType catalog."""

    rule_id = "employee.employment_type.match"
    category = RuleCategory.EMPLOYEE
    priority = 34

    def applies_to(self, context: ValidationContext) -> bool:
        return h.has_authorized_employee(context)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        outcome = h.employment_type_outcome(
            payslip=context.payslip,
            employee=context.employee,
        )
        if outcome == "missing_payslip":
            return None
        if outcome == "missing_reference":
            return _insufficient(self.rule_id, "employment_type")
        if outcome == "match":
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.employee.employment_type.mismatch",
            expected=context.employee.employment_type.value,
            actual=h.additional_value(context.payslip, "employment_type"),
            confidence=context.field_confidence("employment_type"),
        )


@register_rule
class EmployeePayPeriodMatchRule(BaseRule):
    """Transparency finding: payslip period vs selected workspace/document month.

    Does not replace Move / Keep / Cancel. Does not move documents.
    """

    rule_id = "employee.pay_period.match"
    category = RuleCategory.EMPLOYEE
    priority = 35

    def applies_to(self, context: ValidationContext) -> bool:
        return h.has_authorized_employee(context)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        outcome = h.pay_period_vs_selected_outcome(context)
        if outcome == "missing_payslip":
            return None
        if outcome == "missing_reference":
            return _insufficient(self.rule_id, "pay_period")
        if outcome == "match":
            return None
        selected = None
        if context.selected_period_year and context.selected_period_month:
            selected = f"{context.selected_period_year}-{context.selected_period_month:02d}"
        actual = context.payslip.period.label if context.payslip.period else None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.employee.pay_period.mismatch",
            expected=selected,
            actual=actual,
            confidence=context.field_confidence("pay_period"),
        )
