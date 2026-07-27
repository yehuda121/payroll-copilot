"""Legal rule implementations loaded from YAML configuration."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from payroll_copilot.application.services.legal_parameter_resolver import resolve_parameters_as_of
from payroll_copilot.domain.employment_terms import parse_money
from payroll_copilot.domain.enums import EmploymentType, FindingSeverity, RuleCategory, SalaryType
from payroll_copilot.domain.rules import BaseRule, ValidationContext, register_rule
from payroll_copilot.domain.value_objects import RuleFinding


def _payslip_additional(context: ValidationContext, key: str):
    raw = (context.payslip.additional_fields or {}).get(key)
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict) and "value" in raw:
        value = raw.get("value")
        return None if value is None or value == "" else value
    return raw


def _as_of(context: ValidationContext) -> date:
    if context.period is None:
        # Orchestrator should NOT_RUN legal rules when period is missing; defensive guard.
        raise ValueError("pay_period_required_for_legal_as_of")
    return date(context.period.year, context.period.month, 1)


@register_rule
class DailyOvertimeLimitRule(BaseRule):
    """Limited check: uses payslip overtime_hours total vs YAML daily cap.

    Does not reconstruct attendance days — deferred full overtime engine.
    """

    rule_id = "legal.overtime.daily_limit"
    category = RuleCategory.OVERTIME
    priority = 100
    input_fields = ("overtime_hours",)
    reference_dependencies = ("legal_rules.daily_overtime_limit",)

    def applies_to(self, context: ValidationContext) -> bool:
        return context.employee.employment_type in (
            EmploymentType.FULL_TIME,
            EmploymentType.PART_TIME,
        )

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        rule_config = context.legal_rules.rules.get("daily_overtime_limit")
        if rule_config is None:
            return None

        params = resolve_parameters_as_of(rule_config, as_of=_as_of(context))
        max_hours = Decimal(str(params.get("max_hours", 2)))
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
    """Hourly statutory minimum for the payslip period.

    Compares payslip hourly_rate (preferred) against YAML schedule amount.
    Applies only when the payslip/context indicates hourly pay basis.
    Does not compare monthly minimum or partial-month prorations.
    """

    rule_id = "legal.minimum_wage"
    category = RuleCategory.LEGAL
    priority = 50
    input_fields = ("hourly_rate",)
    reference_dependencies = ("legal_rules.minimum_wage_hourly",)

    def applies_to(self, context: ValidationContext) -> bool:
        payslip_basis = _payslip_additional(context, "salary_calculation_basis") or _payslip_additional(
            context, "salary_basis"
        )
        if payslip_basis is not None:
            text = str(payslip_basis).strip().lower()
            if "hour" in text or text in {"hourly", "שעתי"}:
                return True
            if "month" in text or text in {"monthly", "חודשי"}:
                return False
        terms = context.confirmed_employment_terms
        if terms is not None and terms.salary_basis == "hourly":
            return True
        if terms is not None and terms.salary_basis == "monthly":
            return False
        return context.employee.salary_type == SalaryType.HOURLY

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        rule_config = context.legal_rules.rules.get("minimum_wage_hourly")
        if rule_config is None:
            return None

        params = resolve_parameters_as_of(rule_config, as_of=_as_of(context))
        min_wage = Decimal(str(params.get("amount", 32.11)))

        # Prefer explicit payslip field — not HR profile alone.
        hourly_rate = parse_money(_payslip_additional(context, "hourly_rate"))
        if hourly_rate is None:
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
    """DEFERRED Phase-1: contribution base and eligibility are ambiguous.

    Israeli pension uses insured wage components and tenure eligibility
    (applies_from_month). Approximating pension/gross is unsafe.
    Rule remains registered but does not apply until a safe base exists.
    """

    rule_id = "legal.pension.contribution"
    category = RuleCategory.PENSION
    priority = 110
    input_fields = ("pension_employee", "gross_salary")
    reference_dependencies = ("legal_rules.pension_employee_minimum",)

    def applies_to(self, context: ValidationContext) -> bool:
        # Explicitly deferred — do not approximate contribution base.
        return False

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        return None


@register_rule
class YouthEmploymentAgeRule(BaseRule):
    rule_id = "legal.youth.minimum_age"
    category = RuleCategory.LEGAL
    priority = 40
    input_fields = ("age",)
    reference_dependencies = ("legal_rules.youth_minimum_age",)

    def applies_to(self, context: ValidationContext) -> bool:
        return context.employee.employment_type in (
            EmploymentType.INTERN,
            EmploymentType.PRE_INTERN,
        )

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        rule_config = context.legal_rules.rules.get("youth_minimum_age")
        if rule_config is None:
            return None

        params = resolve_parameters_as_of(rule_config, as_of=_as_of(context))
        min_age = int(params.get("min_age", 15))
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
