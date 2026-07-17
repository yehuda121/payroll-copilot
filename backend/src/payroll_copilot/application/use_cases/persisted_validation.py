"""Use cases for persisting and retrieving validation runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.exceptions import DocumentNotFoundError
from payroll_copilot.application.mappers.validation_mapper import (
    report_to_finding_records,
    report_to_run_record,
)
from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.application.ports.repositories import (
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.services.validation_evidence_report import (
    ValidationEvidenceReportBuilder,
)
from payroll_copilot.application.use_cases.validation import RunValidationUseCase
from payroll_copilot.application.validation.guest_extraction_context_builder import (
    ExtractionRequiredError,
    GuestExtractionValidationContextBuilder,
)
from payroll_copilot.infrastructure.config.settings import get_settings


@dataclass(frozen=True, slots=True)
class RunPersistedValidationCommand:
    document_id: UUID
    employee_id: UUID | None = None
    include_historical: bool = True
    include_contract_rag: bool = True
    supporting_document_ids: tuple[UUID, ...] = field(default_factory=tuple)
    locale: str | None = None
    extraction_id: UUID | None = None


class RunPersistedValidationUseCase:
    """Run deterministic validation from guest extraction and persist results."""

    def __init__(
        self,
        run_validation: RunValidationUseCase,
        guest_context_builder: GuestExtractionValidationContextBuilder,
        document_repository: DocumentRepository,
        validation_run_repository: ValidationRunRepository,
        validation_finding_repository: ValidationFindingRepository,
        organization_bootstrap: OrganizationBootstrapPort,
        evidence_report_builder: ValidationEvidenceReportBuilder | None = None,
    ) -> None:
        self._run_validation = run_validation
        self._guest_context_builder = guest_context_builder
        self._document_repository = document_repository
        self._validation_run_repository = validation_run_repository
        self._validation_finding_repository = validation_finding_repository
        self._organization_bootstrap = organization_bootstrap
        self._evidence_report_builder = evidence_report_builder or ValidationEvidenceReportBuilder(
            get_settings()
        )

    async def execute(self, command: RunPersistedValidationCommand) -> ValidationRunRecord:
        from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store

        ephemeral = get_guest_ephemeral_store().get(command.document_id)
        if ephemeral is not None:
            return await self._execute_guest_ephemeral(command, ephemeral)

        document = await self._document_repository.get_by_id(command.document_id)
        if document is None:
            raise DocumentNotFoundError(command.document_id)

        supporting_documents = await self._load_supporting_documents(command.supporting_document_ids)

        bundle = await self._guest_context_builder.build(
            document_id=command.document_id,
            organization_id=document.organization_id,
            employee_id=command.employee_id,
        )
        report = self._run_validation.execute(bundle.command)

        organization_id = document.organization_id or bundle.organization_id
        await self._organization_bootstrap.ensure_demo_organization(organization_id)

        enrichment = self._evidence_report_builder.build(
            payslip_document=document,
            supporting_documents=supporting_documents,
            report=report,
            locale=command.locale,
            extraction_connected=bundle.extraction_connected,
            core_fields_usable=bundle.core_fields_usable,
        )

        run_record = report_to_run_record(
            report=report,
            document_id=document.id,
            organization_id=organization_id,
            employee_id=command.employee_id,
        )
        run_record.enrichment = enrichment
        run_record.context_snapshot = enrichment.to_context_snapshot()
        run_record.extraction_id = command.extraction_id or bundle.extraction_id

        finding_records = report_to_finding_records(report, run_record.id)

        saved_run = await self._validation_run_repository.save(run_record)
        saved_findings = await self._validation_finding_repository.save_all(
            saved_run.id,
            finding_records,
        )
        saved_run.findings = saved_findings
        saved_run.enrichment = enrichment
        return saved_run

    async def _execute_guest_ephemeral(self, command: RunPersistedValidationCommand, ephemeral) -> ValidationRunRecord:
        """Run validation for guest landing without permanent S3/DB writes."""
        from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store

        store = get_guest_ephemeral_store()
        document = store.build_document(ephemeral)
        supporting_documents = []
        support_ids = tuple(command.supporting_document_ids) or tuple(ephemeral.supporting_document_ids)
        for sid in support_ids:
            support = store.get_supporting(sid)
            if support is not None:
                supporting_documents.append(store.build_supporting_document(support))

        bundle = await self._guest_context_builder.build(
            document_id=command.document_id,
            organization_id=document.organization_id,
            employee_id=command.employee_id,
            require_confirmed=True,
        )
        report = self._run_validation.execute(bundle.command)

        enrichment = self._evidence_report_builder.build(
            payslip_document=document,
            supporting_documents=supporting_documents,
            report=report,
            locale=command.locale,
            extraction_connected=bundle.extraction_connected,
            core_fields_usable=bundle.core_fields_usable,
        )

        run_record = report_to_run_record(
            report=report,
            document_id=document.id,
            organization_id=document.organization_id or bundle.organization_id,
            employee_id=command.employee_id,
        )
        # Guest runs are returned in-memory only — never persisted.
        run_record.enrichment = enrichment
        run_record.context_snapshot = enrichment.to_context_snapshot()
        run_record.extraction_id = command.extraction_id or bundle.extraction_id
        finding_records = report_to_finding_records(report, run_record.id)
        run_record.findings = finding_records
        return run_record

    async def _load_supporting_documents(self, document_ids: tuple[UUID, ...]):
        from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store
        from payroll_copilot.domain.entities import Document

        store = get_guest_ephemeral_store()
        documents: list[Document] = []
        for document_id in document_ids:
            support = store.get_supporting(document_id)
            if support is not None:
                documents.append(store.build_supporting_document(support))
                continue
            document = await self._document_repository.get_by_id(document_id)
            if document is not None:
                documents.append(document)
        return documents


class GetValidationRunUseCase:
    """Load a persisted validation run and its findings."""

    def __init__(
        self,
        validation_run_repository: ValidationRunRepository,
        validation_finding_repository: ValidationFindingRepository,
    ) -> None:
        self._validation_run_repository = validation_run_repository
        self._validation_finding_repository = validation_finding_repository

    async def execute(self, validation_run_id: UUID) -> ValidationRunRecord | None:
        run = await self._validation_run_repository.get_by_id(validation_run_id)
        if run is None:
            return None

        run.findings = await self._validation_finding_repository.list_by_run_id(validation_run_id)
        return run


__all__ = [
    "ExtractionRequiredError",
    "GetValidationRunUseCase",
    "RunPersistedValidationCommand",
    "RunPersistedValidationUseCase",
]
