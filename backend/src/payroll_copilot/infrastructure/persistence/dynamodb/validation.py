"""DynamoDB validation run and finding repositories."""

from __future__ import annotations

from decimal import Decimal
from datetime import UTC, datetime
from uuid import UUID

from payroll_copilot.application.dto.validation_report_enrichment import ValidationReportEnrichment
from payroll_copilot.application.dto.validation_run import ValidationFindingRecord, ValidationRunRecord
from payroll_copilot.application.ports.repositories import (
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.domain.enums import FindingSeverity, RuleCategory, ValidationResult, ValidationRunStatus
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI1, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import (
    dumps_value,
    loads_datetime,
    loads_decimal,
    loads_uuid,
)


class DynamoValidationRunRepository(ValidationRunRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _sort_key(self, run: ValidationRunRecord) -> str:
        stamp = run.completed_at or datetime.now(UTC)
        return stamp.isoformat()

    def _to_item(self, run: ValidationRunRecord) -> dict:
        now = datetime.now(UTC)
        context_snapshot = run.context_snapshot
        if run.enrichment is not None:
            context_snapshot = run.enrichment.to_context_snapshot()
        completed = run.completed_at or now
        item = {
            "PK": keys.gsi1_doc(run.document_id),
            "SK": keys.valrun_sk(sort_key=self._sort_key(run), run_id=run.id),
            "entity_type": "validation_run",
            "GSI1PK": keys.gsi1_valrun(run.id),
            "GSI1SK": "META",
            "id": str(run.id),
            "document_id": str(run.document_id),
            "organization_id": str(run.organization_id),
            "employee_id": dumps_value(run.employee_id),
            "extraction_id": dumps_value(run.extraction_id),
            "status": dumps_value(run.status),
            "overall_result": dumps_value(run.overall_result),
            "overall_confidence": dumps_value(run.overall_confidence),
            "rules_evaluated": run.rules_evaluated,
            "rules_failed": run.rules_failed,
            "context_snapshot": dumps_value(context_snapshot or {}),
            "started_at": now.isoformat(),
            "completed_at": dumps_value(completed),
        }
        return {k: v for k, v in item.items() if v is not None}

    def _to_record(self, item: dict) -> ValidationRunRecord:
        enrichment = ValidationReportEnrichment.from_context_snapshot(
            dict(item.get("context_snapshot") or {})
        )
        overall_result = item.get("overall_result")
        return ValidationRunRecord(
            id=UUID(str(item["id"])),
            document_id=UUID(str(item["document_id"])),
            organization_id=UUID(str(item["organization_id"])),
            employee_id=loads_uuid(item.get("employee_id")),
            extraction_id=loads_uuid(item.get("extraction_id")),
            status=ValidationRunStatus(str(item.get("status") or ValidationRunStatus.COMPLETED.value)),
            overall_result=ValidationResult(str(overall_result)) if overall_result else None,
            overall_confidence=loads_decimal(item.get("overall_confidence")),
            rules_evaluated=int(item.get("rules_evaluated") or 0),
            rules_failed=int(item.get("rules_failed") or 0),
            context_snapshot=dict(item.get("context_snapshot") or {}),
            enrichment=enrichment,
            completed_at=loads_datetime(item.get("completed_at")),
        )

    async def save(self, run: ValidationRunRecord) -> ValidationRunRecord:
        existing = await self.get_by_id(run.id)
        if existing is not None:
            old_items = await self._table.query_eq_pk(
                keys.gsi1_valrun(run.id), index_name=GSI1, limit=1
            )
            for old in old_items:
                await self._table.delete_item({"PK": old["PK"], "SK": old["SK"]})
        await self._table.put_item(self._to_item(run))
        return run

    async def get_by_id(self, run_id: UUID) -> ValidationRunRecord | None:
        items = await self._table.query_eq_pk(keys.gsi1_valrun(run_id), index_name=GSI1, limit=1)
        if not items:
            return None
        return self._to_record(items[0])

    async def list_latest_by_document_ids(
        self, document_ids: list[UUID]
    ) -> dict[UUID, ValidationRunRecord]:
        latest: dict[UUID, ValidationRunRecord] = {}
        for document_id in document_ids:
            runs = await self.list_for_document(document_id)
            if runs:
                latest[document_id] = runs[0]
        return latest

    async def list_for_document(self, document_id: UUID) -> list[ValidationRunRecord]:
        items = await self._table.query_eq_pk(
            keys.gsi1_doc(document_id),
            sk_begins_with="VALRUN#",
            scan_index_forward=False,
        )
        return [self._to_record(item) for item in items]


class DynamoValidationFindingRepository(ValidationFindingRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _to_item(self, finding: ValidationFindingRecord) -> dict:
        item = {
            "PK": keys.gsi1_valrun(finding.validation_run_id),
            "SK": keys.valfind_sk(finding.id),
            "entity_type": "validation_finding",
            "id": str(finding.id),
            "validation_run_id": str(finding.validation_run_id),
            "rule_id": finding.rule_id,
            "rule_category": dumps_value(finding.rule_category),
            "severity": dumps_value(finding.severity),
            "message_key": finding.message_key,
            "message_params": dumps_value(finding.message_params or {}),
            "expected_value": finding.expected_value,
            "actual_value": finding.actual_value,
            "confidence": dumps_value(finding.confidence),
            "legal_reference": finding.legal_reference,
            "created_at": datetime.now(UTC).isoformat(),
        }
        return {k: v for k, v in item.items() if v is not None}

    def _to_record(self, item: dict) -> ValidationFindingRecord:
        return ValidationFindingRecord(
            id=UUID(str(item["id"])),
            validation_run_id=UUID(str(item["validation_run_id"])),
            rule_id=str(item.get("rule_id") or ""),
            rule_category=RuleCategory(str(item.get("rule_category") or RuleCategory.LEGAL.value)),
            severity=FindingSeverity(str(item.get("severity") or FindingSeverity.INFO.value)),
            message_key=str(item.get("message_key") or ""),
            message_params=dict(item.get("message_params") or {}),
            expected_value=item.get("expected_value"),
            actual_value=item.get("actual_value"),
            confidence=loads_decimal(item.get("confidence")) or Decimal("0"),
            legal_reference=item.get("legal_reference"),
        )

    async def save_all(
        self,
        run_id: UUID,
        findings: list[ValidationFindingRecord],
    ) -> list[ValidationFindingRecord]:
        saved: list[ValidationFindingRecord] = []
        for finding in findings:
            await self._table.put_item(self._to_item(finding))
            saved.append(finding)
        return saved

    async def list_by_run_id(self, run_id: UUID) -> list[ValidationFindingRecord]:
        items = await self._table.query_eq_pk(
            keys.gsi1_valrun(run_id),
            sk_begins_with="VALFIND#",
            scan_index_forward=True,
        )
        records = [self._to_record(item) for item in items]
        records.sort(key=lambda r: str(r.id))
        return records
