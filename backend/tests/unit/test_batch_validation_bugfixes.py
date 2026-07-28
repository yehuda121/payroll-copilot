"""Unit tests for Batch Validation bug fixes (registry + snapshot merge)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from payroll_copilot.application.dto.validation_report_enrichment import (
    UploadedDocumentSummary,
    ValidationReportEnrichment,
    ValidationScopeItem,
    merge_validation_context_snapshot,
)
from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.domain.enums import ValidationResult, ValidationRunStatus
from payroll_copilot.domain.rules import ensure_validation_rules_registered, get_registered_rules
from payroll_copilot.infrastructure.persistence.dynamodb.validation import (
    DynamoValidationRunRepository,
)
from payroll_copilot.infrastructure.persistence.mappers.validation_mapper import (
    run_record_to_model,
)


def test_ensure_validation_rules_registered_loads_core_categories() -> None:
    ensure_validation_rules_registered()
    registered = get_registered_rules()
    assert registered
    assert any(rid.startswith("sanity.") for rid in registered)
    assert any(rid.startswith("employee.") for rid in registered)
    assert any(rid.startswith("contract.") for rid in registered)
    assert any(rid.startswith("legal.") for rid in registered)
    # Idempotent
    ensure_validation_rules_registered()
    assert len(get_registered_rules()) == len(registered)


def _sample_enrichment() -> ValidationReportEnrichment:
    return ValidationReportEnrichment(
        validation_scope=(
            ValidationScopeItem(
                key="payroll_rules",
                label="Payroll rules",
                status="completed",
                reason=None,
            ),
        ),
        uploaded_documents=(
            UploadedDocumentSummary(
                document_type="payslip",
                document_id=str(uuid4()),
                uploaded=True,
                original_filename="slip.pdf",
            ),
        ),
        validation_confidence=Decimal("0.80"),
        confidence_explanation="ok",
        checks_passed_count=1,
        extraction_connected=True,
    )


def test_merge_validation_context_snapshot_preserves_rule_outcomes() -> None:
    enrichment = _sample_enrichment()
    snapshot = {
        **enrichment.to_context_snapshot(),
        "rerun_scope": "full",
        "rule_outcomes": [
            {
                "rule_id": "employee.national_id.match",
                "outcome": "not_run",
                "skip_reason": "employee_not_identified",
                "reason_code": "EMPLOYEE_NOT_IDENTIFIED",
                "message": "Employee not identified",
            }
        ],
    }
    # Legacy bug path: enrichment-only would drop outcomes.
    wiped = enrichment.to_context_snapshot()
    assert "rule_outcomes" not in wiped

    merged = merge_validation_context_snapshot(snapshot, enrichment)
    assert merged["rule_outcomes"][0]["rule_id"] == "employee.national_id.match"
    assert merged["rerun_scope"] == "full"
    assert merged["validation_scope"][0]["key"] == "payroll_rules"
    assert merged["extraction_connected"] is True


def test_dynamo_validation_run_to_item_keeps_rule_outcomes() -> None:
    enrichment = _sample_enrichment()
    outcomes = [
        {
            "rule_id": "sanity.pay_period.parseable",
            "outcome": "passed",
            "skip_reason": None,
            "reason_code": None,
            "message": None,
        }
    ]
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=uuid4(),
        organization_id=uuid4(),
        employee_id=uuid4(),
        extraction_id=uuid4(),
        status=ValidationRunStatus.COMPLETED,
        overall_result=ValidationResult.PASS,
        overall_confidence=Decimal("0.9"),
        rules_evaluated=1,
        rules_failed=0,
        context_snapshot={
            **enrichment.to_context_snapshot(),
            "rule_outcomes": outcomes,
            "rerun_scope": "full",
        },
        enrichment=enrichment,
    )
    item = DynamoValidationRunRepository(table=None)._to_item(run)  # type: ignore[arg-type]
    snap = item["context_snapshot"]
    # Serde may prune null skip_reason/message fields; identity of outcomes must remain.
    assert snap["rule_outcomes"][0]["rule_id"] == "sanity.pay_period.parseable"
    assert snap["rule_outcomes"][0]["outcome"] == "passed"
    assert snap["rerun_scope"] == "full"
    assert "validation_scope" in snap


def test_sql_run_record_to_model_keeps_rule_outcomes() -> None:
    enrichment = _sample_enrichment()
    outcomes = [{"rule_id": "legal.minimum_wage", "outcome": "not_run"}]
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=uuid4(),
        organization_id=uuid4(),
        status=ValidationRunStatus.COMPLETED,
        overall_result=ValidationResult.PASS,
        overall_confidence=Decimal("0.5"),
        rules_evaluated=0,
        rules_failed=0,
        context_snapshot={
            **enrichment.to_context_snapshot(),
            "rule_outcomes": outcomes,
        },
        enrichment=enrichment,
    )
    model = run_record_to_model(run)
    assert model.context_snapshot["rule_outcomes"] == outcomes
