"""Load confirmed employment terms for an authorized employee."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    CONFIRMATION_CONFIRMED,
)
from payroll_copilot.domain.employment_terms import (
    ConfirmedEmploymentTerms,
    select_terms_for_period,
    terms_from_structured,
)
from payroll_copilot.domain.enums import DocumentType


class ConfirmedEmploymentTermsLoader:
    """Server-side loader — never trusts client-supplied contract IDs as authority."""

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
    ) -> None:
        self._documents = documents
        self._extractions = extractions

    async def load_for_employee_period(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        period_year: int | None,
        period_month: int | None,
    ) -> ConfirmedEmploymentTerms | None:
        try:
            docs = await self._documents.list_for_employee(
                organization_id=organization_id,
                employee_id=employee_id,
            )
        except NotImplementedError:
            return None

        candidates: list[ConfirmedEmploymentTerms] = []
        for doc in docs:
            if doc.document_type != DocumentType.CONTRACT:
                continue
            if doc.organization_id != organization_id or doc.employee_id != employee_id:
                continue
            extraction = await self._extractions.get_latest_for_document(doc.id)
            if extraction is None:
                continue
            if (extraction.confirmation_status or "") != CONFIRMATION_CONFIRMED:
                continue
            terms = terms_from_structured(
                extraction.structured_data,
                source_document_id=doc.id,
                source_extraction_id=extraction.id,
                confirmed_at=extraction.confirmed_at,
            )
            if not terms.has_any_terms:
                continue
            candidates.append(terms)

        if not candidates:
            return None
        if period_year and period_month:
            return select_terms_for_period(
                candidates, year=int(period_year), month=int(period_month)
            )
        # No payslip period: only safe when exactly one confirmed version.
        if len(candidates) == 1:
            return candidates[0]
        return None
