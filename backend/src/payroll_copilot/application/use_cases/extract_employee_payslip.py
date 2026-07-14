"""Employee payslip extraction — reuses guest OCR/parser persistence with binding."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from payroll_copilot.application.exceptions import DuplicatePayslipPeriodError
from payroll_copilot.application.ports.employee_audit import AuditLogEntry, AuditLogRepository, EmployeeRepository
from payroll_copilot.application.ports.repositories import DocumentExtractionRepository, DocumentRepository
from payroll_copilot.application.services.payslip_identity_comparison import (
    PayslipComparisonResult,
    PayslipIdentityComparisonService,
    parse_pay_period,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractedFieldView,
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
    GuestPayslipExtractionResult,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.security.field_crypto import decrypt_national_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmployeePayslipExtractionCommand:
    content: bytes
    original_filename: str
    mime_type: str
    language: str
    period_year: int
    period_month: int
    employee: Employee
    user_id: UUID
    national_id_encrypted: bytes | None
    confirm_new_version: bool = False


@dataclass(frozen=True, slots=True)
class EmployeePayslipExtractionResult:
    extraction: GuestPayslipExtractionResult
    comparison: PayslipComparisonResult
    document_version: int


class ExtractEmployeePayslipUseCase:
    def __init__(
        self,
        *,
        guest_extract: ExtractGuestPayslipUseCase,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        employees: EmployeeRepository,
        audit_logs: AuditLogRepository | None = None,
        comparison: PayslipIdentityComparisonService | None = None,
    ) -> None:
        self._guest = guest_extract
        self._documents = documents
        self._extractions = extractions
        self._employees = employees
        self._audit = audit_logs
        self._comparison = comparison or PayslipIdentityComparisonService()

    async def execute(self, command: EmployeePayslipExtractionCommand) -> EmployeePayslipExtractionResult:
        employee = command.employee
        existing = await self._documents.find_payslip_for_period(
            organization_id=employee.organization_id,
            employee_id=employee.id,
            period_year=command.period_year,
            period_month=command.period_month,
        )
        if existing is not None and not command.confirm_new_version:
            latest = await self._extractions.get_latest_for_document(existing.id)
            uploaded_at = existing.created_at.isoformat() if existing.created_at else None
            raise DuplicatePayslipPeriodError(
                existing_document_id=existing.id,
                existing_version=latest.extraction_version if latest else None,
                uploaded_at=uploaded_at,
            )

        metadata_extra: dict[str, Any] = {
            "owner_user_id": str(command.user_id),
            "selected_period_year": command.period_year,
            "selected_period_month": command.period_month,
        }
        if existing is not None and command.confirm_new_version:
            metadata_extra["supersedes_document_id"] = str(existing.id)
            metadata_extra["document_version_action"] = "explicit_new_version"

        guest_result = await self._guest.execute(
            GuestPayslipExtractionCommand(
                content=command.content,
                original_filename=command.original_filename,
                mime_type=command.mime_type,
                language=command.language,
                employee_id=employee.id,
                organization_id=employee.organization_id,
                uploaded_by=command.user_id,
                period_year=command.period_year,
                period_month=command.period_month,
                confirm_new_version=command.confirm_new_version,
                metadata_extra=metadata_extra,
            )
        )

        # Persist extracted period separately without overwriting selected period columns.
        document = await self._documents.get_by_id(guest_result.document_id)
        if document is not None:
            extracted_year, extracted_month = self._extracted_period(guest_result.fields)
            meta = dict(document.metadata or {})
            meta["selected_period_year"] = command.period_year
            meta["selected_period_month"] = command.period_month
            if extracted_year is not None:
                meta["extracted_period_year"] = extracted_year
            if extracted_month is not None:
                meta["extracted_period_month"] = extracted_month
            document.metadata = meta
            await self._documents.save(document)

        comparison = self._run_comparison(command, guest_result.fields)
        await self._audit_extract(command, guest_result, comparison)

        latest = await self._extractions.get_latest_for_document(guest_result.document_id)
        version = latest.extraction_version if latest else 1
        return EmployeePayslipExtractionResult(
            extraction=guest_result,
            comparison=comparison,
            document_version=version,
        )

    def _run_comparison(
        self,
        command: EmployeePayslipExtractionCommand,
        fields: list[ExtractedFieldView],
    ) -> PayslipComparisonResult:
        settings = get_settings()
        plaintext = decrypt_national_id(
            command.national_id_encrypted,
            encryption_key=settings.encryption_key,
        )
        masked = (command.employee.metadata or {}).get("national_id_masked")
        display_name = (command.employee.metadata or {}).get("verified_display_name") or (
            f"{command.employee.first_name} {command.employee.last_name}"
        )
        return self._comparison.compare(
            trusted_full_name=str(display_name),
            trusted_employee_number=command.employee.employee_number,
            trusted_national_id_plaintext=plaintext,
            trusted_national_id_masked=masked if isinstance(masked, str) else None,
            selected_year=command.period_year,
            selected_month=command.period_month,
            extraction_fields=fields,
        )

    @staticmethod
    def _extracted_period(fields: list[ExtractedFieldView]) -> tuple[int | None, int | None]:
        for field in fields:
            if field.key == "pay_period":
                return parse_pay_period(field.value)
        return None, None

    async def _audit_extract(
        self,
        command: EmployeePayslipExtractionCommand,
        result: GuestPayslipExtractionResult,
        comparison: PayslipComparisonResult,
    ) -> None:
        if self._audit is None:
            return
        details: dict[str, Any] = {
            "event": "employee_payslip_uploaded",
            "document_id": str(result.document_id),
            "period_year": command.period_year,
            "period_month": command.period_month,
            "identity_overall": comparison.identity_check.overall,
            "period_status": comparison.period_check.status,
            "blocks_confirmation": comparison.blocks_confirmation,
            "confirm_new_version": command.confirm_new_version,
        }
        if comparison.identity_check.blocks_confirmation:
            details["identity_mismatch_detected"] = True
            logger.info(
                "employee_identity_mismatch document_id=%s employee_number=%s",
                result.document_id,
                command.employee.employee_number,
            )
        if comparison.period_check.blocks_confirmation:
            details["period_mismatch_detected"] = True
            logger.info(
                "employee_period_mismatch document_id=%s selected=%s-%s",
                result.document_id,
                command.period_year,
                command.period_month,
            )
        await self._audit.append(
            AuditLogEntry(
                action="employee_payslip_uploaded",
                resource_type="document",
                resource_id=result.document_id,
                organization_id=command.employee.organization_id,
                user_id=command.user_id,
                details=details,
            )
        )
        if command.confirm_new_version:
            await self._audit.append(
                AuditLogEntry(
                    action="duplicate_payslip_version_confirmed",
                    resource_type="document",
                    resource_id=result.document_id,
                    organization_id=command.employee.organization_id,
                    user_id=command.user_id,
                    details={"event": "duplicate_version_confirmed"},
                )
            )
