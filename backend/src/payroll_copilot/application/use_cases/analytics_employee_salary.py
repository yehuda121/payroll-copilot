"""Employee salary analytics from existing payslip documents + extractions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from payroll_copilot.application.dto.analytics import EmployeeSalaryAnalytics, SalaryMonthPoint
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
)
from payroll_copilot.application.services.analytics.period_keys import (
    matches_year,
    period_from_document,
)
from payroll_copilot.application.services.analytics.salary_values import salary_amounts_from_sources
from payroll_copilot.application.services.employee_document_lifecycle import (
    is_employee_visible_document,
)
from payroll_copilot.domain.enums import DocumentType


class GetEmployeeSalaryAnalyticsUseCase:
    """Net/gross by payroll month for one employee (on-demand)."""

    metric_name = "employee.salary"

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
    ) -> None:
        self._documents = documents
        self._extractions = extractions

    async def execute(
        self,
        *,
        organization_id: UUID,
        employee_id: UUID,
        year: int,
        include_unpublished: bool = False,
    ) -> EmployeeSalaryAnalytics:
        docs = await self._documents.list_for_employee(
            organization_id=organization_id,
            employee_id=employee_id,
        )
        if not include_unpublished:
            docs = [doc for doc in docs if is_employee_visible_document(doc)]

        payslips = [
            doc
            for doc in docs
            if doc.document_type == DocumentType.PAYSLIP
        ]
        missing_period = sum(1 for doc in payslips if period_from_document(doc) is None)
        years = sorted(
            {
                p.year
                for doc in payslips
                if (p := period_from_document(doc)) is not None
            }
            | {year, datetime.utcnow().year},
            reverse=True,
        )

        # Newest first so last write into month map wins for tie-break without grouping by created_at.
        ordered = sorted(
            payslips,
            key=lambda d: (
                d.period.year if d.period else 0,
                d.period.month if d.period else 0,
                d.created_at.timestamp() if d.created_at else 0.0,
            ),
        )

        by_month: dict[int, SalaryMonthPoint] = {}
        for doc in ordered:
            period = period_from_document(doc)
            if not matches_year(period, year) or period is None:
                continue
            extraction = await self._extractions.get_latest_for_document(doc.id)
            structured = extraction.structured_data if extraction else None
            net, gross, currency = salary_amounts_from_sources(
                structured_data=structured,
                document_metadata=dict(doc.metadata or {}),
            )
            by_month[period.month] = SalaryMonthPoint(
                period_year=period.year,
                period_month=period.month,
                net_salary=net,
                gross_salary=gross,
                currency=currency,
                document_id=doc.id,
                extraction_id=extraction.id if extraction else None,
            )

        months = [by_month[m] for m in sorted(by_month)]
        return EmployeeSalaryAnalytics(
            employee_id=employee_id,
            organization_id=organization_id,
            year=year,
            months=months,
            available_years=years,
            documents_missing_period=missing_period,
        )

    async def compute(self, context):  # AnalyticsContext — duck-typed for registry
        if context.organization_id is None or context.employee_id is None or context.year is None:
            raise ValueError("organization_id, employee_id, and year are required")
        return await self.execute(
            organization_id=context.organization_id,
            employee_id=context.employee_id,
            year=int(context.year),
            include_unpublished=bool(context.params.get("include_unpublished", False)),
        )
