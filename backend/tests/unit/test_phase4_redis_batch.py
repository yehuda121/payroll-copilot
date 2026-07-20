"""Phase 4+5 Redis durability and batch reliability unit tests."""

from __future__ import annotations

import base64
from uuid import uuid4

from payroll_copilot.application.services.batch_progress_store import (
    BatchExtractedItem,
    InMemoryBatchProgressStore,
)
from payroll_copilot.application.services.guest_ephemeral_store import (
    GuestEphemeralSession,
    GuestEphemeralStore,
    GuestEphemeralSupportingDoc,
)
from payroll_copilot.domain.enums import DocumentType


def test_guest_session_roundtrip_serialization() -> None:
    session = GuestEphemeralSession(
        document_id=uuid4(),
        extraction_id=uuid4(),
        content=b"%PDF-1.4 guest",
        original_filename="slip.pdf",
        mime_type="application/pdf",
        language="he",
        ocr_status="completed",
        parser_status="completed",
        ocr_engine="tesseract",
        parser_model="test",
        raw_text="hello",
        structured_data={"a": 1},
        ocr_result={"pages": []},
        warnings=["w1"],
        error_message=None,
        field_confidences={"x": 0.9},
        dynamic_entries=[{"id": "e1"}],
        supporting_document_ids=[uuid4()],
    )
    restored = GuestEphemeralSession.from_dict(session.to_dict())
    assert restored.document_id == session.document_id
    assert restored.content == session.content
    assert restored.structured_data == {"a": 1}
    assert restored.supporting_document_ids == session.supporting_document_ids
    assert "content_b64" in session.to_dict()
    assert base64.b64decode(session.to_dict()["content_b64"]) == b"%PDF-1.4 guest"


def test_guest_supporting_roundtrip_serialization() -> None:
    doc = GuestEphemeralSupportingDoc(
        document_id=uuid4(),
        document_type=DocumentType.NATIONAL_ID,
        content=b"id-bytes",
        original_filename="id.png",
        mime_type="image/png",
    )
    restored = GuestEphemeralSupportingDoc.from_dict(doc.to_dict())
    assert restored.document_id == doc.document_id
    assert restored.content == b"id-bytes"
    assert restored.document_type == DocumentType.NATIONAL_ID


def test_inmemory_guest_store_confirm_and_supporting() -> None:
    store = GuestEphemeralStore(ttl_hours=1.0)
    document_id, extraction_id = store.new_ids()
    store.save(
        GuestEphemeralSession(
            document_id=document_id,
            extraction_id=extraction_id,
            content=b"pdf",
            original_filename="slip.pdf",
            mime_type="application/pdf",
            language="he",
            ocr_status="completed",
            parser_status="completed",
            ocr_engine="tesseract",
            parser_model="test",
            raw_text="x",
            structured_data={},
            ocr_result={},
            warnings=[],
            error_message=None,
            field_confidences={},
        )
    )
    support = store.save_supporting(
        document_type=DocumentType.NATIONAL_ID,
        content=b"id",
        original_filename="id.png",
        mime_type="image/png",
        payslip_document_id=document_id,
    )
    confirmed = store.confirm(document_id, dynamic_entries=[{"id": "e1", "value": "1"}])
    assert confirmed is not None
    assert confirmed.confirmation_status == "confirmed"
    assert support.document_id in confirmed.supporting_document_ids
    assert store.get_supporting(support.document_id) is not None


def test_batch_claim_prevents_duplicate_processing() -> None:
    store = InMemoryBatchProgressStore()
    store.create("job-1", organization_id="org-a", created_by_user_id="user-a")

    assert store.try_claim_processing("job-1", worker_id="w1") is True
    assert store.try_claim_processing("job-1", worker_id="w2") is False
    job = store.get("job-1")
    assert job is not None
    assert job.status == "running"


def test_batch_claim_rejects_completed_jobs() -> None:
    store = InMemoryBatchProgressStore()
    store.create("job-2", organization_id="org-a", created_by_user_id="user-a")
    store.mark_stage("job-2", "report", status="completed", job_status="completed")
    assert store.try_claim_processing("job-2", worker_id="w1") is False


def test_batch_upsert_updates_same_item() -> None:
    store = InMemoryBatchProgressStore()
    store.create("job-3", organization_id="org-a")
    store.upsert_item(
        "job-3",
        BatchExtractedItem(id="slip-1", slip_index=0, status="processing"),
    )
    store.upsert_item(
        "job-3",
        BatchExtractedItem(id="slip-1", slip_index=0, status="passed"),
    )
    job = store.get("job-3")
    assert job is not None
    assert len(job.items) == 1
    assert job.items[0].status == "passed"
