"""Phase 3 evidence-bound mapping — binder, hydration, validation, flags."""

from __future__ import annotations

from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.candidate_evidence_validator import (
    hydrate_and_validate_candidate_fields,
)
from payroll_copilot.application.services.evidence_binder import bind_evidence_candidates
from payroll_copilot.application.services.layout_analysis_pipeline import build_layout_analysis
from payroll_copilot.application.services.parser_semantic import validate_payslip_parser_payload
from payroll_copilot.application.ports.structure_association import LayoutStructureConfig
from payroll_copilot.application.exceptions import PayslipParserSemanticError
from payroll_copilot.infrastructure.ai.payslip_parser_ollama import (
    OllamaPayslipParser,
    build_payslip_instance_template,
)
from payroll_copilot.application.ports.payslip_parser import PAYSLIP_FIELD_KEYS


def _sample_layout_analysis() -> dict:
    snapshot = {
        "pages": [
            {
                "page": 1,
                "width": 400,
                "height": 300,
                "lines": [
                    {
                        "id": "p1_b0_l0",
                        "text": "Gross Salary 15230",
                        "bbox": [40, 40, 220, 14],
                        "reading_index": 0,
                        "word_ids": [],
                    },
                    {
                        "id": "p1_b0_l1",
                        "text": "Net Salary 11842",
                        "bbox": [40, 60, 200, 14],
                        "reading_index": 1,
                        "word_ids": [],
                    },
                ],
                "words": [
                    {
                        "id": "p1_b0_l0_w0",
                        "text": "Gross",
                        "bbox": [40, 40, 50, 14],
                        "line_id": "p1_b0_l0",
                        "word_number": 0,
                    },
                    {
                        "id": "p1_b0_l0_w1",
                        "text": "Salary",
                        "bbox": [95, 40, 50, 14],
                        "line_id": "p1_b0_l0",
                        "word_number": 1,
                    },
                    {
                        "id": "p1_b0_l0_w2",
                        "text": "15230",
                        "bbox": [220, 40, 50, 14],
                        "line_id": "p1_b0_l0",
                        "word_number": 2,
                    },
                    {
                        "id": "p1_b0_l1_w0",
                        "text": "Net",
                        "bbox": [40, 60, 30, 14],
                        "line_id": "p1_b0_l1",
                        "word_number": 0,
                    },
                    {
                        "id": "p1_b0_l1_w1",
                        "text": "Salary",
                        "bbox": [75, 60, 50, 14],
                        "line_id": "p1_b0_l1",
                        "word_number": 1,
                    },
                    {
                        "id": "p1_b0_l1_w2",
                        "text": "11842",
                        "bbox": [220, 60, 50, 14],
                        "line_id": "p1_b0_l1",
                        "word_number": 2,
                    },
                ],
                "blocks": [],
            }
        ]
    }
    return build_layout_analysis(snapshot, config=LayoutStructureConfig(enabled=True))


def test_evidence_binder_creates_candidate_refs() -> None:
    analysis = _sample_layout_analysis()
    bundle = bind_evidence_candidates(analysis)
    assert bundle["candidate_count"] >= 2
    assert bundle["llm_candidates"]
    first = bundle["llm_candidates"][0]
    assert first["candidate_id"].startswith("cand_")
    assert "label" in first and "value" in first
    assert first["candidate_id"] in bundle["candidate_index"]


def test_hydrate_rejects_unknown_candidate() -> None:
    analysis = _sample_layout_analysis()
    bundle = bind_evidence_candidates(analysis)
    known = next(iter(bundle["candidate_index"]))
    parsed = StructuredPayslipParse(
        gross_salary=ExtractedField(
            value=99999,
            status=FieldExtractionStatus.FOUND,
            candidate_ids=["cand_does_not_exist"],
        ),
        net_salary=ExtractedField(
            value=None,
            status=FieldExtractionStatus.FOUND,
            candidate_ids=[known],
        ),
    )
    result = hydrate_and_validate_candidate_fields(
        parsed, candidate_index=bundle["candidate_index"]
    )
    assert result.gross_salary.status == FieldExtractionStatus.MISSING
    assert result.gross_salary.value is None
    assert any("unknown_candidate_id" in w for w in result.gross_salary.warnings)
    assert result.net_salary.status in {FieldExtractionStatus.FOUND, FieldExtractionStatus.UNCERTAIN}
    assert result.net_salary.value not in (None, "")
    assert known in result.net_salary.candidate_ids


def test_hydrate_rejects_hallucinated_value_keeps_candidate_text() -> None:
    analysis = _sample_layout_analysis()
    bundle = bind_evidence_candidates(analysis)
    # Pick a numeric candidate.
    cand_id = None
    cand = None
    for item in bundle["candidates"]:
        if str(item.get("value_text", "")).isdigit():
            cand_id = item["candidate_id"]
            cand = item
            break
    assert cand_id and cand
    parsed = StructuredPayslipParse(
        gross_salary=ExtractedField(
            value=999999,
            status=FieldExtractionStatus.FOUND,
            candidate_ids=[cand_id],
        )
    )
    result = hydrate_and_validate_candidate_fields(
        parsed, candidate_index=bundle["candidate_index"]
    )
    assert result.gross_salary.value != 999999
    assert "hallucinated_value_rejected" in result.gross_salary.warnings
    assert result.gross_salary.source_text == cand["value_text"]
    assert result.gross_salary.candidate_ids == [cand_id]


def test_missing_candidate_ids_cleared() -> None:
    parsed = StructuredPayslipParse(
        employee_name=ExtractedField(
            value="Invented Name",
            status=FieldExtractionStatus.FOUND,
            candidate_ids=[],
        )
    )
    result = hydrate_and_validate_candidate_fields(parsed, candidate_index={})
    assert result.employee_name.status == FieldExtractionStatus.MISSING
    assert result.employee_name.value is None


def test_semantic_validation_rejects_invalid_candidate_refs() -> None:
    payload = {key: {"value": None, "candidate_ids": [], "status": "MISSING"} for key in PAYSLIP_FIELD_KEYS}
    payload["gross_salary"] = {
        "value": 100,
        "candidate_ids": ["cand_fake"],
        "status": "FOUND",
    }
    payload["additional_fields"] = {}
    payload["language"] = "he"
    try:
        validate_payslip_parser_payload(
            payload,
            ocr_text="x",
            evidence_bound=True,
            known_candidate_ids={"cand_real"},
        )
        assert False, "expected semantic error"
    except PayslipParserSemanticError as exc:
        assert exc.category == "invalid_candidate_ids"


def test_evidence_bound_prompt_uses_candidates_not_raw_ocr() -> None:
    parser = OllamaPayslipParser(
        model_provider=object(),
        model="test",
        layout_enabled=True,
    )
    prompt = parser._build_user_prompt(
        ocr_text="THIS RAW OCR SHOULD NOT BE THE PRIMARY SIGNAL",
        language="he",
        pages_text=["RAW PAGE"],
        layout_context={"pages": []},
        retry_hint=None,
        evidence_candidates={
            "llm_candidates": [
                {
                    "candidate_id": "cand_p1_a0",
                    "label": "Gross Salary",
                    "value": "15230",
                    "page": 1,
                    "relation": "same_row",
                    "confidence": "high",
                    "conflict": False,
                }
            ]
        },
    )
    assert "EVIDENCE-BOUND PAYROLL MAPPING" in prompt
    assert "cand_p1_a0" in prompt
    assert "CANDIDATES" in prompt
    assert "THIS RAW OCR SHOULD NOT BE THE PRIMARY SIGNAL" not in prompt
    assert "DOCUMENT TEXT:" not in prompt


def test_feature_flag_off_keeps_legacy_prompt() -> None:
    parser = OllamaPayslipParser(
        model_provider=object(),
        model="test",
        layout_enabled=True,
    )
    prompt = parser._build_user_prompt(
        ocr_text="legacy document text",
        language="en",
        pages_text=None,
        layout_context=None,
        retry_hint=None,
        evidence_candidates=None,
    )
    assert "DOCUMENT TEXT:" in prompt
    assert "legacy document text" in prompt
    assert "EVIDENCE-BOUND" not in prompt


def test_evidence_bound_template_includes_candidate_ids() -> None:
    template = build_payslip_instance_template(evidence_bound=True)
    assert "candidate_ids" in template["gross_salary"]
    assert template["gross_salary"]["status"] == "MISSING"


def test_empty_analysis_binder_returns_empty_candidates() -> None:
    bundle = bind_evidence_candidates({})
    assert bundle["candidate_count"] == 0
    assert bundle["llm_candidates"] == []
