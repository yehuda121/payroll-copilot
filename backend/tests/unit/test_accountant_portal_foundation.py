"""Tests for batch progress store and low-confidence manual review queue."""

from payroll_copilot.application.services.batch_progress_store import BatchProgressStore
from payroll_copilot.application.services.manual_review_queue import (
    ManualReviewQueue,
    should_enqueue_low_confidence,
)


def test_batch_progress_tracks_pipeline_stages() -> None:
    store = BatchProgressStore()
    job = store.create("job-1", document_id="doc-1", source_filename="bulk.pdf")
    assert job.stages[0].status == "completed"
    store.mark_stage("job-1", "split", status="completed", total_slips=3, job_status="running")
    store.mark_stage("job-1", "ocr", status="running")
    updated = store.get("job-1")
    assert updated is not None
    assert updated.total_slips == 3
    assert updated.current_stage == "ocr"
    assert updated.progress_percent > 0


def test_low_confidence_never_auto_creates() -> None:
    assert should_enqueue_low_confidence(None) is True
    assert should_enqueue_low_confidence(0.4) is True
    assert should_enqueue_low_confidence(0.9) is False


def test_manual_review_queue_resolve() -> None:
    queue = ManualReviewQueue()
    item = queue.enqueue(
        reason="low_confidence_employee_identification",
        confidence=0.42,
        national_id_masked="*******123",
    )
    assert len(queue.list_pending()) == 1
    resolved = queue.resolve(item.id, status="dismissed", notes="duplicate scan")
    assert resolved is not None
    assert resolved.status == "dismissed"
    assert queue.list_pending() == []
