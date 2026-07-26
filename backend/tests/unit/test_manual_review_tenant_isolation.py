"""Tenant isolation for the accountant manual-review queue."""

from __future__ import annotations

from uuid import uuid4

from payroll_copilot.application.services.manual_review_queue import ManualReviewQueue


def test_manual_review_queue_is_organization_scoped() -> None:
    queue = ManualReviewQueue()
    org_a = str(uuid4())
    org_b = str(uuid4())

    item_a = queue.enqueue(
        organization_id=org_a,
        reason="low_confidence_employee_identification",
        confidence=0.42,
        national_id_masked="*******123",
    )
    item_b = queue.enqueue(
        organization_id=org_b,
        reason="low_confidence_employee_identification",
        confidence=0.40,
        national_id_masked="*******999",
    )

    assert [row.id for row in queue.list_pending(org_a)] == [item_a.id]
    assert [row.id for row in queue.list_pending(org_b)] == [item_b.id]
    assert queue.list_pending(org_a)[0].organization_id == org_a

    # Cross-tenant resolve must fail closed.
    assert queue.resolve(item_a.id, organization_id=org_b, status="dismissed") is None
    assert queue.list_pending(org_a)[0].status == "pending"

    resolved = queue.resolve(item_a.id, organization_id=org_a, status="dismissed", notes="ok")
    assert resolved is not None
    assert resolved.status == "dismissed"
    assert queue.list_pending(org_a) == []
    assert len(queue.list_pending(org_b)) == 1


def test_manual_review_enqueue_requires_organization_id() -> None:
    queue = ManualReviewQueue()
    try:
        queue.enqueue(organization_id="", reason="x")
        raised = False
    except ValueError as exc:
        raised = True
        assert str(exc) == "organization_id_required"
    assert raised
