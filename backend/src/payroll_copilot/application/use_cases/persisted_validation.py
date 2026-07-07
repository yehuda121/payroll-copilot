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
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DemoValidationContextBuilder,
)
from payroll_copilot.infrastructure.config.settings import get_settings


@dataclass(frozen=True, slots=True)
class RunPersistedValidationCommand:
    document_id: UUID
    employee_id: UUID | None = None
    include_historical: bool = True
    include_contract_rag: bool = True
    supporting_document_ids: tuple[UUID, ...] = field(default_factory=tuple)


class RunPersistedValidationUseCase:
    """Run deterministic validation and persist the run and findings to PostgreSQL."""

    def __init__(
        self,
        run_validation: RunValidationUseCase,
        demo_context_builder: DemoValidationContextBuilder,
        document_repository: DocumentRepository,
        validation_run_repository: ValidationRunRepository,
        validation_finding_repository: ValidationFindingRepository,
        organization_bootstrap: OrganizationBootstrapPort,
        evidence_report_builder: ValidationEvidenceReportBuilder | None = None,
    ) -> None:
        self._run_validation = run_validation
        self._demo_context_builder = demo_context_builder
        self._document_repository = document_repository
        self._validation_run_repository = validation_run_repository
        self._validation_finding_repository = validation_finding_repository
        self._organization_bootstrap = organization_bootstrap
        self._evidence_report_builder = evidence_report_builder or ValidationEvidenceReportBuilder(
            get_settings()
        )

    async def execute(self, command: RunPersistedValidationCommand) -> ValidationRunRecord:
        document = await self._document_repository.get_by_id(command.document_id)
        if document is None:
            raise DocumentNotFoundError(command.document_id)

        supporting_documents = await self._load_supporting_documents(command.supporting_document_ids)

        bundle = self._demo_context_builder.build(command.document_id, command.employee_id)
        report = self._run_validation.execute(bundle.command)

        organization_id = document.organization_id or bundle.organization_id
        await self._organization_bootstrap.ensure_demo_organization(organization_id)

        enrichment = self._evidence_report_builder.build(
            payslip_document=document,
            supporting_documents=supporting_documents,
            report=report,
        )

        run_record = report_to_run_record(
            report=report,
            document_id=document.id,
            organization_id=organization_id,
            employee_id=None,
        )
        run_record.enrichment = enrichment
        run_record.context_snapshot = enrichment.to_context_snapshot()

        finding_records = report_to_finding_records(report, run_record.id)

        saved_run = await self._validation_run_repository.save(run_record)
        saved_findings = await self._validation_finding_repository.save_all(
            saved_run.id,
            finding_records,
        )
        saved_run.findings = saved_findings
        saved_run.enrichment = enrichment
        return saved_run

    async def _load_supporting_documents(self, document_ids: tuple[UUID, ...]) -> list[Document]:
        documents: list[Document] = []
        for document_id in document_ids:
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
