from payroll_copilot.application.services.batch_progress_store import (
    BatchExtractedItem,
    InMemoryBatchProgressStore,
)


def test_batch_jobs_and_items_are_scoped_by_organization() -> None:
    store = InMemoryBatchProgressStore()
    store.create("org-a-job", organization_id="org-a")
    store.create("org-b-job", organization_id="org-b")

    store.upsert_item(
        "org-a-job",
        BatchExtractedItem(id="slip-1", slip_index=0, status="processing"),
    )
    store.upsert_item(
        "org-a-job",
        BatchExtractedItem(id="slip-1", slip_index=0, status="passed"),
    )

    jobs = store.list_recent(organization_id="org-a")

    assert [job.batch_job_id for job in jobs] == ["org-a-job"]
    assert jobs[0].items[0].status == "passed"
    assert store.list_recent(organization_id="org-b")[0].items == []
