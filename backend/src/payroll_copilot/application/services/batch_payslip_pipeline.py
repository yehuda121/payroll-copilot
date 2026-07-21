"""Reusable one-payslip pipeline for bulk payroll processing.

Orchestrates the shared Document Model extraction, confirmation, and
deterministic validation use cases used by the Employee Portal. Adds only
batch-specific employee matching and incremental result projection.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.ports.employee_audit import EmployeeRepository
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.application.services.payslip_identity_comparison import (
    parse_pay_period,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractedFieldView,
    ExtractGuestPayslipUseCase,
    GuestPayslipExtractionCommand,
)
from payroll_copilot.application.use_cases.persisted_validation import (
    RunPersistedValidationCommand,
    RunPersistedValidationUseCase,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    LIFECYCLE_ACCOUNTANT_REVIEW,
    PUBLICATION_DRAFT,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import FindingSeverity, ValidationResult
from payroll_copilot.domain.value_objects import PayPeriod
from payroll_copilot.application.services.national_id_privacy import (
    hash_national_id,
    mask_national_id,
)

SlipProgressCallback = Callable[[str, dict[str, Any] | None], None]


@dataclass(frozen=True, slots=True)
class BatchSlipPipelineResult:
    status: str
    document_id: UUID
    processing_stage: str
    employee_number: str | None = None
    employee_name: str | None = None
    national_id_masked: str | None = None
    payroll_year: int | None = None
    payroll_month: int | None = None
    warnings: int = 0
    critical_issues: int = 0
    validation_run_id: UUID | None = None
    error_message: str | None = None


class BatchPayslipPipelineService:
    """Process one split payslip and persist each completed stage immediately."""

    def __init__(
        self,
        *,
        extract: ExtractGuestPayslipUseCase,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        employees: EmployeeRepository,
        validation: RunPersistedValidationUseCase,
    ) -> None:
        self._extract = extract
        self._documents = documents
        self._extractions = extractions
        self._employees = employees
        self._validation = validation

    async def process(
        self,
        *,
        content: bytes,
        original_filename: str,
        organization_id: UUID,
        actor_user_id: UUID,
        language: str = "auto",
        progress: SlipProgressCallback | None = None,
        batch_job_id: str | None = None,
        batch_item_id: str | None = None,
        slip_index: int | None = None,
        source_document_id: str | None = None,
    ) -> BatchSlipPipelineResult:
        batch_metadata = {
            key: value
            for key, value in {
                "source": "accountant_bulk_upload",
                "batch_job_id": batch_job_id,
                "batch_item_id": batch_item_id,
                "batch_slip_index": slip_index,
                "source_batch_document_id": source_document_id,
            }.items()
            if value is not None
        }
        extracted = await self._extract.execute(
            GuestPayslipExtractionCommand(
                content=content,
                original_filename=original_filename,
                mime_type="application/pdf",
                language=language,
                organization_id=organization_id,
                uploaded_by=actor_user_id,
                metadata_extra=batch_metadata,
                ephemeral=False,
                progress_callback=progress,
            )
        )
        if extracted.ocr_status != "completed" or extracted.parser_status != "completed":
            return BatchSlipPipelineResult(
                status="failed",
                document_id=extracted.document_id,
                processing_stage=(
                    "ocr" if extracted.ocr_status != "completed" else "extracting"
                ),
                error_message=extracted.error_message
                or "Payslip OCR or structured extraction failed.",
            )

        self._notify(progress, "matching")
        national_id = self._field_text(
            extracted.fields,
            "national_id",
            "employee_id",
        )
        employee_number = self._field_text(extracted.fields, "employee_number")
        employee = await self._match_employee(
            organization_id=organization_id,
            national_id=national_id,
            employee_number=employee_number,
        )
        year, month = self._pay_period(extracted.fields)
        if employee is None:
            try:
                validation = await self._prepare_and_validate_draft(
                    document_id=extracted.document_id,
                    employee=None,
                    actor_user_id=actor_user_id,
                    period=(year, month),
                    progress=progress,
                )
                warnings, critical = self._finding_counts(validation)
                return BatchSlipPipelineResult(
                    status="unknown_employee",
                    document_id=extracted.document_id,
                    processing_stage="completed",
                    employee_number=employee_number,
                    national_id_masked=mask_national_id(national_id),
                    payroll_year=year,
                    payroll_month=month,
                    warnings=warnings,
                    critical_issues=critical,
                    validation_run_id=validation.id,
                    error_message="No employee matched inside this organization.",
                )
            except Exception as exc:  # noqa: BLE001 - preserve reviewable extraction
                return BatchSlipPipelineResult(
                    status="unknown_employee",
                    document_id=extracted.document_id,
                    processing_stage="validation",
                    employee_number=employee_number,
                    national_id_masked=mask_national_id(national_id),
                    payroll_year=year,
                    payroll_month=month,
                    error_message=(
                        "No employee matched; initial validation failed: "
                        f"{str(exc) or exc.__class__.__name__}"
                    ),
                )

        self._notify(
            progress,
            "matching",
            {
                "employee_number": employee.employee_number,
                "employee_name": self._employee_name(employee),
            },
        )
        try:
            return await self.finalize_document(
                document_id=extracted.document_id,
                employee=employee,
                actor_user_id=actor_user_id,
                progress=progress,
                period=(year, month),
            )
        except Exception as exc:  # noqa: BLE001 - preserve item identity for the batch
            return BatchSlipPipelineResult(
                status="failed",
                document_id=extracted.document_id,
                processing_stage="validation",
                employee_number=employee.employee_number,
                employee_name=self._employee_name(employee),
                national_id_masked=mask_national_id(national_id),
                payroll_year=year,
                payroll_month=month,
                error_message=str(exc) or exc.__class__.__name__,
            )

    async def finalize_document(
        self,
        *,
        document_id: UUID,
        employee: Employee,
        actor_user_id: UUID,
        progress: SlipProgressCallback | None = None,
        period: tuple[int | None, int | None] | None = None,
    ) -> BatchSlipPipelineResult:
        """Provisionally match an extracted document and place it in accountant review."""
        validation = await self._prepare_and_validate_draft(
            document_id=document_id,
            employee=employee,
            actor_user_id=actor_user_id,
            period=period,
            progress=progress,
        )
        document = await self._documents.get_by_id(document_id)
        assert document is not None
        year = document.period.year if document.period else None
        month = document.period.month if document.period else None
        if year is None or month is None:
            return BatchSlipPipelineResult(
                status="failed",
                document_id=document_id,
                processing_stage="extracting",
                employee_number=employee.employee_number,
                employee_name=self._employee_name(employee),
                error_message="The payroll period could not be extracted.",
            )
        return self._result_from_validation(
            document_id=document_id,
            employee=employee,
            period=(year, month),
            record=validation,
        )

    async def _prepare_and_validate_draft(
        self,
        *,
        document_id: UUID,
        employee: Employee | None,
        actor_user_id: UUID,
        period: tuple[int | None, int | None] | None,
        progress: SlipProgressCallback | None,
    ) -> ValidationRunRecord:
        document = await self._documents.get_by_id(document_id)
        latest = await self._extractions.get_latest_for_document(document_id)
        if (
            document is None
            or latest is None
            or (
                employee is not None
                and document.organization_id != employee.organization_id
            )
        ):
            raise ValueError("Batch payslip document or extraction was not found.")

        fields = self._fields_from_extraction(latest.structured_data)
        year, month = period or self._pay_period(fields)
        metadata = dict(document.metadata or {})
        if employee is not None and year is not None and month is not None:
            existing = await self._documents.find_payslip_for_period(
                organization_id=employee.organization_id,
                employee_id=employee.id,
                period_year=year,
                period_month=month,
            )
            if existing is not None and existing.id != document.id:
                metadata["supersedes_document_id"] = str(existing.id)
                metadata["document_version_action"] = "batch_review_version"
        now = datetime.now(UTC).isoformat()
        metadata.update(
            {
                "owner_user_id": str(actor_user_id),
                "source": "accountant_bulk_upload",
                "publication_status": PUBLICATION_DRAFT,
                "review_status": "pending_review",
                "lifecycle_status": LIFECYCLE_ACCOUNTANT_REVIEW,
                "batch_extracted_at": metadata.get("batch_extracted_at") or now,
                "matched_employee_id": str(employee.id) if employee else None,
                "matched_employee_number": employee.employee_number if employee else None,
                "provisional_employee_match": employee is not None,
            }
        )
        if year is not None and month is not None:
            metadata.update(
                {
                    "selected_period_year": year,
                    "selected_period_month": month,
                    "extracted_period_year": year,
                    "extracted_period_month": month,
                }
            )
            document.period = PayPeriod(year=year, month=month)
        document.employee_id = employee.id if employee else None
        document.uploaded_by = actor_user_id
        document.metadata = metadata
        await self._documents.save(document)

        self._notify(progress, "validation")
        validation = await self._validation.execute(
            RunPersistedValidationCommand(
                document_id=document_id,
                employee_id=employee.id if employee else None,
                include_historical=employee is not None,
                include_contract_rag=employee is not None,
                locale="he",
                extraction_id=latest.id,
            )
        )
        metadata = dict(document.metadata or {})
        metadata.update(
            {
                "lifecycle_status": LIFECYCLE_ACCOUNTANT_REVIEW,
                "review_status": "pending_review",
                "latest_validation_run_id": str(validation.id),
                "initial_validation_at": (
                    metadata.get("initial_validation_at") or now
                ),
                "last_validation_at": datetime.now(UTC).isoformat(),
            }
        )
        document.metadata = metadata
        await self._documents.save(document)
        return validation

    async def find_employee_by_national_id(
        self,
        organization_id: UUID,
        national_id: str,
    ) -> Employee | None:
        return await self._employees.get_by_national_id_hash(
            organization_id,
            hash_national_id(national_id),
        )

    async def find_employee_by_number(
        self,
        organization_id: UUID,
        employee_number: str,
    ) -> Employee | None:
        return await self._employees.get_by_number(
            organization_id,
            employee_number.strip(),
        )

    async def _match_employee(
        self,
        *,
        organization_id: UUID,
        national_id: str | None,
        employee_number: str | None,
    ) -> Employee | None:
        if national_id:
            matched = await self.find_employee_by_national_id(
                organization_id,
                national_id,
            )
            if matched is not None:
                return matched
        if employee_number:
            return await self.find_employee_by_number(
                organization_id,
                employee_number,
            )
        return None

    @staticmethod
    def _field_text(
        fields: list[ExtractedFieldView],
        *keys: str,
    ) -> str | None:
        for key in keys:
            field = next((row for row in fields if row.key == key), None)
            if field is None or field.value in (None, ""):
                continue
            value = str(field.value).strip()
            if value:
                return value
        return None

    @classmethod
    def _pay_period(
        cls,
        fields: list[ExtractedFieldView],
    ) -> tuple[int | None, int | None]:
        period = cls._field_text(fields, "pay_period", "period")
        if period:
            year, month = parse_pay_period(period)
            if year is not None and month is not None:
                return year, month
        year = cls._field_text(fields, "period_year", "payroll_year")
        month = cls._field_text(fields, "period_month", "payroll_month")
        try:
            parsed_year = int(year) if year else None
            parsed_month = int(month) if month else None
        except ValueError:
            return None, None
        if (
            parsed_year is not None
            and parsed_month is not None
            and 2000 <= parsed_year <= 2100
            and 1 <= parsed_month <= 12
        ):
            return parsed_year, parsed_month
        return None, None

    @staticmethod
    def _fields_from_extraction(
        structured_data: dict[str, Any],
    ) -> list[ExtractedFieldView]:
        from payroll_copilot.application.use_cases.extract_guest_payslip import (
            _fields_from_structured,
        )

        fields, _ = _fields_from_structured(structured_data or {})
        return fields

    @staticmethod
    def _employee_name(employee: Employee) -> str:
        metadata = employee.metadata or {}
        return str(
            metadata.get("verified_display_name")
            or metadata.get("display_name_en")
            or employee.full_name
        )

    @classmethod
    def _result_from_validation(
        cls,
        *,
        document_id: UUID,
        employee: Employee,
        period: tuple[int, int],
        record: ValidationRunRecord,
    ) -> BatchSlipPipelineResult:
        overall = (
            record.overall_result.value
            if hasattr(record.overall_result, "value")
            else record.overall_result
        )
        status = (
            "passed"
            if overall == ValidationResult.PASS.value
            else "warning"
            if overall == ValidationResult.WARNINGS.value
            else "failed"
        )
        warning_count, critical_count = cls._finding_counts(record)
        return BatchSlipPipelineResult(
            status=status,
            document_id=document_id,
            processing_stage="completed",
            employee_number=employee.employee_number,
            employee_name=cls._employee_name(employee),
            payroll_year=period[0],
            payroll_month=period[1],
            warnings=warning_count,
            critical_issues=critical_count,
            validation_run_id=record.id,
        )

    @staticmethod
    def _finding_counts(record: ValidationRunRecord) -> tuple[int, int]:
        warning_count = sum(
            1
            for finding in record.findings
            if finding.severity == FindingSeverity.WARNING
        )
        critical_count = sum(
            1
            for finding in record.findings
            if finding.severity == FindingSeverity.CRITICAL
        )
        return warning_count, critical_count

    @staticmethod
    def _notify(
        progress: SlipProgressCallback | None,
        stage: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if progress is not None:
            progress(stage, details)
