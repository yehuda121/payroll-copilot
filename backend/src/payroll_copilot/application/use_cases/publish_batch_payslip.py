"""Final accountant approval boundary for bulk-uploaded payslips."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from payroll_copilot.application.exceptions import (
    ConfirmationBlockedError,
    DocumentNotFoundError,
    DocumentNotOwnedError,
)
from payroll_copilot.application.ports.employee_audit import (
    AuditLogEntry,
    AuditLogRepository,
)
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    CONFIRMATION_CONFIRMED,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_SUPERSEDED,
    PUBLICATION_DRAFT,
    PUBLICATION_PUBLISHED,
    is_employee_visible_document,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import DocumentType, ValidationRunStatus


@dataclass(frozen=True, slots=True)
class PublishBatchPayslipResult:
    document_id: UUID
    employee_number: str
    payroll_year: int
    payroll_month: int
    published_at: str
    validation_run_id: UUID


class PublishBatchPayslipUseCase:
    """Publish only a confirmed draft with current persisted validation."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        validation_runs: ValidationRunRepository,
        audit_logs: AuditLogRepository | None = None,
    ) -> None:
        self._documents = documents
        self._extractions = extractions
        self._runs = validation_runs
        self._audit = audit_logs

    async def execute(
        self,
        *,
        document_id: UUID,
        employee: Employee,
        actor_user_id: UUID,
    ) -> PublishBatchPayslipResult:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if (
            document.organization_id != employee.organization_id
            or document.employee_id != employee.id
        ):
            raise DocumentNotOwnedError(document_id)

        metadata = dict(document.metadata or {})
        legacy_batch_draft = (
            metadata.get("source") == "accountant_bulk_upload"
            and metadata.get("publication_status") is None
        )
        if (
            metadata.get("publication_status") != PUBLICATION_DRAFT
            and not legacy_batch_draft
        ):
            raise ConfirmationBlockedError(
                code="batch_draft_required",
                message="Only an accountant-review draft can be published.",
            )
        if document.period is None:
            raise ConfirmationBlockedError(
                code="payroll_period_required",
                message="A payroll period is required before publishing.",
            )

        extraction = await self._extractions.get_latest_for_document(document_id)
        if extraction is None or extraction.confirmation_status != CONFIRMATION_CONFIRMED:
            raise ConfirmationBlockedError(
                code="current_extraction_not_confirmed",
                message="Confirm the current Digital Payslip before publishing.",
            )

        runs = await self._runs.list_for_document(document_id)
        current_run = next(
            (
                run
                for run in runs
                if run.extraction_id == extraction.id
                and run.status == ValidationRunStatus.COMPLETED
            ),
            None,
        )
        if current_run is None:
            raise ConfirmationBlockedError(
                code="current_validation_required",
                message="Run validation for the current Digital Payslip before publishing.",
            )

        published_at = datetime.now(UTC).isoformat()
        await self._supersede_previous_published(
            document=document,
            employee=employee,
        )
        metadata.update(
            {
                "publication_status": PUBLICATION_PUBLISHED,
                "review_status": "approved",
                "lifecycle_status": LIFECYCLE_PUBLISHED,
                "published_at": published_at,
                "published_by": str(actor_user_id),
                "approved_validation_run_id": str(current_run.id),
                "approved_extraction_id": str(extraction.id),
                "provisional_employee_match": False,
            }
        )
        document.metadata = metadata
        await self._documents.save(document)

        if self._audit is not None:
            await self._audit.append(
                AuditLogEntry(
                    action="batch_payslip_published",
                    resource_type="document",
                    resource_id=document.id,
                    organization_id=employee.organization_id,
                    user_id=actor_user_id,
                    details={
                        "employee_number": employee.employee_number,
                        "period_year": document.period.year,
                        "period_month": document.period.month,
                        "validation_run_id": str(current_run.id),
                        "extraction_id": str(extraction.id),
                    },
                )
            )

        return PublishBatchPayslipResult(
            document_id=document.id,
            employee_number=employee.employee_number,
            payroll_year=document.period.year,
            payroll_month=document.period.month,
            published_at=published_at,
            validation_run_id=current_run.id,
        )

    async def _supersede_previous_published(
        self,
        *,
        document,
        employee: Employee,
    ) -> None:
        """Keep only one employee-visible payslip for a payroll month."""
        if document.period is None or document.organization_id is None:
            return
        existing = await self._documents.list_for_employee(
            organization_id=document.organization_id,
            employee_id=employee.id,
        )
        for candidate in existing:
            if candidate.id == document.id:
                continue
            if candidate.document_type != DocumentType.PAYSLIP:
                continue
            if (
                candidate.period is None
                or candidate.period.year != document.period.year
                or candidate.period.month != document.period.month
            ):
                continue
            if not is_employee_visible_document(candidate):
                continue
            metadata = dict(candidate.metadata or {})
            metadata.update(
                {
                    "lifecycle_status": LIFECYCLE_SUPERSEDED,
                    "publication_status": PUBLICATION_DRAFT,
                    "review_status": "superseded",
                    "superseded_by_document_id": str(document.id),
                }
            )
            candidate.metadata = metadata
            await self._documents.save(candidate)
