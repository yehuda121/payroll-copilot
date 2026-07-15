"""Confirm an employee extraction version before deterministic validation."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from payroll_copilot.application.exceptions import (
    ConfirmationBlockedError,
    DocumentNotFoundError,
    DocumentNotOwnedError,
)
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository
from payroll_copilot.application.ports.repositories import DocumentExtractionRepository, DocumentRepository
from payroll_copilot.application.services.employee_document_lifecycle import (
    CONFIRMATION_CONFIRMED,
    LIFECYCLE_CONFIRMED,
    fields_from_structured,
)
from payroll_copilot.application.services.payslip_identity_comparison import (
    PayslipIdentityComparisonService,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import _fields_from_structured
from payroll_copilot.domain.entities import Employee
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConfirmEmployeeExtractionUseCase:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        audit_logs: AuditLogRepository | None = None,
        comparison: PayslipIdentityComparisonService | None = None,
    ) -> None:
        self._documents = documents
        self._extractions = extractions
        self._audit = audit_logs
        self._comparison = comparison or PayslipIdentityComparisonService()

    async def execute(
        self,
        *,
        document_id: UUID,
        employee: Employee,
        user_id: UUID,
        national_id_encrypted: bytes | None,
        acknowledgement: bool,
    ) -> dict:
        if not acknowledgement:
            raise ConfirmationBlockedError(
                code="confirmation_acknowledgement_required",
                message="Explicit confirmation acknowledgement is required.",
            )
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if document.employee_id != employee.id or document.organization_id != employee.organization_id:
            raise DocumentNotOwnedError(document_id)

        latest = await self._extractions.get_latest_for_document(document_id)
        if latest is None:
            raise ConfirmationBlockedError(
                code="extraction_required",
                message="No extraction is available to confirm.",
            )

        meta = dict(document.metadata or {})
        selected_year = int(meta.get("selected_period_year") or (document.period.year if document.period else 0))
        selected_month = int(
            meta.get("selected_period_month") or (document.period.month if document.period else 0)
        )
        settings = get_settings()
        plaintext = decrypt_national_id(
            national_id_encrypted,
            encryption_key=settings.encryption_key,
        )
        masked = (employee.metadata or {}).get("national_id_masked")
        display_name = (employee.metadata or {}).get("verified_display_name") or (
            f"{employee.first_name} {employee.last_name}"
        )
        fields, _ = _fields_from_structured(latest.structured_data or {})
        comparison = self._comparison.compare(
            trusted_full_name=str(display_name),
            trusted_employee_number=employee.employee_number,
            trusted_national_id_plaintext=plaintext,
            trusted_national_id_masked=masked if isinstance(masked, str) else None,
            selected_year=selected_year or 0,
            selected_month=selected_month or 0,
            extraction_fields=fields,
        )
        if comparison.blocks_confirmation:
            if comparison.identity_check.blocks_confirmation:
                raise ConfirmationBlockedError(
                    code="national_id_mismatch",
                    message="National ID mismatch blocks confirmation.",
                )
            raise ConfirmationBlockedError(
                code="payroll_period_mismatch",
                message="Payroll period mismatch blocks confirmation.",
            )

        now = _utcnow()
        latest.confirmation_status = CONFIRMATION_CONFIRMED
        latest.confirmed_at = now
        latest.confirmed_by = user_id
        await self._extractions.save(latest)

        meta["lifecycle_status"] = LIFECYCLE_CONFIRMED
        meta["confirmed_extraction_id"] = str(latest.id)
        meta["confirmed_extraction_version"] = latest.extraction_version
        document.metadata = meta
        await self._documents.save(document)

        if self._audit is not None:
            await self._audit.append(
                AuditLogEntry(
                    action="employee_extraction_confirmed",
                    resource_type="document_extraction",
                    resource_id=latest.id,
                    organization_id=employee.organization_id,
                    user_id=user_id,
                    details={
                        "event": "extraction_confirmed",
                        "document_id": str(document_id),
                        "extraction_version": latest.extraction_version,
                    },
                )
            )

        return {
            "document_id": str(document_id),
            "extraction_id": str(latest.id),
            "extraction_version": latest.extraction_version,
            "confirmation_status": latest.confirmation_status,
            "confirmed_at": latest.confirmed_at.isoformat() if latest.confirmed_at else None,
            "lifecycle_status": LIFECYCLE_CONFIRMED,
            "fields": fields_from_structured(latest.structured_data),
            "blocks_confirmation": False,
        }
