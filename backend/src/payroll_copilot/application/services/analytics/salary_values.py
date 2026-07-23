"""Extract salary amounts from existing extraction / document payloads.

Does not persist salary. Reuses the same structured field shapes as review/validation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from payroll_copilot.application.services.employee_document_lifecycle import fields_from_structured
from payroll_copilot.application.validation.structured_payslip_mapper import coerce_money


def _decimal_from_field_row(row: dict[str, Any] | None) -> Decimal | None:
    if not row:
        return None
    money = coerce_money(row.get("effective_value"))
    if money is None:
        money = coerce_money(row.get("extracted_value"))
    return money.amount if money is not None else None


def _decimal_from_metadata(metadata: dict[str, Any] | None, key: str) -> Decimal | None:
    if not metadata:
        return None
    money = coerce_money(metadata.get(key))
    return money.amount if money is not None else None


def salary_amounts_from_sources(
    *,
    structured_data: dict[str, Any] | None,
    document_metadata: dict[str, Any] | None = None,
) -> tuple[Decimal | None, Decimal | None, str]:
    """Return (net, gross, currency) preferring extraction structured_data."""
    fields = {str(row.get("key")): row for row in fields_from_structured(structured_data)}
    net = _decimal_from_field_row(fields.get("net_salary"))
    gross = _decimal_from_field_row(fields.get("gross_salary"))
    if net is None:
        net = _decimal_from_metadata(document_metadata, "net_salary")
    if gross is None:
        gross = _decimal_from_metadata(document_metadata, "gross_salary")
    return net, gross, "ILS"
