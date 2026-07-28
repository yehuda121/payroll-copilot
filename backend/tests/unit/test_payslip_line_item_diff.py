"""Unit tests for deterministic payslip line-item diffs (Scenario A)."""

from __future__ import annotations

from uuid import uuid4

from payroll_copilot.application.services.payslip_line_item_diff import (
    diff_snapshots,
    material_deltas,
)
from payroll_copilot.domain.investigation.types import PeriodRef, PeriodSnapshot


def _snap(year: int, month: int, fields: dict) -> PeriodSnapshot:
    return PeriodSnapshot(
        period=PeriodRef(year, month),
        document_id=uuid4(),
        storage_key=None,
        structured_fields=fields,
    )


def test_diff_attributes_net_drop_to_overtime_and_tax() -> None:
    current = _snap(
        2026,
        7,
        {
            "gross_salary": {"value": "12000"},
            "net_salary": {"value": "9000"},
            "overtime_hours": {"value": "10"},
            "income_tax": {"value": "2000"},
        },
    )
    prior = _snap(
        2026,
        6,
        {
            "gross_salary": {"value": "11000"},
            "net_salary": {"value": "9500"},
            "overtime_hours": {"value": "2"},
            "income_tax": {"value": "1500"},
        },
    )
    deltas = material_deltas(diff_snapshots(current, prior))
    by_key = {d.field_key: d for d in deltas}
    assert by_key["net_salary"].direction == "decreased"
    assert by_key["net_salary"].absolute_delta == "-500"
    assert by_key["overtime_hours"].direction == "increased"
    assert by_key["income_tax"].direction == "increased"
    assert by_key["gross_salary"].direction == "increased"


def test_diff_skips_keys_missing_on_both_sides() -> None:
    current = _snap(2026, 7, {"gross_salary": {"value": "10000"}, "net_salary": {"value": "8000"}})
    prior = _snap(2026, 6, {"gross_salary": {"value": "10000"}, "net_salary": {"value": "8000"}})
    deltas = diff_snapshots(current, prior)
    assert all(d.field_key != "overtime_hours" for d in deltas)
    assert material_deltas(deltas) == []
