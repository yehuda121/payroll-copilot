"""Unit tests for server-side payslip identity/period comparison."""

from __future__ import annotations

from payroll_copilot.application.services.payslip_identity_comparison import (
    PayslipIdentityComparisonService,
)


def _fields(**kwargs):
    out = []
    for key, payload in kwargs.items():
        if isinstance(payload, dict):
            item = {"key": key, **payload}
        else:
            item = {"key": key, "value": payload, "status": "FOUND", "confidence": 0.95}
        out.append(item)
    return out


def test_national_id_match_and_period_match():
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id="313366783",
            employee_number="5",
            employee_name="Yehuda Shmulovitz",
            pay_period="06/2026",
        ),
    )
    assert result.identity_check.overall == "match"
    assert result.identity_check.blocks_confirmation is False
    assert result.period_check.status == "match"
    assert result.blocks_confirmation is False
    nid = next(f for f in result.identity_check.fields if f.key == "national_id")
    assert nid.extracted_display == "****6783"
    assert "313366783" not in str(result.identity_check.to_dict())


def test_national_id_mismatch_blocks():
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id="123456789",
            employee_name="Yehuda Shmulovitz",
            pay_period="2026-06",
        ),
    )
    assert result.identity_check.blocks_confirmation is True
    assert result.identity_check.overall == "mismatch"
    assert result.blocks_confirmation is True


def test_name_mismatch_warns_but_does_not_block_when_nid_matches():
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id="313366783",
            employee_name="Someone Else",
            pay_period="06/2026",
        ),
    )
    name = next(f for f in result.identity_check.fields if f.key == "employee_name")
    assert name.status == "mismatch"
    assert name.blocks_confirmation is False
    assert result.identity_check.blocks_confirmation is False


def test_name_different_language_cannot_validate():
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id="313366783",
            employee_name="יהודה שמולוביץ",
            pay_period="06/2026",
        ),
    )
    name = next(f for f in result.identity_check.fields if f.key == "employee_name")
    assert name.status == "cannot_validate"
    assert name.explanation_code == "employee_name_language_mismatch"
    assert name.blocks_confirmation is False
    assert result.blocks_confirmation is False


def test_period_keep_selected_does_not_block():
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=1,
        period_resolution="keep_selected",
        extraction_fields=_fields(
            employee_id="313366783",
            employee_name="Yehuda Shmulovitz",
            pay_period="02/2026",
        ),
    )
    assert result.period_check.status == "mismatch"
    assert result.period_check.blocks_confirmation is False
    assert result.period_check.explanation_code == "period_kept_selected"


def test_period_mismatch_blocks():
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id="313366783",
            employee_name="Yehuda Shmulovitz",
            pay_period="07/2026",
        ),
    )
    assert result.period_check.status == "mismatch"
    assert result.period_check.blocks_confirmation is True
    assert result.period_check.extracted_month == 7
    assert result.blocks_confirmation is True


def test_low_confidence_is_uncertain_not_mismatch():
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id={"value": "999999999", "status": "FOUND", "confidence": 0.4},
            pay_period={"value": "07/2026", "status": "FOUND", "confidence": 0.3},
        ),
    )
    nid = next(f for f in result.identity_check.fields if f.key == "national_id")
    assert nid.status == "uncertain"
    assert nid.blocks_confirmation is False
    assert result.period_check.status == "uncertain"
    assert result.period_check.blocks_confirmation is False


def test_missing_values_remain_missing():
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id={"value": None, "status": "MISSING"},
            employee_name={"value": None, "status": "MISSING"},
            pay_period={"value": None, "status": "MISSING"},
        ),
    )
    assert all(
        f.status == "missing"
        for f in result.identity_check.fields
        if f.key in {"national_id", "employee_name"}
    )
    assert result.period_check.status == "missing"
    assert result.blocks_confirmation is False
