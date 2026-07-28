"""Rolling lookback for payroll investigation period selection.

Window: rolling 12 months across year boundaries (approved product decision).
Never invents a comparison period — returns None when no historical payslip exists.
"""

from __future__ import annotations

from payroll_copilot.domain.investigation.types import PeriodRef

_LOOKBACK_MONTHS = 12


def previous_month(period: PeriodRef) -> PeriodRef:
    if period.month <= 1:
        return PeriodRef(year=period.year - 1, month=12)
    return PeriodRef(year=period.year, month=period.month - 1)


def lookback_candidates(
    target: PeriodRef,
    *,
    months: int = _LOOKBACK_MONTHS,
) -> list[PeriodRef]:
    """Return up to ``months`` prior periods, newest first (excludes target)."""
    if months < 1:
        return []
    cursor = target
    out: list[PeriodRef] = []
    for _ in range(months):
        cursor = previous_month(cursor)
        out.append(cursor)
    return out


def select_comparison_period(
    *,
    target: PeriodRef,
    available: set[str] | frozenset[str],
    months: int = _LOOKBACK_MONTHS,
) -> tuple[PeriodRef | None, list[PeriodRef]]:
    """Pick preferred comparator: X-1 if present, else first lookback hit.

    ``available`` holds period keys ``YYYY-MM``.
    Returns (selected_or_none, attempted_lookback_order).
    """
    candidates = lookback_candidates(target, months=months)
    for candidate in candidates:
        if candidate.key in available:
            return candidate, candidates
    return None, candidates
