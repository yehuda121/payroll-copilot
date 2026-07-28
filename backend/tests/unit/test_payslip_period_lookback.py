"""Unit tests for payroll investigation lookback (Scenario B / D data path)."""

from __future__ import annotations

from payroll_copilot.application.services.payslip_period_lookback import (
    lookback_candidates,
    previous_month,
    select_comparison_period,
)
from payroll_copilot.domain.investigation.types import PeriodRef


def test_previous_month_crosses_year_boundary() -> None:
    assert previous_month(PeriodRef(2026, 1)) == PeriodRef(2025, 12)
    assert previous_month(PeriodRef(2026, 7)) == PeriodRef(2026, 6)


def test_lookback_is_rolling_12_across_years() -> None:
    candidates = lookback_candidates(PeriodRef(2026, 3), months=12)
    assert len(candidates) == 12
    assert candidates[0] == PeriodRef(2026, 2)
    assert candidates[-1] == PeriodRef(2025, 3)


def test_select_prefers_immediate_prior_when_present() -> None:
    selected, attempts = select_comparison_period(
        target=PeriodRef(2026, 7),
        available={"2026-07", "2026-06", "2026-01"},
    )
    assert selected == PeriodRef(2026, 6)
    assert attempts[0] == PeriodRef(2026, 6)


def test_select_looks_back_when_x_minus_1_missing() -> None:
    selected, attempts = select_comparison_period(
        target=PeriodRef(2026, 7),
        available={"2026-07", "2026-04", "2025-12"},
    )
    assert selected == PeriodRef(2026, 4)
    assert PeriodRef(2026, 6) in attempts


def test_select_none_when_no_history() -> None:
    selected, attempts = select_comparison_period(
        target=PeriodRef(2026, 7),
        available={"2026-07"},
    )
    assert selected is None
    assert len(attempts) == 12
