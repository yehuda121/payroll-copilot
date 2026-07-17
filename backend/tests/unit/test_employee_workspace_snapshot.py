"""Tests for employee workspace comparison snapshot persistence helpers."""

from __future__ import annotations

from payroll_copilot.application.services.employee_workspace_snapshot import (
    apply_comparison_snapshot,
    fields_for_workspace_api,
    patch_period_resolution_keep,
    read_comparison_snapshot,
)
from payroll_copilot.application.services.payslip_identity_comparison import (
    FieldComparison,
    IdentityCheckResult,
    PayslipComparisonResult,
    PeriodCheckResult,
)


def _comparison(*, period_blocks: bool = True) -> PayslipComparisonResult:
    return PayslipComparisonResult(
        identity_check=IdentityCheckResult(
            overall="match",
            blocks_confirmation=False,
            fields=[
                FieldComparison(
                    key="national_id",
                    status="match",
                    extracted_display="***",
                    expected_display="***",
                    severity="info",
                )
            ],
        ),
        period_check=PeriodCheckResult(
            status="mismatch",
            blocks_confirmation=period_blocks,
            selected_year=2026,
            selected_month=6,
            extracted_year=2026,
            extracted_month=7,
            explanation_code="period_mismatch",
        ),
    )


def test_apply_and_read_snapshot_roundtrip():
    meta = apply_comparison_snapshot({}, _comparison())
    snap = read_comparison_snapshot(meta)
    assert snap is not None
    assert snap["identity_check"]["overall"] == "match"
    assert snap["period_check"]["status"] == "mismatch"
    assert snap["blocks_confirmation"] is True


def test_patch_period_resolution_keep_clears_period_block():
    meta = apply_comparison_snapshot({}, _comparison(period_blocks=True))
    patched = patch_period_resolution_keep(meta)
    assert patched["period_resolution"] == "keep_selected"
    assert patched["period_check"]["blocks_confirmation"] is False
    assert patched["period_check"]["explanation_code"] == "period_kept_selected"
    assert patched["blocks_confirmation"] is False


def test_fields_for_workspace_api_normalizes_lifecycle_shape():
    rows = fields_for_workspace_api(
        [
            {
                "key": "employee_name",
                "effective_value": "Dana",
                "confidence": 0.9,
                "source_text": "Dana",
                "extraction_status": "FOUND",
                "edited_by_employee": False,
            }
        ]
    )
    assert rows == [
        {
            "key": "employee_name",
            "value": "Dana",
            "confidence": 0.9,
            "source_text": "Dana",
            "status": "FOUND",
            "edited_by_user": False,
        }
    ]
