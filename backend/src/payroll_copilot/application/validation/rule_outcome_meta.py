"""Helpers to attach explicit category / input metadata to rule outcomes."""

from __future__ import annotations

from typing import Any

from payroll_copilot.domain.enums import RuleCategory
from payroll_copilot.domain.rules import ValidationContext
from payroll_copilot.domain.value_objects import RuleEvaluationOutcome

# Stable UI / developer grouping (not identical to RuleCategory enum).
DISPLAY_PAYSLIP_SANITY = "PAYSLIP_SANITY"
DISPLAY_EMPLOYEE_MATCH = "EMPLOYEE_MATCH"
DISPLAY_CONTRACT = "CONTRACT"
DISPLAY_LEGAL = "LEGAL"
DISPLAY_HISTORICAL = "HISTORICAL"
DISPLAY_DEPARTMENT = "DEPARTMENT"


def display_category_for(rule_id: str, category: RuleCategory | str | None) -> str:
    rid = (rule_id or "").lower()
    cat = category.value if isinstance(category, RuleCategory) else str(category or "").lower()
    if rid.startswith("sanity.") or cat == RuleCategory.SANITY.value:
        return DISPLAY_PAYSLIP_SANITY
    if rid.startswith("employee.") or cat == RuleCategory.EMPLOYEE.value:
        return DISPLAY_EMPLOYEE_MATCH
    if rid.startswith("contract.") or cat == RuleCategory.CONTRACT.value:
        return DISPLAY_CONTRACT
    if rid.startswith("historical.") or cat == RuleCategory.HISTORICAL.value:
        return DISPLAY_HISTORICAL
    if rid.startswith("department.") or cat == RuleCategory.DEPARTMENT.value:
        return DISPLAY_DEPARTMENT
    return DISPLAY_LEGAL


def legal_source_for(rule_id: str, context: ValidationContext) -> str | None:
    if not (rule_id or "").startswith("legal."):
        return None
    for cfg in context.legal_rules.rules.values():
        if cfg.rule_id == rule_id:
            ref = cfg.legal_reference or {}
            return str(ref.get("en") or ref.get("he") or "") or None
    return None


def enrich_outcome(
    outcome: RuleEvaluationOutcome,
    *,
    rule: Any | None = None,
    context: ValidationContext | None = None,
    category: RuleCategory | str | None = None,
    required_inputs: tuple[str, ...] | None = None,
) -> RuleEvaluationOutcome:
    """Return a copy of outcome with explicit metadata filled in."""
    rule_id = outcome.rule_id
    cat = category
    inputs = required_inputs
    if rule is not None:
        cat = cat or getattr(rule, "category", None)
        if inputs is None:
            raw = getattr(rule, "input_fields", ()) or ()
            inputs = tuple(str(x) for x in raw)
    cat_value = cat.value if isinstance(cat, RuleCategory) else (str(cat) if cat else None)
    display = display_category_for(rule_id, cat)
    legal_source = None
    legal_version = None
    if context is not None:
        legal_source = legal_source_for(rule_id, context)
        if (rule_id or "").startswith("legal.") or display == DISPLAY_LEGAL:
            legal_version = context.legal_rules.version
    return RuleEvaluationOutcome(
        rule_id=rule_id,
        outcome=outcome.outcome,
        skip_reason=outcome.skip_reason,
        reason_code=outcome.reason_code,
        message=outcome.message,
        category=cat_value or outcome.category,
        display_category=display,
        required_inputs=inputs if inputs is not None else outcome.required_inputs,
        legal_source=legal_source if legal_source is not None else outcome.legal_source,
        legal_version=legal_version if legal_version is not None else outcome.legal_version,
    )


def outcome_to_dict(item: RuleEvaluationOutcome) -> dict[str, Any]:
    return {
        "rule_id": item.rule_id,
        "outcome": item.outcome,
        "skip_reason": item.skip_reason,
        "reason_code": item.reason_code,
        "message": item.message,
        "category": item.category,
        "display_category": item.display_category,
        "required_inputs": list(item.required_inputs),
        "legal_source": item.legal_source,
        "legal_version": item.legal_version,
    }
