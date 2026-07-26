"""Confirmed employment terms projected from confirmed CONTRACT documents.

Never populated from Employee.contract_start_date, system create/onboarding timestamps,
upload dates, or unconfirmed OCR alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID


SALARY_BASIS_VALUES = frozenset({"monthly", "hourly", "daily"})


@dataclass(frozen=True, slots=True)
class ConfirmedEmploymentTerms:
    """Authoritative employment-term snapshot for CONTRACT validation."""

    employment_commencement_date: date | None = None
    salary_basis: str | None = None
    contractual_monthly_salary: Decimal | None = None
    contractual_hourly_rate: Decimal | None = None
    contractual_daily_rate: Decimal | None = None
    employment_scope: Decimal | None = None
    employment_type: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    source_document_id: UUID | None = None
    source_extraction_id: UUID | None = None
    confirmed_at: datetime | None = None

    @property
    def has_any_terms(self) -> bool:
        return any(
            (
                self.employment_commencement_date is not None,
                self.salary_basis is not None,
                self.contractual_monthly_salary is not None,
                self.contractual_hourly_rate is not None,
                self.contractual_daily_rate is not None,
                self.employment_scope is not None,
                self.employment_type is not None,
            )
        )


def _field_value(additional: dict[str, Any], key: str) -> Any | None:
    payload = additional.get(key)
    if isinstance(payload, dict) and "value" in payload:
        value = payload.get("value")
        status = str(payload.get("status") or "").upper()
        if status == "MISSING":
            return None
        return None if value in (None, "") else value
    return None if payload in (None, "") else payload


def parse_iso_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    # Reuse birth-date style normalizer when available
    try:
        from payroll_copilot.application.services.employee_document_form_schemas import (
            normalize_birth_date,
        )

        normalized = normalize_birth_date(text)
        if normalized:
            y, m, d = normalized.split("-")
            return date(int(y), int(m), int(d))
    except Exception:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def parse_money(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, Decimal):
        return raw
    text = str(raw).strip().replace(",", "").replace("₪", "").replace("ILS", "")
    text = text.replace(" ", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def parse_salary_basis(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "monthly": "monthly",
        "month": "monthly",
        "חודשי": "monthly",
        "hourly": "hourly",
        "hour": "hourly",
        "שעתי": "hourly",
        "daily": "daily",
        "day": "daily",
        "יומי": "daily",
    }
    mapped = aliases.get(text, text)
    return mapped if mapped in SALARY_BASIS_VALUES else None


def terms_from_structured(
    structured: dict[str, Any] | None,
    *,
    source_document_id: UUID | None = None,
    source_extraction_id: UUID | None = None,
    confirmed_at: datetime | None = None,
) -> ConfirmedEmploymentTerms:
    additional = (structured or {}).get("additional_fields")
    if not isinstance(additional, dict):
        additional = {}
    return ConfirmedEmploymentTerms(
        employment_commencement_date=parse_iso_date(
            _field_value(additional, "employment_commencement_date")
        ),
        salary_basis=parse_salary_basis(_field_value(additional, "salary_basis")),
        contractual_monthly_salary=parse_money(
            _field_value(additional, "contractual_monthly_salary")
        ),
        contractual_hourly_rate=parse_money(_field_value(additional, "contractual_hourly_rate")),
        contractual_daily_rate=parse_money(_field_value(additional, "contractual_daily_rate")),
        employment_scope=parse_money(_field_value(additional, "employment_scope")),
        employment_type=(
            str(_field_value(additional, "employment_type")).strip().lower()
            if _field_value(additional, "employment_type") not in (None, "")
            else None
        ),
        effective_from=parse_iso_date(_field_value(additional, "effective_from")),
        effective_to=parse_iso_date(_field_value(additional, "effective_to")),
        source_document_id=source_document_id,
        source_extraction_id=source_extraction_id,
        confirmed_at=confirmed_at,
    )


def period_overlaps_terms(terms: ConfirmedEmploymentTerms, *, year: int, month: int) -> bool:
    """True when payslip month is inside [effective_from, effective_to] (inclusive months)."""
    # Month represented as first-of-month for comparison.
    period_start = date(year, month, 1)
    if month == 12:
        period_end = date(year + 1, 1, 1)
    else:
        period_end = date(year, month + 1, 1)

    if terms.effective_from is not None and period_end <= terms.effective_from:
        return False
    if terms.effective_to is not None and period_start > terms.effective_to:
        return False
    return True


def select_terms_for_period(
    candidates: list[ConfirmedEmploymentTerms],
    *,
    year: int,
    month: int,
) -> ConfirmedEmploymentTerms | None:
    """Select applicable confirmed terms without naive 'latest wins'.

    Rules:
    - Ignore candidates that do not overlap the payslip period when dating is present.
    - If multiple overlap → insufficient (return None) — do not guess.
    - If exactly one undated confirmed version exists → use it.
    - If multiple undated → insufficient.
    """
    if not candidates:
        return None

    dated = [t for t in candidates if t.effective_from is not None or t.effective_to is not None]
    undated = [t for t in candidates if t.effective_from is None and t.effective_to is None]

    overlapping = [t for t in dated if period_overlaps_terms(t, year=year, month=month)]
    if len(overlapping) == 1:
        return overlapping[0]
    if len(overlapping) > 1:
        return None
    if dated and not overlapping:
        # Dated versions exist but none apply — do not fall back to undated.
        return None
    if len(undated) == 1:
        return undated[0]
    return None
