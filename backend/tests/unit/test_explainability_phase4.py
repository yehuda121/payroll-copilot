"""Phase 4 read-only explainability projection tests."""

from types import SimpleNamespace

from payroll_copilot.application.services.extraction_explainability import (
    attach_field_evidence,
    build_assistant_evidence_context,
    build_field_evidence_map,
    build_validation_explanation,
    build_validation_run_explanation,
)
from payroll_copilot.application.services.employee_ai_context_builder import (
    analyze_employee_context_intent,
)
from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectGuestExtractionUseCase,
    FieldCorrection,
)
from payroll_copilot.infrastructure.config.settings import Settings


def _artifacts(*, conflict: bool = False) -> tuple[dict, dict]:
    structured = {
        "gross_salary": {
            "value": 15230,
            "status": "FOUND",
            "confidence": 0.9,
            "source_text": "15,230",
            "candidate_ids": ["cand_p1_a0"],
        },
        "net_salary": {
            "value": 11842,
            "status": "FOUND",
            "confidence": 0.7,
            "source_text": "11,842",
            "candidate_ids": ["cand_p1_a1"],
        },
    }
    analysis = {
        "pages": [
            {
                "page": 1,
                "rows": [
                    {"id": "p1_r0", "section_id": "p1_s0"},
                    {"id": "p1_r1", "section_id": "p1_s0"},
                ],
                "cells": [
                    {
                        "id": "p1_r0_c0",
                        "text": "Gross Salary",
                        "row_id": "p1_r0",
                        "column_index": 0,
                        "bbox": [10, 10, 80, 12],
                    },
                    {
                        "id": "p1_r0_c1",
                        "text": "15,230",
                        "row_id": "p1_r0",
                        "column_index": 1,
                        "bbox": [120, 10, 50, 12],
                        "source_line_ids": ["p1_b0_l0"],
                    },
                    {
                        "id": "p1_r1_c0",
                        "text": "Net Salary",
                        "row_id": "p1_r1",
                        "column_index": 0,
                        "bbox": [10, 30, 70, 12],
                    },
                    {
                        "id": "p1_r1_c1",
                        "text": "11,842",
                        "row_id": "p1_r1",
                        "column_index": 1,
                        "bbox": [120, 30, 50, 12],
                    },
                    {
                        "id": "p1_r1_c2",
                        "text": "11,800",
                        "row_id": "p1_r1",
                        "column_index": 2,
                        "bbox": [200, 30, 50, 12],
                    },
                ],
            }
        ],
        "associations": [
            {
                "id": "p1_a0",
                "page": 1,
                "label_id": "p1_r0_c0",
                "label_text": "Gross Salary",
                "value_id": "p1_r0_c1",
                "value_text": "15,230",
                "relation": "same_row",
                "confidence": "high",
                "conflict": False,
                "alternatives": [],
            },
            {
                "id": "p1_a1",
                "page": 1,
                "label_id": "p1_r1_c0",
                "label_text": "Net Salary",
                "value_id": "p1_r1_c1",
                "value_text": "11,842",
                "relation": "same_row",
                "confidence": "medium",
                "conflict": conflict,
                "conflict_group": "conflict_0" if conflict else None,
                "alternatives": [
                    {
                        "value_id": "p1_r1_c2",
                        "value_text": "11,800",
                        "relation": "nearest_neighbor",
                        "confidence": "low",
                    }
                ],
            },
        ],
    }
    return structured, analysis


def test_field_evidence_traces_candidate_to_layout() -> None:
    structured, analysis = _artifacts()
    evidence = build_field_evidence_map(structured, analysis)
    gross = evidence["gross_salary"]
    assert gross["candidate_id"] == "cand_p1_a0"
    assert gross["page"] == 1
    assert gross["section"] == "p1_s0"
    assert gross["row"] == "p1_r0"
    assert gross["label"] == "Gross Salary"
    assert gross["value"] == "15,230"
    assert gross["association_strategy"] == "same_row"
    assert gross["bbox"] == [120, 10, 50, 12]


def test_conflict_and_alternatives_are_displayable_without_selection_change() -> None:
    structured, analysis = _artifacts(conflict=True)
    evidence = build_field_evidence_map(structured, analysis)
    net = evidence["net_salary"]
    assert net["conflict"] is True
    assert net["value"] == "11,842"
    assert len(net["alternatives"]) == 1
    assert net["alternatives"][0]["value"] == "11,800"
    assert net["alternatives"][0]["reason"] == "association_engine_alternative"
    assert structured["net_salary"]["value"] == 11842


def test_field_projection_is_additive_and_preserves_existing_contract() -> None:
    structured, analysis = _artifacts()
    original = [
        {
            "key": "gross_salary",
            "value": 15230,
            "confidence": 0.9,
            "source_text": "15,230",
            "status": "FOUND",
        }
    ]
    enriched = attach_field_evidence(
        original, build_field_evidence_map(structured, analysis)
    )
    assert enriched[0]["value"] == original[0]["value"]
    assert enriched[0]["status"] == original[0]["status"]
    assert enriched[0]["evidence_details"]["available"] is True
    assert "evidence_details" not in original[0]


def test_validation_explanation_uses_only_matching_extracted_evidence() -> None:
    structured, analysis = _artifacts()
    evidence = build_field_evidence_map(structured, analysis)
    finding = SimpleNamespace(
        severity="critical",
        message_params={"field": "net_salary"},
        actual_value="11842",
    )
    explanation = build_validation_explanation(
        finding=finding,
        structured_data=structured,
        evidence_by_field=evidence,
    )
    assert explanation["available"] is True
    assert explanation["result"] == "failed"
    assert explanation["candidate_id"] == "cand_p1_a1"
    assert explanation["page"] == 1


def test_validation_and_assistant_explicitly_report_missing_evidence() -> None:
    structured = {"employee_name": {"value": "Dana", "status": "FOUND"}}
    evidence = build_field_evidence_map(structured, {})
    finding = SimpleNamespace(
        severity="warning",
        message_params={"field": "employee_name"},
        actual_value="Dana",
    )
    explanation = build_validation_explanation(
        finding=finding,
        structured_data=structured,
        evidence_by_field=evidence,
    )
    assert explanation == {
        "available": False,
        "result": "uncertain",
        "reason": "extraction_evidence_unavailable",
        "field_key": "employee_name",
    }
    assistant = build_assistant_evidence_context(structured, {})
    assert assistant == [{"field": "employee_name", "evidence_available": False}]


def test_validation_run_summary_explains_pass_without_revalidating() -> None:
    structured, analysis = _artifacts()
    evidence = build_field_evidence_map(structured, analysis)
    fields = [
        {"key": "gross_salary", "value": 15230},
        {"key": "net_salary", "value": 11842},
    ]
    summary = build_validation_run_explanation(
        overall_result="pass",
        fields=fields,
        evidence_by_field=evidence,
    )
    assert summary["result"] == "pass"
    assert summary["evidence_supported_field_count"] == 2
    assert summary["extracted_field_count"] == 2


def test_phase4_feature_flag_defaults_off() -> None:
    assert Settings().layout_explainability_enabled is False
    assert Settings(layout_explainability_enabled=True).layout_explainability_enabled is True


def test_unresolved_candidate_remains_traceable_without_inventing_label() -> None:
    structured = {
        "bonus": {
            "value": 450,
            "status": "FOUND",
            "candidate_ids": ["cand_unresolved_p2_r4_c1"],
        }
    }
    analysis = {
        "pages": [
            {
                "page": 2,
                "rows": [{"id": "p2_r4", "section_id": "p2_s1"}],
                "cells": [
                    {
                        "id": "p2_r4_c1",
                        "text": "450",
                        "row_id": "p2_r4",
                        "column_index": 1,
                        "bbox": [50, 60, 20, 10],
                    }
                ],
            }
        ],
        "associations": [],
        "unresolved_values": ["p2_r4_c1"],
    }
    evidence = build_field_evidence_map(structured, analysis)["bonus"]
    assert evidence["available"] is True
    assert evidence["page"] == 2
    assert evidence["label"] is None
    assert evidence["association_strategy"] == "unresolved_value"


def test_selected_alternative_does_not_list_itself_as_an_alternative() -> None:
    structured, analysis = _artifacts(conflict=True)
    structured["net_salary"]["candidate_ids"] = ["cand_p1_a1_alt0"]
    evidence = build_field_evidence_map(structured, analysis)["net_salary"]
    assert evidence["candidate_id"] == "cand_p1_a1_alt0"
    assert evidence["value"] == "11,800"
    assert [item["candidate_id"] for item in evidence["alternatives"]] == [
        "cand_p1_a1"
    ]
    assert (
        evidence["alternatives"][0]["reason"]
        == "association_engine_primary_not_selected"
    )


def test_human_correction_preserves_original_candidate_trace() -> None:
    corrected = CorrectGuestExtractionUseCase._apply_edit(
        {
            "value": 15230,
            "source_text": "15,230",
            "candidate_ids": ["cand_p1_a0"],
        },
        FieldCorrection(key="gross_salary", value=15200),
    )
    assert corrected.value == 15200
    assert corrected.original_value == 15230
    assert corrected.edited_by_user is True
    assert corrected.candidate_ids == ["cand_p1_a0"]


def test_employee_assistant_routes_evidence_questions_to_payroll_context() -> None:
    intent = analyze_employee_context_intent(
        "Which source page was this employee ID extracted from?"
    )
    assert intent.payroll is True


def test_user_edited_fields_do_not_claim_evidence_supports_current_value() -> None:
    structured, analysis = _artifacts()
    structured["gross_salary"]["edited_by_user"] = True
    structured["gross_salary"]["value"] = 15000
    evidence = build_field_evidence_map(structured, analysis)["gross_salary"]
    assert evidence["available"] is False
    assert evidence["user_edited"] is True
    assert evidence["reason"] == "user_edited"
    assert evidence["candidate_id"] == "cand_p1_a0"
    explanation = build_validation_explanation(
        finding=SimpleNamespace(
            severity="warning",
            message_params={"field": "gross_salary"},
            actual_value="15000",
        ),
        structured_data=structured,
        evidence_by_field={"gross_salary": evidence},
    )
    assert explanation["available"] is False
    assert explanation["reason"] == "user_edited"


def test_validation_does_not_invent_field_links_from_actual_value() -> None:
    structured, analysis = _artifacts()
    evidence = build_field_evidence_map(structured, analysis)
    explanation = build_validation_explanation(
        finding=SimpleNamespace(
            severity="critical",
            message_params={},
            actual_value="15230",
        ),
        structured_data=structured,
        evidence_by_field=evidence,
    )
    assert explanation["available"] is False
    assert explanation["field_key"] is None
    assert explanation["reason"] == "extraction_evidence_unavailable"
