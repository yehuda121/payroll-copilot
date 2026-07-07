"""Map domain validation reports to persistence DTOs."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from payroll_copilot.application.dto.validation_run import ValidationFindingRecord, ValidationRunRecord
from payroll_copilot.domain.enums import ValidationResult, ValidationRunStatus
from payroll_copilot.domain.value_objects import ValidationReport


def report_to_run_record(
    *,
    report: ValidationReport,
    document_id: UUID,
    organization_id: UUID,
    employee_id: UUID | None,
) -> ValidationRunRecord:
    overall_result = ValidationResult(report.overall_result)
    return ValidationRunRecord(
        id=report.validation_run_id,
        document_id=document_id,
        organization_id=organization_id,
        employee_id=employee_id,
        status=ValidationRunStatus.COMPLETED,
        overall_result=overall_result,
        overall_confidence=Decimal(str(report.overall_confidence.value)),
        rules_evaluated=report.rules_evaluated,
        rules_failed=report.rules_failed,
    )


def report_to_finding_records(
    report: ValidationReport,
    validation_run_id: UUID,
) -> list[ValidationFindingRecord]:
    return [
        ValidationFindingRecord(
            id=uuid4(),
            validation_run_id=validation_run_id,
            rule_id=finding.rule_id,
            rule_category=finding.category,
            severity=finding.severity,
            message_key=finding.message_key,
            message_params=finding.message_params,
            expected_value=finding.expected_value,
            actual_value=finding.actual_value,
            confidence=Decimal(str(finding.confidence.value)),
            legal_reference=finding.legal_reference,
        )
        for finding in report.findings
    ]