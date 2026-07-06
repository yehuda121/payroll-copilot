"""Department-specific rule implementations."""

from __future__ import annotations

from decimal import Decimal

from payroll_copilot.domain.enums import FindingSeverity, RuleCategory
from payroll_copilot.domain.rules import BaseRule, ValidationContext, register_rule


@register_rule
class InternWeeklyHoursRule(BaseRule):
    """Interns and pre-interns have reduced weekly hour limits."""

    rule_id = "department.intern.weekly_hours_limit"
    category = RuleCategory.DEPARTMENT
    priority = 90

    def applies_to(self, context: ValidationContext) -> bool:
        return context.department.rule_profile in ("interns", "pre_interns")

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        profile_limits = {
            "interns": Decimal("30"),
            "pre_interns": Decimal("20"),
        }
        max_hours = profile_limits.get(context.department.rule_profile, Decimal("30"))
        work_hours = context.payslip.work_hours

        if work_hours is None:
            return self._missing_data(self.rule_id, self.category, "work_hours")

        if work_hours > max_hours:
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.WARNING,
                message_key="validation.department.intern_hours_exceeded",
                expected=max_hours,
                actual=work_hours,
                confidence=context.field_confidence("work_hours"),
                message_params={
                    "department": context.department.code,
                    "expected": str(max_hours),
                    "actual": str(work_hours),
                },
            )
        return None


@register_rule
class LawyerOvertimeCapRule(BaseRule):
    """Lawyers department may have different overtime arrangements."""

    rule_id = "department.lawyers.overtime_cap"
    category = RuleCategory.DEPARTMENT
    priority = 95

    def applies_to(self, context: ValidationContext) -> bool:
        return context.department.rule_profile == "lawyers"

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        max_overtime = Decimal("40")
        overtime_hours = context.payslip.overtime_hours

        if overtime_hours is None:
            return None

        if overtime_hours > max_overtime:
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.WARNING,
                message_key="validation.department.lawyers_overtime_cap",
                expected=max_overtime,
                actual=overtime_hours,
                confidence=context.field_confidence("overtime_hours"),
            )
        return None
