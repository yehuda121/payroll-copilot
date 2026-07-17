"""Guest validation context from ephemeral store or persisted extractions."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from payroll_copilot.application.ports.repositories import DocumentExtractionRepository
from payroll_copilot.application.services.guest_ephemeral_store import get_guest_ephemeral_store
from payroll_copilot.application.use_cases.validation import RunValidationCommand
from payroll_copilot.application.validation.structured_payslip_mapper import (
    MappedValidationInputs,
    map_structured_payslip_to_validation_inputs,
)


class ExtractionRequiredError(Exception):
    """Raised when guest validation needs a completed parser extraction."""

    def __init__(self, document_id: UUID, message: str) -> None:
        self.document_id = document_id
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class GuestValidationBundle:
    command: RunValidationCommand
    organization_id: UUID
    document_id: UUID
    extraction_id: UUID
    extraction_connected: bool
    core_fields_usable: bool
    mapping_warnings: tuple[str, ...] = ()
    guest_ephemeral: bool = False


class GuestExtractionValidationContextBuilder:
    """Builds ValidationContext inputs from ephemeral guest session or DB extraction.

    Does not use DemoValidationContextBuilder. Does not consume raw OCR text.
    """

    def __init__(self, extraction_repository: DocumentExtractionRepository) -> None:
        self._extractions = extraction_repository

    async def build(
        self,
        *,
        document_id: UUID,
        organization_id: UUID | None,
        employee_id: UUID | None = None,
        require_confirmed: bool = False,
    ) -> GuestValidationBundle:
        ephemeral = get_guest_ephemeral_store().get(document_id)
        if ephemeral is not None:
            if ephemeral.parser_status != "completed":
                raise ExtractionRequiredError(
                    document_id,
                    "Payslip details are not ready for validation yet.",
                )
            if require_confirmed and ephemeral.confirmation_status != "confirmed":
                raise ExtractionRequiredError(
                    document_id,
                    "Confirm extracted fields before running validation.",
                )
            mapped: MappedValidationInputs = map_structured_payslip_to_validation_inputs(
                document_id=document_id,
                structured_data=ephemeral.structured_data or {},
                employee_id=employee_id,
                organization_id=organization_id,
                parser_completed=True,
            )
            return GuestValidationBundle(
                command=mapped.command,
                organization_id=mapped.organization_id,
                document_id=document_id,
                extraction_id=ephemeral.extraction_id,
                extraction_connected=mapped.extraction_connected,
                core_fields_usable=mapped.core_fields_usable,
                mapping_warnings=mapped.mapping_warnings,
                guest_ephemeral=True,
            )

        extraction = await self._extractions.get_latest_for_document(document_id)
        if extraction is None:
            raise ExtractionRequiredError(
                document_id,
                "No extraction found for this document. Complete review first.",
            )
        if extraction.parser_status != "completed":
            raise ExtractionRequiredError(
                document_id,
                "Payslip details are not ready for validation yet.",
            )

        mapped = map_structured_payslip_to_validation_inputs(
            document_id=document_id,
            structured_data=extraction.structured_data or {},
            employee_id=employee_id,
            organization_id=organization_id,
            parser_completed=True,
        )
        return GuestValidationBundle(
            command=mapped.command,
            organization_id=mapped.organization_id,
            document_id=document_id,
            extraction_id=extraction.id,
            extraction_connected=mapped.extraction_connected,
            core_fields_usable=mapped.core_fields_usable,
            mapping_warnings=mapped.mapping_warnings,
            guest_ephemeral=False,
        )
