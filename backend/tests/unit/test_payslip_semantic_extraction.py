"""Unit tests for payslip semantic_v1 extraction (grounding + catalog + propagation)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from payroll_copilot.application.services.dynamic_document import (
    map_dynamic_entries_to_structured,
    project_structured_from_entries,
    resolve_canonical_key,
)
from payroll_copilot.application.services.ocr_line_evidence import (
    build_ocr_line_evidence_bundle,
)
from payroll_copilot.application.services.payslip_semantic_catalog import (
    EXTRACTOR_VERSION,
    build_payslip_field_catalog,
    catalog_as_prompt_rows,
)
from payroll_copilot.application.services.payslip_semantic_extractor import (
    PayslipSemanticExtractor,
    ground_semantic_field,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import _fields_from_entries


def _cand(cid: str, value: str, *, label: str | None = None, page: int = 1) -> dict[str, Any]:
    return {
        "candidate_id": cid,
        "label_text": label,
        "value_text": value,
        "page": page,
        "conflict": False,
        "normalized_value": None,
        "source_line_ids": [cid],
        "bbox": None,
    }


def test_field_catalog_includes_required_concepts() -> None:
    catalog = build_payslip_field_catalog()
    keys = {row.canonical_key for row in catalog}
    assert "employee_name" in keys
    assert "national_id" in keys
    assert "pay_period" in keys
    assert "gross_salary" in keys
    assert "net_salary" in keys
    rows = catalog_as_prompt_rows(catalog)
    employee = next(r for r in rows if r["canonical_key"] == "employee_name")
    assert "employee" in employee["meaning"].casefold()
    assert employee["priority"] == "required"


def test_unlabeled_employee_name_grounds_to_canonical() -> None:
    index = {
        "c_12": _cand("c_12", "ישראל ישראלי"),
        "c_13": _cand("c_13", "123456782"),
    }
    consumed: dict[str, str] = {}
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="ישראל ישראלי",
        status="FOUND",
        confidence=0.94,
        evidence_ids=["c_12"],
        label_as_printed=None,
        candidate_index=index,
        consumed=consumed,
    )
    assert rejected is False
    assert entry is not None
    assert entry.key == "employee_name"
    assert entry.value == "ישראל ישראלי"
    assert entry.source == EXTRACTOR_VERSION
    assert consumed["c_12"] == "employee_name"
    assert not any(w.startswith("ungrounded") for w in warnings)


def test_national_id_vs_employee_number_consumed_evidence() -> None:
    index = {
        "c_nid": _cand("c_nid", "123456782", label=None),
        "c_num": _cand("c_num", "EMP-42", label="מספר עובד"),
    }
    consumed: dict[str, str] = {}
    nid, _, rej_nid = ground_semantic_field(
        canonical_key="national_id",
        model_value="123456782",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_nid"],
        label_as_printed=None,
        candidate_index=index,
        consumed=consumed,
    )
    assert rej_nid is False and nid is not None and nid.key == "national_id"

    # Same candidate must not also become employee_number.
    dup, warnings, rejected = ground_semantic_field(
        canonical_key="employee_number",
        model_value="123456782",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_nid"],
        label_as_printed=None,
        candidate_index=index,
        consumed=consumed,
    )
    assert rejected is True
    assert dup is None
    assert any("consumed_evidence_conflict" in w for w in warnings)

    num, _, rej_num = ground_semantic_field(
        canonical_key="employee_number",
        model_value="EMP-42",
        status="FOUND",
        confidence=0.88,
        evidence_ids=["c_num"],
        label_as_printed="מספר עובד",
        candidate_index=index,
        consumed=consumed,
    )
    assert rej_num is False and num is not None and num.value == "EMP-42"


def test_invalid_evidence_id_rejected() -> None:
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="Ghost",
        status="FOUND",
        confidence=0.99,
        evidence_ids=["does_not_exist"],
        label_as_printed=None,
        candidate_index={},
        consumed={},
    )
    assert rejected is True
    assert entry is None
    assert any("unknown_evidence_id" in w or "ungrounded" in w for w in warnings)


def test_unsupported_model_value_rejected_not_replaced_with_value_text() -> None:
    """Unsupported model values must not be silently replaced with value_text."""
    index = {"c1": _cand("c1", "ישראל ישראלי")}
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="Profile Name From HR",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c1"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is True
    assert entry is None
    assert any("unsupported_model_value_rejected" in w for w in warnings)


def test_association_candidate_label_supports_employee_name_value_supports_national_id() -> None:
    """One label/value association candidate can ground two different concepts."""
    index = {
        "cand_12": _cand("cand_12", "123456789", label="ישראל ישראלי"),
    }
    consumed: dict[str, str] = {}

    name_entry, name_warnings, name_rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="ישראל ישראלי",
        status="FOUND",
        confidence=0.94,
        evidence_ids=["cand_12"],
        label_as_printed=None,
        candidate_index=index,
        consumed=consumed,
    )
    assert name_rejected is False
    assert name_entry is not None
    assert name_entry.key == "employee_name"
    assert name_entry.value == "ישראל ישראלי"
    assert name_entry.value != "123456789"
    assert not any("unsupported" in w for w in name_warnings)

    # employee_name vs national_id are not mutually exclusive — same candidate OK.
    nid_entry, nid_warnings, nid_rejected = ground_semantic_field(
        canonical_key="national_id",
        model_value="123456789",
        status="FOUND",
        confidence=0.91,
        evidence_ids=["cand_12"],
        label_as_printed=None,
        candidate_index=index,
        consumed=consumed,
    )
    assert nid_rejected is False
    assert nid_entry is not None
    assert nid_entry.key == "national_id"
    assert str(nid_entry.value) == "123456789"
    assert not any("unsupported" in w for w in nid_warnings)


def test_standard_label_value_candidate_grounds_national_id() -> None:
    index = {"c_nid": _cand("c_nid", "123456789", label="ת.ז.")}
    entry, _, rejected = ground_semantic_field(
        canonical_key="national_id",
        model_value="123456789",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_nid"],
        label_as_printed="ת.ז.",
        candidate_index=index,
        consumed={},
    )
    assert rejected is False
    assert entry is not None
    assert str(entry.value) == "123456789"


def test_unsupported_name_against_tz_label_value_not_replaced_with_nid() -> None:
    index = {"c_nid": _cand("c_nid", "123456789", label="ת.ז.")}
    entry, warnings, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="John Smith",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c_nid"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is True
    assert entry is None
    assert any("unsupported_model_value_rejected" in w for w in warnings)


def test_model_value_matching_value_text_unchanged() -> None:
    index = {"c1": _cand("c1", "ישראל ישראלי")}
    entry, _, rejected = ground_semantic_field(
        canonical_key="employee_name",
        model_value="ישראל ישראלי",
        status="FOUND",
        confidence=0.9,
        evidence_ids=["c1"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is False
    assert entry is not None
    assert entry.value == "ישראל ישראלי"


def test_invalid_printed_national_id_still_extracted() -> None:
    """Checksum-invalid IDs must still extract; SANITY is downstream."""
    bad_id = "123456789"  # often checksum-invalid; still printed
    index = {"c_nid": _cand("c_nid", bad_id)}
    entry, _, rejected = ground_semantic_field(
        canonical_key="national_id",
        model_value=bad_id,
        status="FOUND",
        confidence=0.85,
        evidence_ids=["c_nid"],
        label_as_printed=None,
        candidate_index=index,
        consumed={},
    )
    assert rejected is False
    assert entry is not None
    assert str(entry.value) == bad_id


def test_not_found_does_not_fabricate() -> None:
    entry, _, rejected = ground_semantic_field(
        canonical_key="employment_scope",
        model_value=None,
        status="NOT_FOUND",
        confidence=None,
        evidence_ids=[],
        label_as_printed=None,
        candidate_index={},
        consumed={},
    )
    assert entry is None
    assert rejected is False


def test_canonical_propagation_through_projection_and_digital_fields() -> None:
    index = {
        "c_name": _cand("c_name", "ישראל ישראלי"),
        "c_nid": _cand("c_nid", "123456782"),
        "c_period": _cand("c_period", "05/2026"),
        "c_gross": _cand("c_gross", "15000"),
        "c_net": _cand("c_net", "11200"),
    }
    consumed: dict[str, str] = {}
    entries = []
    for key, cid, value in [
        ("employee_name", "c_name", "ישראל ישראלי"),
        ("national_id", "c_nid", "123456782"),
        ("pay_period", "c_period", "05/2026"),
        ("gross_salary", "c_gross", "15000"),
        ("net_salary", "c_net", "11200"),
    ]:
        entry, _, rejected = ground_semantic_field(
            canonical_key=key,
            model_value=value,
            status="FOUND",
            confidence=0.9,
            evidence_ids=[cid],
            label_as_printed=None,
            candidate_index=index,
            consumed=consumed,
        )
        assert rejected is False and entry is not None
        entries.append(entry)

    # Synonym map not required — keys are already canonical.
    assert resolve_canonical_key("employee_name") == "employee_name"
    structured, _ = project_structured_from_entries(entries)
    assert structured["employee_name"]["value"] == "ישראל ישראלי"
    nid_payload = structured.get("national_id") or structured["additional_fields"]["national_id"]
    assert nid_payload["value"] == "123456782"
    assert structured["pay_period"]["value"] == "05/2026"
    assert structured["gross_salary"]["value"] in {15000, "15000", 15000.0}
    assert structured["net_salary"]["value"] in {11200, "11200", 11200.0}

    views = _fields_from_entries(entries)
    by_key = {v.key: v for v in views}
    assert by_key["employee_name"].status == "FOUND"
    assert by_key["employee_name"].value == "ישראל ישראלי"
    assert by_key["national_id"].value == "123456782"
    assert by_key["pay_period"].value == "05/2026"


def test_additional_unknown_component_preserved() -> None:
    extractor = PayslipSemanticExtractor.__new__(PayslipSemanticExtractor)
    index = {"c_44": _cand("c_44", "350.00", label="דמי הבראה")}
    payload = {
        "extractor_version": EXTRACTOR_VERSION,
        "fields": [],
        "additional_fields": [
            {
                "label": "דמי הבראה",
                "value": "350.00",
                "confidence": 0.87,
                "evidence_ids": ["c_44"],
            }
        ],
        "not_found": ["employment_scope"],
    }
    result = extractor._materialize(payload, candidate_index=index)
    assert any(e.key == "דמי הבראה" and str(e.value) in {"350.00", "350", "350.0"} for e in result.entries)
    assert "employment_scope" in result.not_found
    mapped, _ = map_dynamic_entries_to_structured(result.entries)
    assert "דמי הבראה" in mapped["additional_fields"] or any(
        "הבראה" in k for k in mapped["additional_fields"]
    )


def test_ocr_line_candidates_support_unlabeled_header() -> None:
    bundle = build_ocr_line_evidence_bundle(
        ocr_text="ישראל ישראלי\n123456782\nמחלקת פיתוח\n05/2026",
    )
    values = {c["value_text"] for c in bundle["candidates"]}
    assert "ישראל ישראלי" in values
    assert "123456782" in values
    assert "05/2026" in values


@pytest.mark.asyncio
async def test_semantic_extractor_materializes_llm_json() -> None:
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value=MagicMock(
            content="""
            {
              "extractor_version": "semantic_v1",
              "fields": [
                {
                  "canonical_key": "employee_name",
                  "value": "ישראל ישראלי",
                  "status": "FOUND",
                  "confidence": 0.94,
                  "evidence_ids": ["ocr_p1_t0"],
                  "label_as_printed": null
                },
                {
                  "canonical_key": "national_id",
                  "value": "123456782",
                  "status": "FOUND",
                  "confidence": 0.91,
                  "evidence_ids": ["ocr_p1_t1"],
                  "label_as_printed": null
                },
                {
                  "canonical_key": "employer_name",
                  "value": "חברת דוגמה בע״מ",
                  "status": "FOUND",
                  "confidence": 0.9,
                  "evidence_ids": ["ocr_p1_t4"],
                  "label_as_printed": null
                },
                {
                  "canonical_key": "pay_period",
                  "value": "05/2026",
                  "status": "FOUND",
                  "confidence": 0.9,
                  "evidence_ids": ["ocr_p1_t3"],
                  "label_as_printed": null
                },
                {
                  "canonical_key": "gross_salary",
                  "value": "15000",
                  "status": "FOUND",
                  "confidence": 0.9,
                  "evidence_ids": ["ocr_p1_t5"],
                  "label_as_printed": "ברוטו"
                },
                {
                  "canonical_key": "net_salary",
                  "value": "11200",
                  "status": "FOUND",
                  "confidence": 0.9,
                  "evidence_ids": ["ocr_p1_t6"],
                  "label_as_printed": "נטו"
                }
              ],
              "additional_fields": [
                {
                  "label": "דמי הבראה",
                  "value": "350.00",
                  "confidence": 0.87,
                  "evidence_ids": ["ocr_p1_t7"]
                }
              ],
              "not_found": ["employment_scope"]
            }
            """,
            model="test-model",
        )
    )
    extractor = PayslipSemanticExtractor(model_provider=provider, model="test-model")
    ocr = (
        "ישראל ישראלי\n"
        "123456782\n"
        "מחלקת פיתוח\n"
        "05/2026\n"
        "חברת דוגמה בע״מ\n"
        "15000\n"
        "11200\n"
        "350.00\n"
    )
    bundle = build_ocr_line_evidence_bundle(ocr_text=ocr)
    result = await extractor.extract(
        ocr_text=ocr,
        language="he",
        evidence_bundle=bundle,
    )
    by_key = {e.key: e for e in result.entries}
    assert by_key["employee_name"].value == "ישראל ישראלי"
    assert by_key["national_id"].value == "123456782"
    assert by_key["pay_period"].value == "05/2026"
    assert by_key["employer_name"].value == "חברת דוגמה בע״מ"
    assert result.extractor_version == EXTRACTOR_VERSION
    assert result.grounded_count >= 4

    structured, _ = project_structured_from_entries(result.entries)
    assert structured["employee_name"]["value"] == "ישראל ישראלי"
    views = _fields_from_entries(result.entries)
    assert any(v.key == "employee_name" and v.status == "FOUND" for v in views)
