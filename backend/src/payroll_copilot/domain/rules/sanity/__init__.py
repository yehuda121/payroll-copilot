"""Deterministic document-only SANITY rules for payslips.

No employee profile, contract, or law comparisons. No AI.
"""

from __future__ import annotations

from decimal import Decimal

from payroll_copilot.application.services.payslip_field_registry import (
    required_on_payslip_keys,
)
from payroll_copilot.domain.enums import FindingSeverity, RuleCategory
from payroll_copilot.domain.rules import BaseRule, ValidationContext, register_rule
from payroll_copilot.domain.rules.sanity import helpers as h
from payroll_copilot.domain.value_objects import RuleFinding

_NET_GROSS_TOLERANCE = Decimal("0.000001")


@register_rule
class NationalIdLengthRule(BaseRule):
    """National ID must normalize to exactly 9 digits."""

    rule_id = "sanity.national_id.length"
    category = RuleCategory.SANITY
    priority = 20

    def applies_to(self, context: ValidationContext) -> bool:
        raw, _ = h.resolve_national_id_raw(context.payslip)
        return raw is not None

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        raw, _ = h.resolve_national_id_raw(context.payslip)
        digits = h.national_id_digits(raw)
        if digits is None:
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.WARNING,
                message_key="validation.sanity.national_id.not_digits",
                expected="9 digits",
                actual=raw,
                confidence=context.field_confidence("national_id"),
            )
        if not h.national_id_length_ok(digits):
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.WARNING,
                message_key="validation.sanity.national_id.length",
                expected="9 digits",
                actual=f"{len(digits)} digits",
                confidence=context.field_confidence("national_id"),
            )
        return None


@register_rule
class NationalIdChecksumRule(BaseRule):
    """Israeli National ID checksum (same algorithm as ID-card entry)."""

    rule_id = "sanity.national_id.checksum"
    category = RuleCategory.SANITY
    priority = 21

    def applies_to(self, context: ValidationContext) -> bool:
        raw, _ = h.resolve_national_id_raw(context.payslip)
        digits = h.national_id_digits(raw)
        return digits is not None and h.national_id_length_ok(digits)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        raw, _ = h.resolve_national_id_raw(context.payslip)
        digits = h.national_id_digits(raw) or ""
        if h.national_id_checksum_ok(digits):
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.sanity.national_id.checksum",
            expected="valid checksum",
            actual=digits,
            confidence=context.field_confidence("national_id"),
        )


@register_rule
class EmployeeNameStructureRule(BaseRule):
    """Reject numeric-only / letter-less employee names (Unicode letters OK)."""

    rule_id = "sanity.employee_name.structure"
    category = RuleCategory.SANITY
    priority = 22

    def applies_to(self, context: ValidationContext) -> bool:
        name = (context.payslip.employee_name or "").strip()
        return bool(name)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        name = context.payslip.employee_name
        reason = h.name_structure_fail_reason(name)
        if reason is None:
            return None
        message_key = {
            "implausible_employee_name_numeric_only": "validation.sanity.employee_name.numeric",
            "implausible_employee_name_no_letters": "validation.sanity.employee_name.no_letters",
            "implausible_employee_name_too_short": "validation.sanity.employee_name.too_short",
        }.get(reason, "validation.sanity.employee_name.structure")
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key=message_key,
            expected="person name",
            actual=name,
            confidence=context.field_confidence("employee_name"),
        )


@register_rule
class PayPeriodParseableRule(BaseRule):
    """Fail only for numeric-shaped periods that are invalid or unparseable.

    Free-form labels (e.g. Hebrew month names) are left alone — same policy as
    extraction plausibility — and are not forced into a FAIL here.
    """

    rule_id = "sanity.pay_period.parseable"
    category = RuleCategory.SANITY
    priority = 23

    def applies_to(self, context: ValidationContext) -> bool:
        if context.payslip.period is not None:
            return False
        raw = h.pay_period_raw(context.payslip)
        if raw is None:
            return False
        if h.pay_period_raw_fail_reason(raw) is not None:
            return True
        return h.pay_period_looks_numeric(raw)

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        raw = h.pay_period_raw(context.payslip)
        reason = h.pay_period_raw_fail_reason(raw)
        if reason == "implausible_pay_period_month":
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.WARNING,
                message_key="validation.sanity.pay_period.month",
                expected="month 1-12",
                actual=raw,
                confidence=context.field_confidence("pay_period"),
            )
        if reason == "implausible_pay_period_year":
            return self._violation(
                rule_id=self.rule_id,
                category=self.category,
                severity=FindingSeverity.WARNING,
                message_key="validation.sanity.pay_period.year",
                expected="valid year",
                actual=raw,
                confidence=context.field_confidence("pay_period"),
            )
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.sanity.pay_period.unparseable",
            expected="YYYY-MM or MM-YYYY",
            actual=raw,
            confidence=context.field_confidence("pay_period"),
        )


@register_rule
class PayPeriodCalendarRule(BaseRule):
    """Valid month 1–12 and year window already used by extraction plausibility."""

    rule_id = "sanity.pay_period.calendar"
    category = RuleCategory.SANITY
    priority = 24

    def applies_to(self, context: ValidationContext) -> bool:
        return context.payslip.period is not None

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        reason = h.pay_period_calendar_fail_reason(context.payslip.period)
        if reason is None:
            # Also reject numeric-shaped raw that is calendar-invalid if preserved.
            raw = h.pay_period_raw(context.payslip)
            if raw is not None:
                reason = h.pay_period_raw_fail_reason(raw)
        if reason is None:
            return None
        message_key = (
            "validation.sanity.pay_period.month"
            if reason == "implausible_pay_period_month"
            else "validation.sanity.pay_period.year"
        )
        period = context.payslip.period
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key=message_key,
            expected="valid calendar period",
            actual=period.label if period is not None else None,
            confidence=context.field_confidence("pay_period"),
        )


@register_rule
class EmploymentStartDateCalendarRule(BaseRule):
    """employment_start_date must be a real calendar date when present."""

    rule_id = "sanity.employment_start_date.calendar"
    category = RuleCategory.SANITY
    priority = 25

    def applies_to(self, context: ValidationContext) -> bool:
        return h.additional_value(context.payslip, "employment_start_date") is not None

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        raw = h.additional_value(context.payslip, "employment_start_date")
        reason = h.employment_start_date_fail_reason(raw)
        if reason is None:
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.sanity.employment_start_date.invalid",
            expected="YYYY-MM-DD",
            actual=raw,
            confidence=context.field_confidence("employment_start_date"),
        )


@register_rule
class NetNotExceedGrossRule(BaseRule):
    """Document-internal coherence: net cannot exceed gross when both present.

    Same relationship already flagged at extraction time (net_exceeds_gross).
    """

    rule_id = "sanity.net_salary.not_exceed_gross"
    category = RuleCategory.SANITY
    priority = 26

    def applies_to(self, context: ValidationContext) -> bool:
        return (
            context.payslip.gross_salary is not None
            and context.payslip.net_salary is not None
        )

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        gross = context.payslip.gross_salary
        net = context.payslip.net_salary
        assert gross is not None and net is not None
        if net.amount <= gross.amount + _NET_GROSS_TOLERANCE:
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.sanity.net_exceeds_gross",
            expected=f"<= {gross.amount}",
            actual=net.amount,
            confidence=min(
                context.field_confidence("net_salary"),
                context.field_confidence("gross_salary"),
                key=lambda c: c.value,
            ),
        )


@register_rule
class EmploymentTypeRecognizedRule(BaseRule):
    """Present employment_type must match the existing EmploymentType catalog.

    Does not invent FULL_TIME. Does not compare to profile/contract.
    Does not treat hourly/monthly/daily salary modes as EmploymentType.
    """

    rule_id = "sanity.employment_type.recognized"
    category = RuleCategory.SANITY
    priority = 27

    def applies_to(self, context: ValidationContext) -> bool:
        return h.employment_type_raw(context.payslip) is not None

    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        raw = h.employment_type_raw(context.payslip)
        if h.employment_type_recognized(raw):
            return None
        return self._violation(
            rule_id=self.rule_id,
            category=self.category,
            severity=FindingSeverity.WARNING,
            message_key="validation.sanity.employment_type.unrecognized",
            expected="recognized employment type",
            actual=raw,
            confidence=context.field_confidence("employment_type"),
        )


def _register_required_presence_rules() -> None:
    """One independent rule per required_on_payslip key (future per-check friendly)."""

    for field_key in sorted(required_on_payslip_keys()):

        class RequiredFieldPresenceRule(BaseRule):
            rule_id = f"sanity.required.{field_key}"
            category = RuleCategory.SANITY
            priority = 15
            _field_key = field_key

            def applies_to(self, context: ValidationContext) -> bool:
                return True

            def evaluate(self, context: ValidationContext) -> RuleFinding | None:
                if h.required_field_present(context.payslip, self._field_key):
                    return None
                return RuleFinding(
                    rule_id=self.rule_id,
                    category=self.category,
                    severity=FindingSeverity.INFO,
                    message_key="validation.sanity.required_field_missing",
                    message_params={"field": self._field_key},
                    expected_value=self._field_key,
                    actual_value=None,
                    confidence=context.field_confidence(self._field_key),
                )

        RequiredFieldPresenceRule.__name__ = f"RequiredPresence_{field_key}"
        RequiredFieldPresenceRule.__qualname__ = f"RequiredPresence_{field_key}"
        register_rule(RequiredFieldPresenceRule)


_register_required_presence_rules()
