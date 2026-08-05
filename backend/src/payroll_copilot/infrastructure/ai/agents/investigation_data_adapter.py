"""DynamoDB + ephemeral S3 enrichment adapter for payroll investigation."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from payroll_copilot.application.ports.object_storage import ObjectStoragePort
from payroll_copilot.application.ports.payslip_parser import PayslipParser
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    is_employee_visible_document,
)
from payroll_copilot.application.use_cases.ocr_extract import (
    ExtractDocumentTextCommand,
    ExtractDocumentTextUseCase,
)
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.domain.investigation.types import (
    PeriodRef,
    PeriodSnapshot,
    ValidationFindingExcerpt,
)

logger = logging.getLogger(__name__)


def _structured_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


class InvestigationDataAdapter:
    """Loads auth-bound payslip snapshots. Enrichment is ephemeral (no Dynamo write)."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        validation_runs: ValidationRunRepository,
        validation_findings: ValidationFindingRepository,
        object_storage: ObjectStoragePort | None = None,
        ocr_use_case: ExtractDocumentTextUseCase | None = None,
        payslip_parser: PayslipParser | None = None,
    ) -> None:
        self._documents = documents
        self._extractions = extractions
        self._validation_runs = validation_runs
        self._validation_findings = validation_findings
        self._storage = object_storage
        self._ocr = ocr_use_case
        self._parser = payslip_parser

    async def list_available_payslip_periods(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        include_unpublished: bool = False,
    ) -> set[str]:
        docs = await self._documents.list_for_employee(
            organization_id=organization_id,
            employee_id=employee_id,
        )
        if not include_unpublished:
            docs = [doc for doc in docs if is_employee_visible_document(doc)]
        periods: set[str] = set()
        for doc in docs:
            if doc.document_type != DocumentType.PAYSLIP:
                continue
            if doc.period is None:
                continue
            periods.add(f"{doc.period.year:04d}-{doc.period.month:02d}")
        return periods

    async def load_period_snapshot(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        period: PeriodRef,
        include_unpublished: bool = False,
    ) -> PeriodSnapshot | None:
        doc = await self._documents.find_payslip_for_period(
            organization_id=organization_id,
            employee_id=employee_id,
            period_year=period.year,
            period_month=period.month,
        )
        if doc is None:
            return None
        if not include_unpublished and not is_employee_visible_document(doc):
            return None
        extraction = await self._extractions.get_latest_for_document(doc.id)
        structured = _structured_dict(extraction.structured_data if extraction else None)
        excerpts: list[ValidationFindingExcerpt] = []
        runs = await self._validation_runs.list_for_document(doc.id)
        if runs:
            latest = runs[0]
            findings = await self._validation_findings.list_by_run_id(latest.id)
            for finding in findings[:20]:
                excerpts.append(
                    ValidationFindingExcerpt(
                        finding_id=str(finding.id),
                        rule_id=str(finding.rule_id),
                        severity=str(getattr(finding.severity, "value", finding.severity)),
                        message=str(finding.message_key),
                        period_key=period.key,
                    )
                )
        return PeriodSnapshot(
            period=period,
            document_id=doc.id,
            storage_key=doc.storage_key,
            structured_fields=structured,
            finding_excerpts=excerpts,
        )

    async def enrich_snapshot_from_original(
        self,
        snapshot: PeriodSnapshot,
        *,
        missing_keys: tuple[str, ...],
    ) -> PeriodSnapshot:
        if not missing_keys:
            return snapshot
        if not snapshot.storage_key or self._storage is None or self._ocr is None or self._parser is None:
            return PeriodSnapshot(
                period=snapshot.period,
                document_id=snapshot.document_id,
                storage_key=snapshot.storage_key,
                structured_fields=dict(snapshot.structured_fields),
                finding_excerpts=list(snapshot.finding_excerpts),
                enrichment_applied=False,
                enrichment_notes="s3_enrichment_unavailable",
            )
        try:
            content = await self._storage.download(snapshot.storage_key)
            if not content:
                return PeriodSnapshot(
                    period=snapshot.period,
                    document_id=snapshot.document_id,
                    storage_key=snapshot.storage_key,
                    structured_fields=dict(snapshot.structured_fields),
                    finding_excerpts=list(snapshot.finding_excerpts),
                    enrichment_applied=False,
                    enrichment_notes="enrichment_failed:empty_s3_object",
                )
            filename = snapshot.storage_key.rsplit("/", 1)[-1] or "payslip.pdf"
            from payroll_copilot.application.services.deterministic_pdf import (
                DeterministicExtractionStatus,
                extract_document_from_pdf,
            )
            from payroll_copilot.domain.enums import DocumentType

            extracted = extract_document_from_pdf(
                content,
                document_type=DocumentType.PAYSLIP,
                filename=filename,
                mime_type="application/pdf",
            )
            if extracted.status is not DeterministicExtractionStatus.COMPLETED:
                return PeriodSnapshot(
                    period=snapshot.period,
                    document_id=snapshot.document_id,
                    storage_key=snapshot.storage_key,
                    structured_fields=dict(snapshot.structured_fields),
                    finding_excerpts=list(snapshot.finding_excerpts),
                    enrichment_applied=False,
                    enrichment_notes=f"enrichment_failed:{extracted.error_code or extracted.status.value}",
                )
            parse_result = None
            source_map_from_pdf = extracted.field_map()
            ocr_text = extracted.raw_text
            if not ocr_text:
                return PeriodSnapshot(
                    period=snapshot.period,
                    document_id=snapshot.document_id,
                    storage_key=snapshot.storage_key,
                    structured_fields=dict(snapshot.structured_fields),
                    finding_excerpts=list(snapshot.finding_excerpts),
                    enrichment_applied=False,
                    enrichment_notes="enrichment_failed:empty_ocr",
                )
            _ = self._ocr, self._parser  # retained for DI; enrichment uses deterministic PDF SoT
        except Exception as exc:  # noqa: BLE001 — Scenario C must never raise to chat
            logger.info(
                "investigation ephemeral enrichment failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return PeriodSnapshot(
                period=snapshot.period,
                document_id=snapshot.document_id,
                storage_key=snapshot.storage_key,
                structured_fields=dict(snapshot.structured_fields),
                finding_excerpts=list(snapshot.finding_excerpts),
                enrichment_applied=False,
                enrichment_notes=f"enrichment_failed:{type(exc).__name__}",
            )

        try:
            merged = dict(snapshot.structured_fields)
            filled: list[str] = []
            source_map: dict[str, Any] = dict(source_map_from_pdf)
            fields_obj = getattr(parse_result, "fields", None) if parse_result is not None else None
            payload = getattr(parse_result, "parsed_payload", None) if parse_result is not None else None
            if isinstance(payload, dict):
                source_map.update(payload)
            if fields_obj is not None and hasattr(fields_obj, "model_dump"):
                dumped = fields_obj.model_dump()
                if isinstance(dumped, dict):
                    source_map.update(dumped)
            elif isinstance(fields_obj, dict):
                source_map.update(fields_obj)

            for key in missing_keys:
                if key not in source_map:
                    continue
                value = source_map[key]
                if value in (None, ""):
                    continue
                if isinstance(value, dict):
                    status = str(value.get("status") or "").upper()
                    if status == "MISSING" and value.get("value") in (None, ""):
                        continue
                merged[key] = value
                filled.append(key)

            return PeriodSnapshot(
                period=snapshot.period,
                document_id=snapshot.document_id,
                storage_key=snapshot.storage_key,
                structured_fields=merged,
                finding_excerpts=list(snapshot.finding_excerpts),
                enrichment_applied=bool(filled),
                enrichment_notes=("filled:" + ",".join(filled)) if filled else "enrichment_no_fields",
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "investigation enrichment merge failed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return PeriodSnapshot(
                period=snapshot.period,
                document_id=snapshot.document_id,
                storage_key=snapshot.storage_key,
                structured_fields=dict(snapshot.structured_fields),
                finding_excerpts=list(snapshot.finding_excerpts),
                enrichment_applied=False,
                enrichment_notes=f"enrichment_failed:{type(exc).__name__}",
            )
