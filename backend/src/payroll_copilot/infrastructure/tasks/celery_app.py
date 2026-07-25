"""Celery task definitions for background processing.

Composition:
- ``batch_pipeline_factory.create_batch_payslip_pipeline`` — shared DI for
  sync review paths and the worker processor.
- ``batch_processor.BatchPayslipProcessor`` — bulk split/process orchestration.
- This module — Celery app config + thin task wrappers only.
"""

import logging

from celery import Celery

from payroll_copilot.infrastructure.config.service_resolver import (
    get_resolved_celery_broker_url,
    get_resolved_celery_result_backend,
)
from payroll_copilot.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "payroll_copilot",
    broker=get_resolved_celery_broker_url(settings),
    backend=get_resolved_celery_result_backend(settings),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Jerusalem",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
)


@celery_app.task(name="process_bulk_payslip_pdf", bind=True, max_retries=0)
def process_bulk_payslip_pdf(self, batch_job_id: str, document_id: str) -> dict:
    """Background task: split bulk PDF, then OCR/identify/validate each slip.

    Retries are disabled: after the first payslip is persisted, a whole-job
    retry would risk duplicate documents and double-counted progress.
    Per-slip failures are isolated inside the processor instead.
    Duplicate deliveries are skipped via Redis claim.
    """
    from payroll_copilot.infrastructure.tasks.batch_processor import BatchPayslipProcessor

    self.update_state(
        state="STARTED",
        meta={"batch_job_id": batch_job_id, "document_id": document_id},
    )
    try:
        processor = BatchPayslipProcessor()
        result = processor.process(batch_job_id, document_id)
        if result.get("status") == "skipped_duplicate":
            logger.info(
                "Skipping duplicate bulk payslip delivery batch_job_id=%s existing=%s",
                batch_job_id,
                result.get("existing_status"),
            )
        return result
    except Exception as exc:
        logger.exception(
            "Bulk payslip processing failed batch_job_id=%s document_id=%s",
            batch_job_id,
            document_id,
        )
        self.update_state(
            state="FAILURE",
            meta={
                "batch_job_id": batch_job_id,
                "document_id": document_id,
                "error": str(exc) or exc.__class__.__name__,
            },
        )
        raise


@celery_app.task(
    name="process_document_ocr",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
)
def process_document_ocr(self, document_id: str) -> dict:
    """Background task: OCR extraction for uploaded document.

    Transient infrastructure failures are retried. Full OCR worker wiring
    remains a later phase; this keeps enqueue/state contracts consistent.
    """
    self.update_state(state="STARTED", meta={"document_id": document_id})
    return {"document_id": document_id, "status": "processed"}


@celery_app.task(
    name="import_employee_excel",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
)
def import_employee_excel(self, document_id: str, organization_id: str) -> dict:
    """Background task: import employee master data from Excel."""
    self.update_state(
        state="STARTED",
        meta={"document_id": document_id, "organization_id": organization_id},
    )
    return {
        "document_id": document_id,
        "organization_id": organization_id,
        "status": "imported",
    }


@celery_app.task(name="sync_legal_rules_mcp")
def sync_legal_rules_mcp() -> dict:
    """Scheduled task: compare local YAML rules against external sources."""
    return {"status": "completed", "proposals_created": 0}


@celery_app.task(name="reconcile_employee_leave_status")
def reconcile_employee_leave_status(organization_id: str | None = None) -> dict:
    """Reconcile employee on_leave from approved vacations covering today."""
    import asyncio
    from uuid import UUID

    from payroll_copilot.application.use_cases.manage_vacations import (
        ReconcileEmployeeLeaveStatusUseCase,
    )
    from payroll_copilot.infrastructure.persistence import dynamodb as dynamo_persistence

    async def _run() -> dict:
        uc = ReconcileEmployeeLeaveStatusUseCase(
            vacations=dynamo_persistence.get_vacation_request_repository(),
            employees=dynamo_persistence.get_employee_repository(),
            audit=dynamo_persistence.get_audit_log_repository(),
        )
        if organization_id:
            return await uc.execute(UUID(organization_id))
        orgs = await dynamo_persistence.get_organization_directory().list_organization_ids()
        totals = {"updated": 0, "organizations": 0}
        for org in orgs:
            result = await uc.execute(org)
            totals["updated"] += int(result.get("updated") or 0)
            totals["organizations"] += 1
        return totals

    return asyncio.run(_run())


# Celery Beat schedule — enable the beat process in deployment to run this.
celery_app.conf.beat_schedule = {
    "reconcile-employee-leave-status-hourly": {
        "task": "reconcile_employee_leave_status",
        "schedule": 3600.0,
    },
}
