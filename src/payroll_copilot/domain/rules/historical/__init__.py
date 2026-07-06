"""Historical comparison rules."""

from __future__ import annotations

from decimal import Decimal

from payroll_copilot.domain.enums import FindingSeverity, RuleCategory
from payroll_copilot.domain.rules import BaseRule, ValidationContext, register_rule


@register_rule
class SalaryDriftRule(BaseRule):
    rule_id = "historical.salary_drift"
    category = RuleCategory.HISTORICAL
    priority = 200

    DRIFT_THRESHOLD = Decimal("0.15")

    def applies_to(self, context: ValidationContext) -> bool:
        return len(context.historical_payslips) >= 1 and context.payslip.gross_salary is not None

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        current_gross = context.payslip.gross_salary
        if current_gross is None:
            return None

        previous = context.historical_payslips[-1].gross_salary
        if previous is None or previous.amount == 0:
            return None

        drift = abs(current_gross.amount - previous.amount) / previous.amount
        if drift > self.DRIFT_THRESHOLD:
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.WARNING,
                message_key="validation.historical.salary_drift",
                expected=f"≤ {self.DRIFT_THRESHOLD * 100}% change",
                actual=f"{drift * 100:.1f}% change",
                confidence=context.field_confidence("gross_salary"),
            )
        return None
