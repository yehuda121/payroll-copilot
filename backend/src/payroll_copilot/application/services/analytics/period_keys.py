"""Shared payroll-period helpers for analytics (period_year / period_month only)."""

from __future__ import annotations

from typing import Any

from payroll_copilot.domain.value_objects import PayPeriod


def period_from_document(document: Any) -> PayPeriod | None:
    period = getattr(document, "period", None)
    if period is None:
        return None
    year = getattr(period, "year", None)
    month = getattr(period, "month", None)
    if year is None or month is None:
        return None
    try:
        return PayPeriod(year=int(year), month=int(month))
    except (TypeError, ValueError):
        return None


def period_key(period: PayPeriod) -> tuple[int, int]:
    return (period.year, period.month)


def matches_year(period: PayPeriod | None, year: int | None) -> bool:
    if period is None:
        return False
    if year is None:
        return True
    return period.year == year
