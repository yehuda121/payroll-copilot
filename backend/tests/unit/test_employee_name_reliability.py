"""Employee-name reliability without obsolete semantic LLM extractor."""

from __future__ import annotations

from typing import Any

from payroll_copilot.application.services.dynamic_document import (
    DynamicDocumentEntry,
    project_structured_from_entries,
)
from payroll_copilot.application.services.ocr_line_evidence import (
    DEFAULT_HIGH_PRIORITY_OCR_RESERVE,
    DEFAULT_MERGE_MAX_CANDIDATES,
    build_ocr_line_evidence_bundle,
    evidence_candidate_priority_tier,
    merge_evidence_bundles,
)
from payroll_copilot.application.services.parser_evidence import (
    employee_name_implausible_reason,
)
from payroll_copilot.application.services.payslip_boundary_detector import (
    PayslipBoundaryDetector,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import _fields_from_entries
from payroll_copilot.domain.entities import Employee


def test_national_id_rejected_as_employee_name() -> None:
    assert employee_name_implausible_reason("313366783") is not None


def test_unicode_scripts_hebrew_english_arabic_plausible() -> None:
    assert employee_name_implausible_reason("דנה כהן") is None
    assert employee_name_implausible_reason("Dana Cohen") is None


def test_website_email_date_implausible() -> None:
    assert employee_name_implausible_reason("https://example.com") is not None
    assert employee_name_implausible_reason("a@b.com") is not None
    assert employee_name_implausible_reason("03/11/2019") is not None


def test_grounded_name_survives_canonical_projection() -> None:
    entry = DynamicDocumentEntry(
        id="e1",
        key="שם עובד",
        value="Dana Cohen",
        confidence=0.91,
        source="ocr",
    )
    structured, _ = project_structured_from_entries([entry])
    assert structured["employee_name"]["value"] == "Dana Cohen"
    views = _fields_from_entries([entry])
    assert views[0].value == "Dana Cohen"


def test_accountant_matched_profile_name_is_not_extraction_field() -> None:
    """Matched employee profile name must not be injected as an extracted field."""
    employee = Employee(
        id=__import__("uuid").uuid4(),
        organization_id=__import__("uuid").uuid4(),
        employee_number="1001",
        first_name="Profile",
        last_name="Only",
        department_id=__import__("uuid").uuid4(),
        employment_type=__import__(
            "payroll_copilot.domain.enums", fromlist=["EmploymentType"]
        ).EmploymentType.FULL_TIME,
        salary_type=__import__(
            "payroll_copilot.domain.enums", fromlist=["SalaryType"]
        ).SalaryType.MONTHLY,
        contract_start_date=__import__("datetime").date(2024, 1, 1),
    )
    assert employee.full_name == "Profile Only"
    # Extraction projection stays document-sourced.
    structured, _ = project_structured_from_entries([])
    assert structured["employee_name"]["value"] in (None, "")


def test_ocr_line_bundle_exposes_unlabeled_name_candidate() -> None:
    bundle = build_ocr_line_evidence_bundle(
        ocr_text="יהודה שמולביץ\n313366783\n03/11/2019\n",
    )
    values = {
        str(c.get("value_text") or "")
        for c in bundle.get("candidates") or []
    }
    assert "יהודה שמולביץ" in values
    assert any(c.get("label_text") in (None, "") for c in bundle["candidates"])


def test_boundary_detector_api_intact() -> None:
    assert hasattr(PayslipBoundaryDetector, "detect")
    detector = PayslipBoundaryDetector()
    assert callable(detector.detect)


def _cand(
    cid: str,
    value: str,
    *,
    label: str | None = None,
    page: int = 1,
    relation: str | None = None,
) -> dict[str, Any]:
    row = {
        "candidate_id": cid,
        "label_text": label,
        "value_text": value,
        "page": page,
        "conflict": False,
        "normalized_value": None,
    }
    if relation:
        row["relation"] = relation
    return row


def test_saturated_layout_merge_preserves_ocr_employee_name_candidate() -> None:
    layout = {
        "binder": "evidence_binder_v1",
        "candidate_count": 40,
        "candidates": [
            _cand(f"lay_{i}", f"amt-{i}", label=f"lbl-{i}", relation="association")
            for i in range(40)
        ],
    }
    ocr = build_ocr_line_evidence_bundle(
        ocr_text="יהודה שמולביץ\n10000\n",
    )
    merged = merge_evidence_bundles(layout, ocr, max_candidates=DEFAULT_MERGE_MAX_CANDIDATES)
    values = {str(c.get("value_text") or "") for c in merged.get("candidates") or []}
    assert "יהודה שמולביץ" in values
    assert len(merged["candidates"]) <= DEFAULT_MERGE_MAX_CANDIDATES


def test_merge_never_exceeds_configured_maximum() -> None:
    layout = {
        "candidates": [
            _cand(f"lay_{i}", f"v{i}", label="x", relation="association") for i in range(80)
        ]
    }
    ocr = {"candidates": [_cand(f"ocr_{i}", f"name-{i}") for i in range(20)]}
    merged = merge_evidence_bundles(layout, ocr, max_candidates=DEFAULT_MERGE_MAX_CANDIDATES)
    assert len(merged["candidates"]) <= DEFAULT_MERGE_MAX_CANDIDATES


def test_numeric_ocr_lines_do_not_consume_name_reserve() -> None:
    assert evidence_candidate_priority_tier(_cand("n", "313366783")) != 0
    assert DEFAULT_HIGH_PRIORITY_OCR_RESERVE >= 1
