"""Resolve period-applicable legal parameters from YAML rule configs.

Supports optional parameters.schedule:
  schedule:
    - effective_from: "2024-04-01"
      amount: 32.11
    - effective_from: "2026-01-01"
      amount: 32.11

When schedule is absent, uses flat parameters (current file values).
Never invents rates — only values present in YAML.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from payroll_copilot.domain.rules import LegalRuleConfig


def _parse_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = str(raw).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def resolve_parameters_as_of(
    rule_config: LegalRuleConfig,
    *,
    as_of: date,
) -> dict[str, Any]:
    """Return parameter dict applicable on as_of (payslip period month start)."""
    params = dict(rule_config.parameters or {})
    schedule = params.pop("schedule", None)
    if not isinstance(schedule, list) or not schedule:
        return params

    applicable: list[tuple[date, dict[str, Any]]] = []
    for row in schedule:
        if not isinstance(row, dict):
            continue
        start = _parse_date(row.get("effective_from"))
        if start is None:
            continue
        if start <= as_of:
            entry = {k: v for k, v in row.items() if k != "effective_from"}
            applicable.append((start, entry))
    if not applicable:
        return params
    applicable.sort(key=lambda item: item[0])
    merged = dict(params)
    merged.update(applicable[-1][1])
    return merged
