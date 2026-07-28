"""Deterministic line-item diffs for payroll investigation.

Compares structured extraction fields only. Does NOT recalculate tax or salary rules.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from payroll_copilot.domain.investigation.types import LineItemDelta, PeriodSnapshot

# Core comparison keys for anomaly explanations (canonical registry keys).
COMPARISON_FIELD_KEYS: tuple[str, ...] = (
    "base_salary",
    "gross_salary",
    "net_salary",
    "amount_paid",
    "overtime_hours",
    "regular_hours",
    "travel_expenses",
    "income_tax",
    "national_insurance",
    "health_tax",
    "pension_employee",
    "pension_employer",
    "total_deductions",
    "vacation_balance",
    "sick_leave_balance",
)


def _payload_value(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, dict):
        for key in ("corrected_value", "effective_value", "value", "extracted_value"):
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
        return None
    return payload


def structured_field_value(structured: dict[str, Any], key: str) -> Any:
    if key in structured:
        return _payload_value(structured.get(key))
    additional = structured.get("additional_fields")
    if isinstance(additional, dict) and key in additional:
        return _payload_value(additional.get(key))
    return None


def coerce_numeric(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = (
            value.strip()
            .replace("₪", "")
            .replace("ILS", "")
            .replace("NIS", "")
            .replace(",", "")
            .replace(" ", "")
        )
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def format_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _direction(
    current: Decimal | None,
    prior: Decimal | None,
) -> str:
    if current is None and prior is None:
        return "unknown"
    if current is not None and prior is None:
        return "appeared"
    if current is None and prior is not None:
        return "disappeared"
    assert current is not None and prior is not None
    if current > prior:
        return "increased"
    if current < prior:
        return "decreased"
    return "unchanged"


def diff_snapshots(
    current: PeriodSnapshot,
    prior: PeriodSnapshot,
    *,
    field_keys: tuple[str, ...] | None = None,
) -> list[LineItemDelta]:
    """Return deltas for selected keys (defaults to COMPARISON_FIELD_KEYS)."""
    keys = field_keys or COMPARISON_FIELD_KEYS
    deltas: list[LineItemDelta] = []
    for key in keys:
        cur_raw = structured_field_value(current.structured_fields, key)
        prior_raw = structured_field_value(prior.structured_fields, key)
        cur_num = coerce_numeric(cur_raw)
        prior_num = coerce_numeric(prior_raw)
        # Skip keys missing on both sides.
        if cur_num is None and prior_num is None and cur_raw in (None, "") and prior_raw in (None, ""):
            continue
        abs_delta: str | None = None
        if cur_num is not None and prior_num is not None:
            abs_delta = format_decimal(cur_num - prior_num)
        deltas.append(
            LineItemDelta(
                field_key=key,
                current_value=format_decimal(cur_num) if cur_num is not None else (
                    str(cur_raw) if cur_raw not in (None, "") else None
                ),
                prior_value=format_decimal(prior_num) if prior_num is not None else (
                    str(prior_raw) if prior_raw not in (None, "") else None
                ),
                absolute_delta=abs_delta,
                direction=_direction(cur_num, prior_num),
            )
        )
    return deltas


def material_deltas(deltas: list[LineItemDelta]) -> list[LineItemDelta]:
    """Filter to items that changed (exclude unchanged)."""
    return [d for d in deltas if d.direction != "unchanged"]
