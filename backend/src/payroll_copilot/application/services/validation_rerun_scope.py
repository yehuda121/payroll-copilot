"""Selective validation rerun helpers — taxonomy/rule-id scopes without OCR."""

from __future__ import annotations

from payroll_copilot.application.services.validation_taxonomy import (
    ValidationTaxonomy,
    taxonomy_for_rule_id,
)
from payroll_copilot.domain.rules import get_registered_rules


EMPLOYEE_CHECKS_TAXONOMIES = frozenset(
    {ValidationTaxonomy.EMPLOYEE, ValidationTaxonomy.CONTRACT}
)
LAW_CHECKS_TAXONOMIES = frozenset({ValidationTaxonomy.LAW})


def disabled_rule_ids_for_scope(
    *,
    scope: str | None,
    rule_ids: frozenset[str] | None = None,
) -> frozenset[str]:
    """Return rule IDs to disable so only the requested scope is evaluated.

    Scopes:
      full / None — evaluate all (empty disabled set)
      employee_checks — EMPLOYEE + CONTRACT taxonomy
      law_checks — LAW taxonomy
      rules — only explicit rule_ids
    """
    registered = get_registered_rules()
    all_ids = frozenset(registered.keys())
    normalized = (scope or "full").strip().lower()

    if normalized in {"full", "all", ""}:
        return frozenset()

    if normalized == "rules":
        if not rule_ids:
            return all_ids  # nothing selected → evaluate nothing
        keep = rule_ids & all_ids
        return all_ids - keep

    if normalized == "employee_checks":
        keep = frozenset(
            rid
            for rid in all_ids
            if taxonomy_for_rule_id(rid, getattr(registered[rid], "category", None))
            in EMPLOYEE_CHECKS_TAXONOMIES
            or rid.startswith("employee.")
            or rid.startswith("contract.")
        )
        # Include department.* (taxonomy CONTRACT) in employee checks UI group.
        keep = keep | frozenset(rid for rid in all_ids if rid.startswith("department."))
        return all_ids - keep

    if normalized == "law_checks":
        keep = frozenset(
            rid
            for rid in all_ids
            if taxonomy_for_rule_id(rid, getattr(registered[rid], "category", None))
            in LAW_CHECKS_TAXONOMIES
            or rid.startswith("legal.")
        )
        return all_ids - keep

    # Unknown scope → safe full run
    return frozenset()


def merge_findings_preserving_unscoped(
    *,
    previous_findings: list,
    new_findings: list,
    evaluated_rule_ids: frozenset[str],
) -> list:
    """Replace findings for re-evaluated rules; keep prior findings for others."""
    kept = [f for f in previous_findings if getattr(f, "rule_id", None) not in evaluated_rule_ids]
    return list(kept) + list(new_findings)


def merge_rule_outcomes_preserving_unscoped(
    *,
    previous_outcomes: list,
    new_outcomes: list,
    evaluated_rule_ids: frozenset[str],
) -> list:
    """Replace outcomes for re-evaluated rules; keep prior outcomes for others."""
    kept = [
        item
        for item in previous_outcomes
        if getattr(item, "rule_id", None) not in evaluated_rule_ids
    ]
    return list(kept) + list(new_outcomes)
