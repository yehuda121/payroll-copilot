"""Unit tests for investigation completeness (Scenario C gate / D prerequisites)."""

from __future__ import annotations

from uuid import uuid4

from payroll_copilot.application.services.investigation_completeness import (
    assess_completeness,
    needs_s3_enrichment,
)
from payroll_copilot.domain.investigation.types import (
    InvestigationFocus,
    PeriodRef,
    PeriodSnapshot,
)


def _snap(fields: dict) -> PeriodSnapshot:
    return PeriodSnapshot(
        period=PeriodRef(2026, 7),
        document_id=uuid4(),
        storage_key="organizations/o/employees/e/payroll/2026/07/payslip/d/f.pdf",
        structured_fields=fields,
    )


def test_complete_when_essentials_and_focus_keys_present() -> None:
    report = assess_completeness(
        _snap(
            {
                "gross_salary": {"value": "12000"},
                "net_salary": {"value": "9000"},
                "overtime_hours": {"value": "8"},
            }
        ),
        focus=InvestigationFocus.OVERTIME,
    )
    assert report.is_complete is True
    assert needs_s3_enrichment(report) is False


def test_enrichment_needed_when_overtime_missing() -> None:
    report = assess_completeness(
        _snap(
            {
                "gross_salary": {"value": "12000"},
                "net_salary": {"value": "9000"},
            }
        ),
        focus=InvestigationFocus.OVERTIME,
    )
    assert report.is_complete is False
    assert "overtime_hours" in report.missing_enrichment_keys
    assert needs_s3_enrichment(report) is True


def test_essential_missing_triggers_enrichment_gate() -> None:
    report = assess_completeness(
        _snap({"base_salary": {"value": "8000"}}),
        focus=InvestigationFocus.GENERAL,
    )
    assert "gross_salary" in report.missing_essential_keys
    assert "net_salary" in report.missing_essential_keys
    assert needs_s3_enrichment(report) is True
