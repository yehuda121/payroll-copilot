"""Application DTOs for persisted validation runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from payroll_copilot.application.dto.validation_report_enrichment import ValidationReportEnrichment

from payroll_copilot.domain.enums import FindingSeverity, RuleCategory, ValidationResult, ValidationRunStatus


@dataclass
class ValidationFindingRecord:
    id: UUID
    validation_run_id: UUID
    rule_id: str
    rule_category: RuleCategory
    severity: FindingSeverity
    message_key: str
    message_params: dict[str, Any]
    expected_value: str | None
    actual_value: str | None
    confidence: Decimal
    legal_reference: str | None = None


@dataclass
class ValidationRunRecord:
    id: UUID
    document_id: UUID
    organization_id: UUID
    status: ValidationRunStatus
    rules_evaluated: int
    rules_failed: int
    employee_id: UUID | None = None
    overall_result: ValidationResult | None = None
    overall_confidence: Decimal | None = None
    findings: list[ValidationFindingRecord] = field(default_factory=list)
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    enrichment: ValidationReportEnrichment | None = None
    completed_at: datetime | None = None
    extraction_id: UUID | None = None
