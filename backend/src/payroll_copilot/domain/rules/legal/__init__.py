"""Legal rule implementations loaded from YAML configuration."""

from __future__ import annotations

from decimal import Decimal

from payroll_copilot.domain.enums import EmploymentType, FindingSeverity, RuleCategory
from payroll_copilot.domain.rules import BaseRule, ValidationContext, register_rule
from payroll_copilot.domain.value_objects import RuleFinding


@register_rule
class DailyOvertimeLimitRule(BaseRule):
    rule_id = "legal.overtime.daily_limit"
    category = RuleCategory.OVERTIME
    priority = 100

    def applies_to(self, context: ValidationContext) -> bool:
        return context.employee.employment_type in (
            EmploymentType.FULL_TIME,
            EmploymentType.PART_TIME,
        )

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        rule_config = context.legal_rules.rules.get("daily_overtime_limit")
        if rule_config is None:
            return None

        max_hours = Decimal(str(rule_config.parameters.get("max_hours", 2)))
        overtime_hours = context.payslip.overtime_hours
        if overtime_hours is None:
            return self._missing_data(self.rule_id, self.category, "overtime_hours")

        if overtime_hours > max_hours:
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=rule_config.severity,
                message_key="validation.overtime.daily_limit_exceeded",
                expected=max_hours,
                actual=overtime_hours,
                confidence=context.field_confidence("overtime_hours"),
                legal_reference=rule_config.legal_reference.get("he"),
            )
        return None


@register_rule
class MinimumWageRule(BaseRule):
    rule_id = "legal.minimum_wage"
    category = RuleCategory.LEGAL
    priority = 50

    def applies_to(self, context: ValidationContext) -> bool:
        return context.employee.salary_type.value == "hourly"

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        rule_config = context.legal_rules.rules.get("minimum_wage_hourly")
        if rule_config is None:
            return None

        min_wage = Decimal(str(rule_config.parameters.get("amount", 32.11)))
        hourly_rate = context.employee.hourly_rate
        if hourly_rate is None:
            return self._missing_data(self.rule_id, self.category, "hourly_rate")

        if hourly_rate < min_wage:
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.CRITICAL,
                message_key="validation.minimum_wage.below_threshold",
                expected=min_wage,
                actual=hourly_rate,
                confidence=context.field_confidence("hourly_rate"),
                legal_reference=rule_config.legal_reference.get("he"),
            )
        return None


@register_rule
class PensionContributionRule(BaseRule):
    rule_id = "legal.pension.contribution"
    category = RuleCategory.PENSION
    priority = 110

    def applies_to(self, context: ValidationContext) -> bool:
        return context.payslip.gross_salary is not None

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        rule_config = context.legal_rules.rules.get("pension_employee_minimum")
        if rule_config is None:
            return None

        min_rate = Decimal(str(rule_config.parameters.get("minimum_rate", 0.06)))
        gross = context.payslip.gross_salary
        pension = context.payslip.pension_employee

        if gross is None or pension is None:
            return self._missing_data(self.rule_id, self.category, "pension_employee")

        actual_rate = pension.amount / gross.amount if gross.amount > 0 else Decimal("0")
        if actual_rate < min_rate:
            expected_amount = gross.amount * min_rate
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.CRITICAL,
                message_key="validation.pension.insufficient_contribution",
                expected=expected_amount,
                actual=pension.amount,
                confidence=context.field_confidence("pension_employee"),
                legal_reference=rule_config.legal_reference.get("he"),
            )
        return None


@register_rule
class YouthEmploymentAgeRule(BaseRule):
    rule_id = "legal.youth.minimum_age"
    category = RuleCategory.LEGAL
    priority = 40

    def applies_to(self, context: ValidationContext) -> bool:
        return context.employee.employment_type in (
            EmploymentType.INTERN,
            EmploymentType.PRE_INTERN,
        )

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        rule_config = context.legal_rules.rules.get("youth_minimum_age")
        if rule_config is None:
            return None

        min_age = int(rule_config.parameters.get("min_age", 15))
        employee_age = context.employee.metadata.get("age")
        if employee_age is None:
            return self._missing_data(self.rule_id, self.category, "age")

        if int(employee_age) < min_age:
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.CRITICAL,
                message_key="validation.youth.below_minimum_age",
                expected=min_age,
                actual=employee_age,
                confidence=context.field_confidence("age"),
                legal_reference=rule_config.legal_reference.get("he"),
            )
        return None
