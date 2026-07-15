"""Map between validation run DTOs and SQLAlchemy models."""

from __future__ import annotations

from datetime import UTC, datetime

from payroll_copilot.application.dto.validation_run import ValidationFindingRecord, ValidationRunRecord
from payroll_copilot.application.dto.validation_report_enrichment import ValidationReportEnrichment
from payroll_copilot.infrastructure.persistence.models import ValidationFindingModel, ValidationRunModel


def run_record_to_model(record: ValidationRunRecord) -> ValidationRunModel:
    now = datetime.now(UTC)
    context_snapshot = record.context_snapshot
    if record.enrichment is not None:
        context_snapshot = record.enrichment.to_context_snapshot()
    return ValidationRunModel(
        id=record.id,
        organization_id=record.organization_id,
        document_id=record.document_id,
        employee_id=record.employee_id,
        extraction_id=record.extraction_id,
        status=record.status,
        overall_result=record.overall_result,
        overall_confidence=record.overall_confidence,
        rules_evaluated=record.rules_evaluated,
        rules_failed=record.rules_failed,
        context_snapshot=context_snapshot,
        started_at=now,
        completed_at=now,
    )


def run_model_to_record(model: ValidationRunModel) -> ValidationRunRecord:
    enrichment = ValidationReportEnrichment.from_context_snapshot(model.context_snapshot)
    return ValidationRunRecord(
        id=model.id,
        document_id=model.document_id,
        organization_id=model.organization_id,
        employee_id=model.employee_id,
        extraction_id=getattr(model, "extraction_id", None),
        status=model.status,
        overall_result=model.overall_result,
        overall_confidence=model.overall_confidence,
        rules_evaluated=model.rules_evaluated,
        rules_failed=model.rules_failed,
        context_snapshot=model.context_snapshot,
        enrichment=enrichment,
        completed_at=model.completed_at,
    )


def finding_record_to_model(record: ValidationFindingRecord) -> ValidationFindingModel:
    return ValidationFindingModel(
        id=record.id,
        validation_run_id=record.validation_run_id,
        rule_id=record.rule_id,
        rule_category=record.rule_category,
        severity=record.severity,
        message_key=record.message_key,
        message_params=record.message_params,
        expected_value=record.expected_value,
        actual_value=record.actual_value,
        confidence=record.confidence,
        legal_reference=record.legal_reference,
    )


def finding_model_to_record(model: ValidationFindingModel) -> ValidationFindingRecord:
    return ValidationFindingRecord(
        id=model.id,
        validation_run_id=model.validation_run_id,
        rule_id=model.rule_id,
        rule_category=model.rule_category,
        severity=model.severity,
        message_key=model.message_key,
        message_params=model.message_params,
        expected_value=model.expected_value,
        actual_value=model.actual_value,
        confidence=model.confidence,
        legal_reference=model.legal_reference,
    )
