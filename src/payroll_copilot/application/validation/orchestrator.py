"""Deterministic validation orchestrator — no AI dependency."""

from __future__ import annotations

from uuid import UUID, uuid4

from payroll_copilot.domain.enums import ConfidenceSource, FindingSeverity, ValidationResult
from payroll_copilot.domain.rules import ValidationContext, get_registered_rules
from payroll_copilot.domain.value_objects import ConfidenceScore, ValidationReport


class ValidationOrchestrator:
    """Evaluates all applicable rules against a validation context."""

    def run(self, context: ValidationContext) -> ValidationReport:
        rules = self._get_applicable_rules(context)
        findings = []

        for rule_cls in rules:
            rule = rule_cls()
            if not rule.applies_to(context):
                continue
            finding = rule.evaluate(context)
            if finding is not None:
                findings.append(finding)

        overall_result = self._compute_result(findings)
        overall_confidence = self._compute_confidence(findings, context)

        return ValidationReport(
            validation_run_id=uuid4(),
            overall_result=overall_result.value,
            overall_confidence=overall_confidence,
            findings=tuple(findings),
            rules_evaluated=len(rules),
            rules_failed=len(findings),
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
