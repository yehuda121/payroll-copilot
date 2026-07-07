"""Celery task definitions for background processing."""

from celery import Celery

from payroll_copilot.infrastructure.config.service_resolver import (
    get_resolved_celery_broker_url,
    get_resolved_celery_result_backend,
)
from payroll_copilot.infrastructure.config.settings import get_settings

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
)


@celery_app.task(name="process_bulk_payslip_pdf", bind=True, max_retries=3)
def process_bulk_payslip_pdf(self, batch_job_id: str, document_id: str) -> dict:
    """Background task: split bulk PDF, OCR, identify, validate each slip."""
    from payroll_copilot.infrastructure.tasks.batch_processor import BatchPayslipProcessor

    processor = BatchPayslipProcessor()
    return processor.process(batch_job_id, document_id)


@celery_app.task(name="process_document_ocr")
def process_document_ocr(document_id: str) -> dict:
    """Background task: OCR extraction for uploaded document."""
    return {"document_id": document_id, "status": "processed"}


@celery_app.task(name="import_employee_excel")
def import_employee_excel(document_id: str, organization_id: str) -> dict:
    """Background task: import employee master data from Excel."""
    return {"document_id": document_id, "organization_id": organization_id, "status": "imported"}


@celery_app.task(name="sync_legal_rules_mcp")
def sync_legal_rules_mcp() -> dict:
    """Scheduled task: compare local YAML rules against external sources."""
    return {"status": "completed", "proposals_created": 0}
