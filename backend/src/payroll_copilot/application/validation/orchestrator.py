"""Deterministic validation orchestrator — no AI dependency."""

from __future__ import annotations

from uuid import uuid4

from payroll_copilot.domain.enums import ConfidenceSource, FindingSeverity, RuleCategory, ValidationResult
from payroll_copilot.domain.rules import ValidationContext, get_registered_rules
from payroll_copilot.domain.value_objects import (
    ConfidenceScore,
    RuleEvaluationOutcome,
    ValidationReport,
)


def _skip_reason_for(rule_cls: type, context: ValidationContext) -> str | None:
    """Return a stable, accountant-safe skip reason when context makes it obvious.

    Prefer None over speculative rule-specific explanations.
    """
    category = getattr(rule_cls, "category", None)
    if category == RuleCategory.EMPLOYEE and not context.authorized_employee:
        return "employee_not_identified"
    if category == RuleCategory.CONTRACT:
        if not context.authorized_employee:
            return "employee_not_identified"
        terms = context.confirmed_employment_terms
        if terms is None or not getattr(terms, "has_any_terms", False):
            return "no_confirmed_contract"
    return None


class ValidationOrchestrator:
    """Evaluates all applicable rules against a validation context."""

    def run(self, context: ValidationContext) -> ValidationReport:
        rules = self._get_applicable_rules(context)
        findings = []
        outcomes: list[RuleEvaluationOutcome] = []

        for rule_cls in rules:
            rule = rule_cls()
            rule_id = str(getattr(rule, "rule_id", "") or "")
            if not rule.applies_to(context):
                outcomes.append(
                    RuleEvaluationOutcome(
                        rule_id=rule_id,
                        outcome="skipped",
                        skip_reason=_skip_reason_for(rule_cls, context),
                    )
                )
                continue
            finding = rule.evaluate(context)
            if finding is not None:
                findings.append(finding)
                outcomes.append(
                    RuleEvaluationOutcome(rule_id=rule_id or finding.rule_id, outcome="failed")
                )
            else:
                outcomes.append(RuleEvaluationOutcome(rule_id=rule_id, outcome="passed"))

        overall_result = self._compute_result(findings)
        overall_confidence = self._compute_confidence(findings, context)

        # Count only rules that actually ran (passed or produced a finding).
        evaluated_count = sum(1 for item in outcomes if item.outcome in {"passed", "failed"})

        return ValidationReport(
            validation_run_id=uuid4(),
            overall_result=overall_result.value,
            overall_confidence=overall_confidence,
            findings=tuple(findings),
            rules_evaluated=evaluated_count,
            # INFO findings (e.g. missing-data / required-on-payslip) are informational —
            # they must not inflate failed-rule counts. Aligns with overall_result, which
            # already ignores INFO when computing PASS/WARNINGS/CRITICAL.
            rules_failed=sum(
                1
                for finding in findings
                if finding.severity
                in (FindingSeverity.WARNING, FindingSeverity.CRITICAL)
            ),
            rule_outcomes=tuple(outcomes),
        )

    def _get_applicable_rules(self, context: ValidationContext) -> list[type]:
        registered = get_registered_rules()
        applicable = [
            cls
            for rule_id, cls in registered.items()
            if rule_id not in context.disabled_rule_ids
        ]
        return sorted(applicable, key=lambda c: c.priority)  # type: ignore[attr-defined]

    @staticmethod
    def _compute_result(findings: list) -> ValidationResult:
        if any(f.severity == FindingSeverity.CRITICAL for f in findings):
            return ValidationResult.CRITICAL
        if any(f.severity == FindingSeverity.WARNING for f in findings):
            return ValidationResult.WARNINGS
        return ValidationResult.PASS

    @staticmethod
    def _compute_confidence(findings: list, context: ValidationContext) -> ConfidenceScore:
        if not findings:
            if context.field_confidences:
                min_conf = min(context.field_confidences.values())
                return ConfidenceScore(value=min_conf, source=ConfidenceSource.OCR)
            return ConfidenceScore.certain(ConfidenceSource.RULE)

        min_conf = min(f.confidence.value for f in findings)
        source = min(findings, key=lambda f: f.confidence.value).confidence.source
        return ConfidenceScore(value=min_conf, source=source)
