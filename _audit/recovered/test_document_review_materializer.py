"""Document review materializer — curated review surface after extraction."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from payroll_copilot.application.ports.payslip_parser import (
    ExtractedField,
    FieldExtractionStatus,
    StructuredPayslipParse,
)
from payroll_copilot.application.services.document_review_materializer import (
    REVIEW_MATERIALIZED_META_KEY,
    materialize_review_document,
)
from payroll_copilot.application.services.review_dto import review_lines_from_document
from payroll_copilot.domain.document_model import (
    DocumentEvidenceRef,
    DocumentInstance,
    DocumentLayoutRef,
    DocumentPage,
    DocumentSlot,
)


def _slot(
    *,
    slot_id: str,
    label: str | None = None,
    value: object = None,
    canonical_key: str | None = None,
    source: str | None = None,
    confidence: str | None = "high",
    conflict: bool = False,
    candidate_ids: list[str] | None = None,
    page: int = 1,
    reading_index: int | None = None,
) -> DocumentSlot:
    meta: dict = {}
    if canonical_key:
        meta["canonical_key"] = canonical_key
    if source:
        meta["source"] = source
    return DocumentSlot(
        id=slot_id,
        kind="field",
        label=label,
        value=value,
        confidence=confidence,
        layout=DocumentLayoutRef(page=page, reading_index=reading_index, bbox=[0, float(reading_index or 0), 10, 10]),
        evidence=DocumentEvidenceRef(
            candidate_ids=list(candidate_ids or []),
            conflict=conflict,
        ),
        metadata=meta,
    )


def _doc(*slots: DocumentSlot) -> DocumentInstance:
    return DocumentInstance(
        pages=[DocumentPage(page=1)],
        slots=list(slots),
        slot_count=len(slots),
        cell_count=0,
        layout_metadata={"seed": True},
    )


def test_idempotent_and_stable_ids() -> None:
    doc = _doc(
        _slot(slot_id="a", label="Gross", value="1", canonical_key="gross_salary", candidate_ids=["c1"]),
        _slot(slot_id="b", label="Gross", value="2", canonical_key="gross_salary", candidate_ids=["c2"], conflict=True),
        _slot(slot_id="c", label="Custom Bonus", value="50", candidate_ids=["c3"]),
    )
    once = materialize_review_document(doc)
    twice = materialize_review_document(once)
    assert [s.id for s in once.slots] == [s.id for s in twice.slots]
    assert [s.value for s in once.slots] == [s.value for s in twice.slots]
    assert once.layout_metadata.get(REVIEW_MATERIALIZED_META_KEY) is True
    assert twice.to_dict()["slots"] == once.to_dict()["slots"]


def test_deterministic_ordering_by_reading_index() -> None:
    doc = _doc(
        _slot(slot_id="late", label="Net", value="9", canonical_key="net_salary", reading_index=20),
        _slot(slot_id="early", label="Gross", value="1", canonical_key="gross_salary", reading_index=1),
        _slot(slot_id="mid", label="Tax", value="2", canonical_key="income_tax", reading_index=5),
    )
    out = materialize_review_document(doc)
    assert [s.id for s in out.slots] == ["early", "mid", "late"]


def test_duplicate_canonical_removal_keeps_best_evidence() -> None:
    doc = _doc(
        _slot(
            slot_id="weak",
            label="ID",
            value="111",
            canonical_key="employee_id",
            confidence="low",
            conflict=True,
            candidate_ids=["c_weak"],
            reading_index=0,
        ),
        _slot(
            slot_id="strong",
            label="ID",
            value="999",
            canonical_key="employee_id",
            confidence="high",
            conflict=False,
            candidate_ids=["c_strong"],
            reading_index=1,
        ),
        _slot(
            slot_id="also",
            label="ID",
            value="888",
            canonical_key="employee_id",
            confidence="medium",
            candidate_ids=["c_also"],
            reading_index=2,
        ),
    )
    out = materialize_review_document(doc)
    keys = [
        (s.metadata or {}).get("canonical_key")
        for s in out.slots
        if (s.metadata or {}).get("canonical_key")
    ]
    assert keys.count("employee_id") == 1
    winner = next(s for s in out.slots if (s.metadata or {}).get("canonical_key") == "employee_id")
    assert winner.id == "strong"
    assert winner.value == "999"
    assert winner.evidence.candidate_ids == ["c_strong"]


def test_preserves_evidence_and_candidate_ids() -> None:
    doc = _doc(
        _slot(
            slot_id="g1",
            label="Gross",
            value="100",
            canonical_key="gross_salary",
            candidate_ids=["cand_42", "cand_43"],
        )
    )
    out = materialize_review_document(doc)
    assert out.slots[0].evidence.candidate_ids == ["cand_42", "cand_43"]


def test_preserves_source_user_even_when_label_duplicates() -> None:
    doc = _doc(
        _slot(slot_id="sys", label="Note", value="A", reading_index=0),
        _slot(slot_id="user_1", label="Note", value="B", source="user", reading_index=1),
        _slot(slot_id="user_2", label="Note", value="C", source="user", reading_index=2),
    )
    out = materialize_review_document(doc)
    ids = {s.id for s in out.slots}
    assert "user_1" in ids and "user_2" in ids
    # System duplicate label collapses to one; users remain.
    assert sum(1 for s in out.slots if (s.label or "") == "Note") >= 3


def test_preserves_unique_non_canonical_fields() -> None:
    doc = _doc(
        _slot(slot_id="e1", label="Employer Name", value="Acme Ltd", reading_index=0),
        _slot(slot_id="e2", label="Employer Name", value="Acme Wrong", reading_index=1, conflict=True),
        _slot(slot_id="c1", label="Custom Allowance", value="200", reading_index=2),
        _slot(slot_id="g1", label="Gross", value="1000", canonical_key="gross_salary", reading_index=3),
    )
    out = materialize_review_document(doc)
    labels = [s.label for s in out.slots]
    assert labels.count("Employer Name") == 1
    assert "Custom Allowance" in labels
    assert any((s.metadata or {}).get("canonical_key") == "gross_salary" for s in out.slots)
    employer = next(s for s in out.slots if s.label == "Employer Name")
    assert employer.value == "Acme Ltd"


def test_preserves_layout_structure() -> None:
    doc = _doc(_slot(slot_id="a", label="X", value="1"))
    doc.pages = [DocumentPage(page=1), DocumentPage(page=2)]
    doc.layout_metadata = {"keep": "me"}
    out = materialize_review_document(doc)
    assert len(out.pages) == 2
    assert out.layout_metadata.get("keep") == "me"
    assert out.layout_metadata.get(REVIEW_MATERIALIZED_META_KEY) is True


def test_review_dto_projects_curated_slots_only() -> None:
    polluted = _doc(
        *[_slot(slot_id=f"d{i}", label="Gross", value=str(i), canonical_key="gross_salary", reading_index=i) for i in range(5)],
        _slot(slot_id="extra", label="Department", value="Ops", reading_index=10),
    )
    curated = materialize_review_document(polluted)
    lines = review_lines_from_document(curated)
    assert len(lines) == 2
    assert len(review_lines_from_document(polluted)) == 6


def test_drops_internal_machine_labels_without_value() -> None:
    doc = _doc(
        _slot(slot_id="s1", label="slot_cand_x", value=None),
        _slot(slot_id="s2", label="candidate_y", value=None),
        _slot(slot_id="ok", label="Net Pay", value="10"),
    )
    out = materialize_review_document(doc)
    assert [s.id for s in out.slots] == ["ok"]


@pytest.mark.asyncio
async def test_shared_pipeline_materializes_before_review_dto() -> None:
    """Guest/Employee/Batch share _run_shared_document_pipeline — materialize once."""
    from payroll_copilot.application.use_cases.extract_guest_payslip import (
        ExtractGuestPayslipUseCase,
    )

    polluted = _doc(
        _slot(slot_id="a", label="Gross", value="1", canonical_key="gross_salary", candidate_ids=["c1"], reading_index=0),
        _slot(slot_id="b", label="Gross", value="2", canonical_key="gross_salary", candidate_ids=["c2"], conflict=True, reading_index=1),
        _slot(slot_id="c", label="Employer", value="Acme", reading_index=2),
    )

    class _FakeOutcome:
        used_template = True
        document = polluted
        structured = StructuredPayslipParse(
            gross_salary=ExtractedField(value="1", status=FieldExtractionStatus.FOUND),
        )
        template = SimpleNamespace(id=uuid4())
        warnings: list[str] = []
        candidate_index: dict = {}
        fingerprint = None
        should_learn_after_ai = False
        fallback_reason = None

    templates = MagicMock()
    templates.enabled = True
    templates.try_deterministic_extract = AsyncMock(return_value=_FakeOutcome())

    use_case = ExtractGuestPayslipUseCase(
        document_repository=MagicMock(),
        extraction_repository=MagicMock(),
        object_storage=MagicMock(),
        organization_bootstrap=MagicMock(),
        ocr_use_case=MagicMock(),
        parse_use_case=MagicMock(),
        template_orchestrator=templates,
    )

    ocr = SimpleNamespace(pages=[1], raw_text="x", engine="tesseract", warnings=[])
    timer = MagicMock()
    result = await use_case._run_shared_document_pipeline(
        document_id=uuid4(),
        extraction_id=uuid4(),
        document_model=polluted.to_dict(),
        layout_analysis={"pages": [{"page": 1}]},
        evidence_bundle={"candidate_index": {}},
        ocr_result=ocr,
        cancel_check=None,
        organization_id=None,
        timer=timer,
    )
    slots = (result.document_model or {}).get("slots") or []
    assert result.parser_status == "completed"
    assert len(slots) == 2
    assert (result.document_model or {}).get("layout_metadata", {}).get(REVIEW_MATERIALIZED_META_KEY) is True
    gross = [s for s in slots if (s.get("metadata") or {}).get("canonical_key") == "gross_salary"]
    assert len(gross) == 1
    assert gross[0]["id"] == "a"


@pytest.mark.asyncio
async def test_shared_pipeline_ai_path_materializes() -> None:
    from payroll_copilot.application.use_cases.extract_guest_payslip import (
        ExtractGuestPayslipUseCase,
    )

    base_slots = [
        _slot(slot_id="a", label="Gross Salary", value="100", reading_index=0, candidate_ids=["c1"]),
        _slot(slot_id="b", label="Gross Salary", value="200", reading_index=1, candidate_ids=["c2"], conflict=True),
        _slot(slot_id="c", label="Custom Line", value="9", reading_index=2, candidate_ids=["c3"]),
    ]
    base = _doc(*base_slots)

    parsed = StructuredPayslipParse(
        gross_salary=ExtractedField(
            value="100",
            status=FieldExtractionStatus.FOUND,
            candidate_ids=["c1"],
        ),
    )
    parse_uc = MagicMock()
    parse_uc.execute = AsyncMock(
        return_value=SimpleNamespace(fields=parsed, warnings=[], retry_used=False, model="test-model")
    )

    use_case = ExtractGuestPayslipUseCase(
        document_repository=MagicMock(),
        extraction_repository=MagicMock(),
        object_storage=MagicMock(),
        organization_bootstrap=MagicMock(),
        ocr_use_case=MagicMock(),
        parse_use_case=parse_uc,
        template_orchestrator=None,
    )
    ocr = SimpleNamespace(pages=[1], raw_text="x", engine="tesseract", warnings=[])
    result = await use_case._run_shared_document_pipeline(
        document_id=uuid4(),
        extraction_id=uuid4(),
        document_model=base.to_dict(),
        layout_analysis={"pages": [{"page": 1}]},
        evidence_bundle={
            "candidate_index": {
                "c1": {"candidate_id": "c1", "label_text": "Gross Salary", "value_text": "100"},
                "c2": {"candidate_id": "c2", "label_text": "Gross Salary", "value_text": "200"},
                "c3": {"candidate_id": "c3", "label_text": "Custom Line", "value_text": "9"},
            }
        },
        ocr_result=ocr,
        cancel_check=None,
        organization_id=None,
        timer=MagicMock(),
    )
    slots = (result.document_model or {}).get("slots") or []
    labels = [s.get("label") for s in slots]
    assert labels.count("Gross Salary") == 1
    assert "Custom Line" in labels
    assert result.parser_status == "completed"


def test_deepcopy_input_not_mutated() -> None:
    doc = _doc(
        _slot(slot_id="a", label="X", value="1", canonical_key="gross_salary"),
        _slot(slot_id="b", label="X", value="2", canonical_key="gross_salary", conflict=True),
    )
    before = deepcopy(doc.to_dict())
    materialize_review_document(doc)
    assert doc.to_dict()["slots"] == before["slots"]
