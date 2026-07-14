"""Employee validation gate — ownership + trusted identity/period checks before rules run."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.exceptions import (
    ConfirmationBlockedError,
    DocumentNotFoundError,
    DocumentNotOwnedError,
)
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository
from payroll_copilot.application.ports.repositories import DocumentExtractionRepository, DocumentRepository
from payroll_copilot.application.services.payslip_identity_comparison import (
    PayslipComparisonResult,
    PayslipIdentityComparisonService,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import _fields_from_structured
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmployeeValidationResult:
    record: ValidationRunRecord
    comparison: PayslipComparisonResult


class ValidateEmployeePayslipUseCase:
    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        validation: RunPersistedValidationUseCase,
        audit_logs: AuditLogRepository | None = None,
        comparison: PayslipIdentityComparisonService | None = None,
    ) -> None:
        self._documents = documents
        self._extractions = extractions
        self._validation = validation
        self._audit = audit_logs
        self._comparison = comparison or PayslipIdentityComparisonService()

    async def execute(
        self,
        *,
        document_id: UUID,
        employee: Employee,
        user_id: UUID,
        national_id_encrypted: bytes | None,
        supporting_document_ids: tuple[UUID, ...] = (),
        locale: str = "he",
    ) -> EmployeeValidationResult:
        document = await self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        if document.employee_id != employee.id or document.organization_id != employee.organization_id:
            raise DocumentNotOwnedError(document_id)

        latest = await self._extractions.get_latest_for_document(document_id)
        if latest is None:
            raise ConfirmationBlockedError(
                code="correction_not_allowed",
                message="Document has no extraction to confirm.",
            )

        meta = dict(document.metadata or {})
        selected_year = int(meta.get("selected_period_year") or (document.period.year if document.period else 0))
        selected_month = int(
            meta.get("selected_period_month") or (document.period.month if document.period else 0)
        )
        if not selected_year or not selected_month:
            raise ConfirmationBlockedError(
                code="correction_not_allowed",
                message="Document is missing a selected payroll period.",
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
            selected_year=selected_year,
            selected_month=selected_month,
            extraction_fields=fields,
        )

        if comparison.identity_check.blocks_confirmation:
            await self._audit_blocked(document_id, employee, user_id, comparison, "national_id_mismatch")
            raise ConfirmationBlockedError(
                code="national_id_mismatch",
                message="National ID mismatch blocks confirmation and validation.",
            )
        if comparison.period_check.blocks_confirmation:
            await self._audit_blocked(document_id, employee, user_id, comparison, "payroll_period_mismatch")
            raise ConfirmationBlockedError(
                code="payroll_period_mismatch",
                message="Payroll period mismatch blocks confirmation and validation.",
            )

        record = await self._validation.execute(
            RunPersistedValidationCommand(
                document_id=document_id,
                employee_id=employee.id,
                include_historical=True,
                include_contract_rag=True,
                supporting_document_ids=supporting_document_ids,
                locale=locale,
            )
        )
        if self._audit is not None:
            await self._audit.append(
                AuditLogEntry(
                    action="employee_payslip_validated",
                    resource_type="document",
                    resource_id=document_id,
                    organization_id=employee.organization_id,
                    user_id=user_id,
                    details={
                        "event": "employee_payslip_validated",
                        "validation_run_id": str(record.id),
                        "identity_overall": comparison.identity_check.overall,
                        "period_status": comparison.period_check.status,
                    },
                )
            )
        return EmployeeValidationResult(record=record, comparison=comparison)

    async def _audit_blocked(
        self,
        document_id: UUID,
        employee: Employee,
        user_id: UUID,
        comparison: PayslipComparisonResult,
        code: str,
    ) -> None:
        logger.info(
            "employee_validation_blocked document_id=%s code=%s",
            document_id,
            code,
        )
        if self._audit is None:
            return
        details: dict[str, Any] = {
            "event": "validation_blocked",
            "code": code,
            "identity_overall": comparison.identity_check.overall,
            "period_status": comparison.period_check.status,
        }
        await self._audit.append(
            AuditLogEntry(
                action="validation_blocked",
                resource_type="document",
                resource_id=document_id,
                organization_id=employee.organization_id,
                user_id=user_id,
                details=details,
            )
        )
