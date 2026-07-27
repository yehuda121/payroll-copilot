"""Deterministic validation orchestrator — no AI dependency."""

from __future__ import annotations

import logging
from uuid import uuid4

from payroll_copilot.application.services.validation_catalog import (
    OUTCOME_FAILED,
    OUTCOME_NOT_RUN,
    OUTCOME_PASSED,
    OUTCOME_UNCERTAIN,
    READINESS_NOT_READY,
    REASON_EXECUTION_ERROR,
    REASON_MISSING_PAY_PERIOD,
    REASON_MISSING_PAYSLIP_DATA,
    REASON_NO_APPLICABLE_LEGAL_VERSION,
    REASON_NOT_APPLICABLE,
    REASON_RULE_NOT_READY,
    catalog_by_rule_id,
    labor_law_rule_ids,
    map_legacy_skip_to_reason,
    reason_message,
)
from payroll_copilot.domain.enums import ConfidenceSource, FindingSeverity, RuleCategory, ValidationResult
from payroll_copilot.domain.rules import ValidationContext, get_registered_rules
from payroll_copilot.domain.value_objects import (
    ConfidenceScore,
    RuleEvaluationOutcome,
    ValidationReport,
)

logger = logging.getLogger(__name__)


def _skip_reason_for(rule_cls: type, context: ValidationContext) -> str | None:
    """Return a stable, accountant-safe skip reason when context makes it obvious."""
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


def _not_run_outcome(
    rule_id: str,
    *,
    reason_code: str,
    skip_reason: str | None = None,
) -> RuleEvaluationOutcome:
    return RuleEvaluationOutcome(
        rule_id=rule_id,
        outcome=OUTCOME_NOT_RUN,
        skip_reason=skip_reason or reason_code,
        reason_code=reason_code,
        message=reason_message(reason_code),
    )


class ValidationOrchestrator:
    """Evaluates all applicable rules against a validation context."""

    def run(self, context: ValidationContext) -> ValidationReport:
        rules = self._get_applicable_rules(context)
        findings = []
        outcomes: list[RuleEvaluationOutcome] = []
        seen_ids: set[str] = set()
        catalog = catalog_by_rule_id()

        for rule_cls in rules:
            rule = rule_cls()
            rule_id = str(getattr(rule, "rule_id", "") or "")
            if not rule_id:
                continue
            seen_ids.add(rule_id)

            # Catalog NOT_READY labor-law rules that are registered but intentionally inactive
            cat = catalog.get(rule_id)
            if cat is not None and cat.readiness == READINESS_NOT_READY and rule_id.startswith("legal."):
                # Still respect applies_to=False path as RULE_NOT_READY, not silent skip.
                if not rule.applies_to(context):
                    outcomes.append(
                        _not_run_outcome(rule_id, reason_code=REASON_RULE_NOT_READY, skip_reason="rule_not_ready")
                    )
                    continue

            # Legal versioned evaluation requires a known payslip period — never invent today.
            if rule_id.startswith("legal.") and context.period is None:
                if cat is not None and cat.readiness == READINESS_NOT_READY:
                    outcomes.append(
                        _not_run_outcome(
                            rule_id,
                            reason_code=REASON_RULE_NOT_READY,
                            skip_reason="rule_not_ready",
                        )
                    )
                else:
                    outcomes.append(
                        _not_run_outcome(
                            rule_id,
                            reason_code=REASON_MISSING_PAY_PERIOD,
                            skip_reason="missing_pay_period",
                        )
                    )
                continue

            if not rule.applies_to(context):
                legacy = _skip_reason_for(rule_cls, context)
                reason_code = map_legacy_skip_to_reason(legacy)
                if legacy is None:
                    reason_code = REASON_NOT_APPLICABLE
                outcomes.append(
                    _not_run_outcome(
                        rule_id,
                        reason_code=reason_code,
                        skip_reason=legacy or reason_code,
                    )
                )
                continue

            try:
                finding = rule.evaluate(context)
            except Exception:  # noqa: BLE001 — isolate rule failures
                logger.exception("validation_rule_execution_error", extra={"rule_id": rule_id})
                outcomes.append(
                    _not_run_outcome(
                        rule_id,
                        reason_code=REASON_EXECUTION_ERROR,
                        skip_reason="execution_error",
                    )
                )
                continue

            if finding is not None:
                findings.append(finding)
                if finding.message_key == "validation.missing_data" or (
                    finding.severity == FindingSeverity.INFO
                    and (finding.message_key or "").endswith("missing_data")
                ):
                    outcomes.append(
                        RuleEvaluationOutcome(
                            rule_id=rule_id or finding.rule_id,
                            outcome=OUTCOME_UNCERTAIN,
                            skip_reason=None,
                            reason_code=REASON_MISSING_PAYSLIP_DATA,
                            message=reason_message(REASON_MISSING_PAYSLIP_DATA),
                        )
                    )
                else:
                    outcomes.append(
                        RuleEvaluationOutcome(
                            rule_id=rule_id or finding.rule_id,
                            outcome=OUTCOME_FAILED,
                            reason_code=None,
                            message=None,
                        )
                    )
            else:
                # evaluate returned None — only PASS if rule config / legal knowledge was available
                # when the rule depends on YAML (legal.*) and config key missing → NOT_RUN
                if rule_id.startswith("legal.") and self._legal_config_missing(rule, context):
                    outcomes.append(
                        _not_run_outcome(
                            rule_id,
                            reason_code=REASON_NO_APPLICABLE_LEGAL_VERSION,
                            skip_reason="no_applicable_legal_version",
                        )
                    )
                else:
                    outcomes.append(
                        RuleEvaluationOutcome(
                            rule_id=rule_id,
                            outcome=OUTCOME_PASSED,
                        )
                    )

        # Ensure every catalog labor-law rule has an explicit outcome (even if no Python class).
        for law_id in labor_law_rule_ids():
            if law_id in seen_ids:
                continue
            cat = catalog.get(law_id)
            reason = REASON_RULE_NOT_READY
            if cat and cat.readiness == READINESS_NOT_READY:
                reason = REASON_RULE_NOT_READY
            outcomes.append(
                _not_run_outcome(law_id, reason_code=reason, skip_reason="rule_not_ready")
            )

        overall_result = self._compute_result(findings)
        overall_confidence = self._compute_confidence(findings, context)

        evaluated_count = sum(
            1 for item in outcomes if item.outcome in {OUTCOME_PASSED, OUTCOME_FAILED, OUTCOME_UNCERTAIN}
        )

        return ValidationReport(
            validation_run_id=uuid4(),
            overall_result=overall_result.value,
            overall_confidence=overall_confidence,
            findings=tuple(findings),
            rules_evaluated=evaluated_count,
            rules_failed=sum(
                1
                for finding in findings
                if finding.severity
                in (FindingSeverity.WARNING, FindingSeverity.CRITICAL)
            ),
            rule_outcomes=tuple(outcomes),
        )

    @staticmethod
    def _legal_config_missing(rule: object, context: ValidationContext) -> bool:
        """Detect evaluate→None caused by absent YAML config key (not a true PASS)."""
        # Known legal rules look up specific YAML keys; if evaluate returned None without
        # a finding, callers already handled missing data. Config absence returns None
        # in DailyOvertimeLimitRule / MinimumWageRule — detect via reference_dependencies.
        deps = getattr(rule, "reference_dependencies", ()) or ()
        for dep in deps:
            # e.g. legal_rules.daily_overtime_limit → key daily_overtime_limit
            if not str(dep).startswith("legal_rules."):
                continue
            key = str(dep).split(".", 1)[-1]
            if key and key not in context.legal_rules.rules:
                return True
        return False

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
