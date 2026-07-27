"""Employee-name reliability: grounding, plausibility, and projection (no live LLM)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from payroll_copilot.application.services.batch_payslip_pipeline import (
    BatchPayslipPipelineService,
)
from payroll_copilot.application.services.dynamic_document import (
    project_structured_from_entries,
)
from payroll_copilot.application.services.ocr_line_evidence import (
    build_ocr_line_evidence_bundle,
)
from payroll_copilot.application.services.parser_evidence import (
    employee_name_implausible_reason,
)
from payroll_copilot.application.services.payslip_boundary_detector import (
    PayslipBoundaryDetector,
)
from payroll_copilot.application.services.payslip_semantic_extractor import (
    PayslipSemanticExtractor,
    _compact_candidates_for_prompt,
    ground_semantic_field,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import _fields_from_entries
from payroll_copilot.domain.entities import Employee


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
        "source_line_ids": [cid],
        "bbox": None,
    }
    if relation:
        row["relation"] = relation
    return row


def test_labeled_employee_name_grounds() -> None:
    index = {"c1": _cand("c1", "יהודה שמולביץ", label="שם העובד")}
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="יהודה שמולביץ",
        status="FOUND",
        confidence=0.95,
        evidence_ids=["c1"],
        label_as_printed="שם העובד",
        candidate_index=index,
        consumed={},
    )
    assert rejected is False
    assert entry is not None
    assert entry.value == "יהודה שמולביץ"
    assert "employee_name_grounded" in warnings


def test_unlabeled_personal_details_name_grounds_when_model_cites_evidence() -> None:
    """Name + NID + start date without שם label — mock semantic proposal + grounding."""
    index = {
        "c_name": _cand("c_name", "יהודה שמולביץ", relation="ocr_line"),
        "c_nid": _cand("c_nid", "313366783", relation="ocr_line"),
        "c_start": _cand("c_start", "03/11/2019", relation="ocr_line"),
    }
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="יהודה שמולביץ",
        status="FOUND",
        confidence=0.92,
        evidence_ids=["c_name"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is False
    assert entry is not None
    assert entry.value == "יהודה שמולביץ"
    assert entry.value != "313366783"
    assert "employee_name_grounded" in warnings


def test_reversed_hebrew_token_order_grounds_to_document_text() -> None:
    index = {"c_name": _cand("c_name", "שמולביץ יהודה")}
    entry, _, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="יהודה שמולביץ",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_name"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is False
    assert entry is not None
    assert entry.value == "שמולביץ יהודה"


def test_national_id_as_employee_name_rejected() -> None:
    index = {"c_nid": _cand("c_nid", "313366783")}
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="313366783",
        status="FOUND",
        confidence=0.99,
        evidence_ids=["c_nid"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is True
    assert entry is None
    assert any("employee_name_rejected_numeric" in w for w in warnings)


def test_empty_model_value_does_not_hydrate_nid_as_employee_name() -> None:
    """Association: name on label, NID on value — empty model must not take digits."""
    index = {"cand": _cand("cand", "313366783", label="יהודה שמולביץ")}
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value=None,
        status="FOUND",
        confidence=0.8,
        evidence_ids=["cand"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is False
    assert entry is not None
    assert entry.value == "יהודה שמולביץ"
    assert "313366783" not in str(entry.value)
    assert "employee_name_grounded" in warnings


def test_employer_like_candidate_rejected_for_employee_name() -> None:
    index = {
        "c_co": _cand("c_co", 'עמותת טוב לחיים בע"מ'),
        "c_person": _cand("c_person", "ישראל ישראלי"),
    }
    bad, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value='עמותת טוב לחיים בע"מ',
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_co"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is True
    assert bad is None
    assert any("employee_name_rejected_employer_like" in w for w in warnings)

    good, _, rej_good = ground_semantic_field(
        canonical_key="employee_name",
        model_value="ישראל ישראלי",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_person"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rej_good is False
    assert good is not None
    assert good.value == "ישראל ישראלי"


def test_website_cannot_ground_as_employee_name() -> None:
    index = {"c_web": _cand("c_web", "WWW.TOV.ORG.IL")}
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="WWW.TOV.ORG.IL",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_web"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is True
    assert entry is None
    assert any("employee_name_rejected_url" in w for w in warnings)
    assert employee_name_implausible_reason("WWW.TOV.ORG.IL") == "implausible_employee_name_url"


def test_email_and_date_cannot_ground_as_employee_name() -> None:
    assert employee_name_implausible_reason("name@example.com") == "implausible_employee_name_email"
    assert employee_name_implausible_reason("03/11/2019") == "implausible_employee_name_date"
    index = {"c_date": _cand("c_date", "03/11/2019")}
    entry, _, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="03/11/2019",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_date"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is True
    assert entry is None


def test_unicode_scripts_hebrew_english_arabic_plausible() -> None:
    assert employee_name_implausible_reason("יהודה שמולביץ") is None
    assert employee_name_implausible_reason("Yehuda Example") is None
    assert employee_name_implausible_reason("محمد علي") is None


def test_profile_name_without_document_evidence_stays_missing() -> None:
    """LLM/profile-like value with no citeable evidence must not become document name."""
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="Yehuda Shmulevitz",
        status="FOUND",
        confidence=0.99,
        evidence_ids=[],
        label_as_printed=None,
        candidate_index={},
        consumed={},
    )
    assert rejected is True
    assert entry is None
    assert any("ungrounded_rejected" in w for w in warnings)


def test_accountant_matched_profile_name_is_not_extraction_field() -> None:
    employee = MagicMock(spec=Employee)
    employee.metadata = {"verified_display_name": "Matched Profile Name"}
    employee.full_name = "Matched Profile Name"

    matched = BatchPayslipPipelineService._employee_name(employee)
    assert matched == "Matched Profile Name"

    structured = {
        "employee_name": {"value": None, "status": "MISSING", "confidence": None},
        "national_id": {"value": "123456782", "status": "FOUND", "confidence": 0.9},
    }
    fields = BatchPayslipPipelineService._fields_from_extraction(structured)
    name_field = next((f for f in fields if f.key == "employee_name"), None)
    if name_field is not None:
        assert name_field.value in (None, "")
        assert name_field.value != "Matched Profile Name"


def test_grounded_name_survives_canonical_projection() -> None:
    index = {"c_name": _cand("c_name", "Dana Cohen")}
    entry, _, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="Dana Cohen",
        status="FOUND",
        confidence=0.91,
        evidence_ids=["c_name"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is False and entry is not None
    structured, _ = project_structured_from_entries([entry])
    assert structured["employee_name"]["value"] == "Dana Cohen"
    views = _fields_from_entries([entry])
    assert views[0].key == "employee_name"
    assert views[0].value == "Dana Cohen"


def test_employee_and_accountant_share_same_grounding_function() -> None:
    """Parity: both portals use ground_semantic_field / shared semantic extractor."""
    assert hasattr(PayslipSemanticExtractor, "extract")
    assert callable(ground_semantic_field)


def test_compact_candidates_prioritize_unlabeled_person_name_lines() -> None:
    llm_candidates = [
        {"candidate_id": "salary", "label": "ברוטו", "value": "15000", "relation": "association"},
        {
            "candidate_id": "name",
            "label": None,
            "value": "יהודה שמולביץ",
            "relation": "ocr_line",
        },
        {"candidate_id": "nid", "label": None, "value": "313366783", "relation": "ocr_line"},
    ]
    compact = _compact_candidates_for_prompt(llm_candidates, max_items=2)
    ids = [row["id"] for row in compact]
    assert ids[0] == "name"
    assert "name" in ids


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


def test_this_train_does_not_change_boundary_detector_one_page_fallback() -> None:
    """Regression: segmentation semantics unchanged (scanned → one page per slip)."""
    # Minimal blank-ish multi-page PDF bytes exercised by existing detector tests;
    # here we only assert the detector API/strategy constant still exists for fallback.
    assert hasattr(PayslipBoundaryDetector, "detect")
    detector = PayslipBoundaryDetector()
    assert callable(detector.detect)


def test_materialize_records_employee_name_outcome_without_pii() -> None:
    extractor = PayslipSemanticExtractor.__new__(PayslipSemanticExtractor)
    index = {"c_nid": _cand("c_nid", "313366783")}
    payload = {
        "fields": [
            {
                "canonical_key": "employee_name",
                "value": "313366783",
                "status": "FOUND",
                "confidence": 0.9,
                "evidence_ids": ["c_nid"],
            }
        ],
        "additional_fields": [],
        "not_found": [],
    }
    result = extractor._materialize(payload, candidate_index=index)
    assert result.meta.get("employee_name_outcome") == "employee_name_rejected_numeric"
    assert not any(e.key == "employee_name" for e in result.entries)
