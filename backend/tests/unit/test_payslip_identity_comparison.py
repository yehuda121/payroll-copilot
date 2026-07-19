"""Unit tests for server-side payslip identity/period comparison."""

from __future__ import annotations

from payroll_copilot.application.services.payslip_identity_comparison import (
    PayslipIdentityComparisonService,
    person_name_tokens_equal,
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


def test_hebrew_reversed_name_tokens_match():
    assert person_name_tokens_equal("יהודה שמולביץ", "שמולביץ יהודה")
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="יהודה שמולביץ",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id="313366783",
            employee_name="שמולביץ יהודה",
            pay_period="06/2026",
        ),
    )
    name = next(f for f in result.identity_check.fields if f.key == "employee_name")
    assert name.status == "match"
    assert name.explanation_code == "employee_name_match"
    assert result.identity_check.overall == "match"


def test_latin_first_last_swap_matches():
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
            employee_name="Shmulovitz Yehuda",
            pay_period="06/2026",
        ),
    )
    name = next(f for f in result.identity_check.fields if f.key == "employee_name")
    assert name.status == "match"


def test_middle_name_omission_remains_mismatch():
    assert not person_name_tokens_equal("Yehuda David Shmulovitz", "Yehuda Shmulovitz")
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Yehuda David Shmulovitz",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id="313366783",
            employee_name="Yehuda Shmulovitz",
            pay_period="06/2026",
        ),
    )
    name = next(f for f in result.identity_check.fields if f.key == "employee_name")
    assert name.status == "mismatch"
    assert name.severity == "warning"
    assert name.blocks_confirmation is False
    assert result.identity_check.blocks_confirmation is False


def test_hyphenated_surname_preserved_and_order_insensitive():
    assert person_name_tokens_equal("Anne-Marie Cohen", "Cohen Anne-Marie")
    assert not person_name_tokens_equal("Anne-Marie Cohen", "Anne Marie Cohen")
    svc = PayslipIdentityComparisonService()
    result = svc.compare(
        trusted_full_name="Anne-Marie Cohen",
        trusted_employee_number="5",
        trusted_national_id_plaintext="313366783",
        trusted_national_id_masked="****6783",
        selected_year=2026,
        selected_month=6,
        extraction_fields=_fields(
            employee_id="313366783",
            employee_name="Cohen Anne-Marie",
            pay_period="06/2026",
        ),
    )
    name = next(f for f in result.identity_check.fields if f.key == "employee_name")
    assert name.status == "match"


def test_duplicate_tokens_require_exact_multiset():
    assert person_name_tokens_equal("John John Smith", "Smith John John")
    assert not person_name_tokens_equal("John John Smith", "John Smith")
