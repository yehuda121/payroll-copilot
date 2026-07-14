"""Employee extraction corrections with ownership and re-compare."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from payroll_copilot.application.exceptions import (
    CorrectionNotAllowedError,
    DocumentNotFoundError,
    DocumentNotOwnedError,
)
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository
from payroll_copilot.application.ports.repositories import DocumentExtractionRepository, DocumentRepository
from payroll_copilot.application.services.payslip_identity_comparison import (
    PayslipComparisonResult,
    PayslipIdentityComparisonService,
)
from payroll_copilot.application.use_cases.correct_guest_extraction import (
    CorrectExtractionResult,
    CorrectGuestExtractionUseCase,
    FieldCorrection,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CorrectEmployeeExtractionResult:
    correction: CorrectExtractionResult
    comparison: PayslipComparisonResult


class CorrectEmployeeExtractionUseCase:
    def __init__(
        self,
        *,
        guest_correct: CorrectGuestExtractionUseCase,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        audit_logs: AuditLogRepository | None = None,
        comparison: PayslipIdentityComparisonService | None = None,
    ) -> None:
        self._guest = guest_correct
        self._documents = documents
        self._extractions = extractions
        self._audit = audit_logs
        self._comparison = comparison or PayslipIdentityComparisonService()

    async def execute(
        self,
        *,
        document_id: UUID,
        corrections: list[FieldCorrection],
        employee: Employee,
        user_id: UUID,
        national_id_encrypted: bytes | None,
    ) -> CorrectEmployeeExtractionResult:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if document.employee_id != employee.id or document.organization_id != employee.organization_id:
            raise DocumentNotOwnedError(document_id)

        correction = await self._guest.execute(document_id=document_id, corrections=corrections)

        meta = dict(document.metadata or {})
        selected_year = int(meta.get("selected_period_year") or (document.period.year if document.period else 0))
        selected_month = int(
            meta.get("selected_period_month") or (document.period.month if document.period else 0)
        )
        if not selected_year or not selected_month:
            raise CorrectionNotAllowedError(
                "Document is missing a selected payroll period and cannot be corrected."
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
        comparison = self._comparison.compare(
            trusted_full_name=str(display_name),
            trusted_employee_number=employee.employee_number,
            trusted_national_id_plaintext=plaintext,
            trusted_national_id_masked=masked if isinstance(masked, str) else None,
            selected_year=selected_year,
            selected_month=selected_month,
            extraction_fields=correction.fields,
        )

        if self._audit is not None:
            await self._audit.append(
                AuditLogEntry(
                    action="employee_extraction_corrected",
                    resource_type="document",
                    resource_id=document_id,
                    organization_id=employee.organization_id,
                    user_id=user_id,
                    details={
                        "event": "extraction_corrected",
                        "extraction_version": correction.extraction_version,
                        "blocks_confirmation": comparison.blocks_confirmation,
                        "identity_overall": comparison.identity_check.overall,
                        "period_status": comparison.period_check.status,
                        "corrected_keys": [c.key for c in corrections],
                    },
                )
            )
        logger.info(
            "employee_extraction_corrected document_id=%s version=%s blocks=%s",
            document_id,
            correction.extraction_version,
            comparison.blocks_confirmation,
        )
        return CorrectEmployeeExtractionResult(correction=correction, comparison=comparison)
