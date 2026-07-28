"""Unit tests for payroll investigation graph routing (Scenarios A–D)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from payroll_copilot.domain.investigation.types import (
    InvestigationOutcome,
    PeriodRef,
    PeriodSnapshot,
)
from payroll_copilot.infrastructure.ai.agents.payroll_investigation_graph import (
    PayrollInvestigationGraph,
)


class _FakeData:
    def __init__(
        self,
        *,
        periods: set[str],
        snapshots: dict[str, PeriodSnapshot],
        enrich_fill: dict[str, object] | None = None,
    ) -> None:
        self.periods = periods
        self.snapshots = snapshots
        self.enrich_fill = enrich_fill or {}
        self.enrich_calls = 0

    async def list_available_payslip_periods(
        self,
        *,
        organization_id,
        employee_id,
        include_unpublished: bool = False,
    ) -> set[str]:
        return set(self.periods)

    async def load_period_snapshot(
        self,
        *,
        organization_id,
        employee_id,
        period: PeriodRef,
        include_unpublished: bool = False,
    ) -> PeriodSnapshot | None:
        return self.snapshots.get(period.key)

    async def enrich_snapshot_from_original(
        self,
        snapshot: PeriodSnapshot,
        *,
        missing_keys: tuple[str, ...],
    ) -> PeriodSnapshot:
        self.enrich_calls += 1
        merged = dict(snapshot.structured_fields)
        for key in missing_keys:
            if key in self.enrich_fill:
                merged[key] = self.enrich_fill[key]
        return PeriodSnapshot(
            period=snapshot.period,
            document_id=snapshot.document_id,
            storage_key=snapshot.storage_key,
            structured_fields=merged,
            finding_excerpts=list(snapshot.finding_excerpts),
            enrichment_applied=True,
            enrichment_notes="filled:" + ",".join(missing_keys),
        )


def _snap(period: PeriodRef, fields: dict, *, storage_key: str | None = "s3/key") -> PeriodSnapshot:
    return PeriodSnapshot(
        period=period,
        document_id=uuid4(),
        storage_key=storage_key,
        structured_fields=fields,
    )


@pytest.mark.asyncio
async def test_scenario_a_adjacent_month_explained() -> None:
    jul = PeriodRef(2026, 7)
    jun = PeriodRef(2026, 6)
    data = _FakeData(
        periods={"2026-07", "2026-06"},
        snapshots={
            "2026-07": _snap(
                jul,
                {
                    "gross_salary": {"value": "12000"},
                    "net_salary": {"value": "9000"},
                    "overtime_hours": {"value": "10"},
                },
            ),
            "2026-06": _snap(
                jun,
                {
                    "gross_salary": {"value": "11000"},
                    "net_salary": {"value": "8500"},
                    "overtime_hours": {"value": "2"},
                },
            ),
        },
    )
    result = await PayrollInvestigationGraph(data).run(
        message="למה ירד לי הנטו?",
        session_id="s1",
        locale="he",
        organization_id=uuid4(),
        employee_id=uuid4(),
        target_year=2026,
        target_month=7,
    )
    assert result.outcome == InvestigationOutcome.EXPLAINED
    assert result.comparison_period == jun
    assert result.target_period == jul
    assert any(d.field_key == "net_salary" for d in result.deltas)
    assert "יולי 2026" in result.answer
    assert "יוני 2026" in result.answer
    assert "→" not in result.answer
    assert "s3_ephemeral_enrichment" not in result.used_tools
    assert data.enrich_calls == 0


@pytest.mark.asyncio
async def test_scenario_b_lookback_skips_missing_prior() -> None:
    jul = PeriodRef(2026, 7)
    apr = PeriodRef(2026, 4)
    data = _FakeData(
        periods={"2026-07", "2026-04"},
        snapshots={
            "2026-07": _snap(
                jul,
                {
                    "gross_salary": {"value": "12000"},
                    "net_salary": {"value": "9000"},
                    "base_salary": {"value": "10000"},
                    "overtime_hours": {"value": "0"},
                    "income_tax": {"value": "1000"},
                    "pension_employee": {"value": "500"},
                    "total_deductions": {"value": "3000"},
                },
            ),
            "2026-04": _snap(
                apr,
                {
                    "gross_salary": {"value": "12000"},
                    "net_salary": {"value": "9500"},
                    "base_salary": {"value": "10000"},
                    "overtime_hours": {"value": "0"},
                    "income_tax": {"value": "800"},
                    "pension_employee": {"value": "500"},
                    "total_deductions": {"value": "2500"},
                },
            ),
        },
    )
    result = await PayrollInvestigationGraph(data).run(
        message="what changed on my payslip?",
        session_id="s2",
        locale="en",
        organization_id=uuid4(),
        employee_id=uuid4(),
        target_year=2026,
        target_month=7,
    )
    assert result.outcome == InvestigationOutcome.EXPLAINED
    assert result.comparison_period == apr
    assert "2026-06" in result.lookback_attempts


@pytest.mark.asyncio
async def test_scenario_c_triggers_ephemeral_enrichment() -> None:
    jul = PeriodRef(2026, 7)
    jun = PeriodRef(2026, 6)
    data = _FakeData(
        periods={"2026-07", "2026-06"},
        snapshots={
            "2026-07": _snap(
                jul,
                {
                    "gross_salary": {"value": "12000"},
                    "net_salary": {"value": "9000"},
                },
            ),
            "2026-06": _snap(
                jun,
                {
                    "gross_salary": {"value": "11000"},
                    "net_salary": {"value": "8500"},
                    "overtime_hours": {"value": "2"},
                },
            ),
        },
        enrich_fill={"overtime_hours": {"value": "12"}},
    )
    result = await PayrollInvestigationGraph(data).run(
        message="why did my overtime increase?",
        session_id="s3",
        locale="en",
        organization_id=uuid4(),
        employee_id=uuid4(),
        target_year=2026,
        target_month=7,
    )
    assert result.outcome == InvestigationOutcome.EXPLAINED
    assert data.enrich_calls >= 1
    assert "s3_ephemeral_enrichment" in result.used_tools
    assert any(d.field_key == "overtime_hours" for d in result.deltas)


@pytest.mark.asyncio
async def test_scenario_d_no_history_asks_user() -> None:
    jul = PeriodRef(2026, 7)
    data = _FakeData(
        periods={"2026-07"},
        snapshots={
            "2026-07": _snap(
                jul,
                {
                    "gross_salary": {"value": "12000"},
                    "net_salary": {"value": "9000"},
                },
            ),
        },
    )
    result = await PayrollInvestigationGraph(data).run(
        message="למה ירד לי הנטו?",
        session_id="s4",
        locale="he",
        organization_id=uuid4(),
        employee_id=uuid4(),
        target_year=2026,
        target_month=7,
    )
    assert result.outcome == InvestigationOutcome.NEEDS_USER_INPUT
    assert result.comparison_period is None
    assert result.clarification_prompt
    assert "יוני 2026" in result.answer
    assert "אינו זמין" in result.answer or "לא זמין" in result.answer
    assert data.enrich_calls == 0
