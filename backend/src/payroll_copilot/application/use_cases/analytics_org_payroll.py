"""Organization payroll analytics for accountant dashboards (on-demand)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from uuid import UUID

from payroll_copilot.application.dto.analytics import (
    ConfidenceMonthPoint,
    ErrorTypeBucket,
    OrgPayrollAnalytics,
    OutcomeMonthPoint,
    ValidationFailureMonthPoint,
)
from payroll_copilot.application.ports.employee_audit import EmployeeListFilter, EmployeeRepository
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationFindingRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.services.analytics.aggregation import average, sorted_period_keys, top_n
from payroll_copilot.application.services.analytics.document_outcomes import (
    DocumentOutcome,
    classify_document_outcome,
)
from payroll_copilot.application.services.analytics.period_keys import (
    matches_year,
    period_from_document,
)
from payroll_copilot.domain.enums import DocumentType


class GetOrgPayrollAnalyticsUseCase:
    """Documents, outcomes, validation, and confidence by payroll period."""

    metric_name = "org.payroll"

    def __init__(
        self,
        *,
        employees: EmployeeRepository,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        validation_runs: ValidationRunRepository,
        validation_findings: ValidationFindingRepository,
        top_failures_limit: int = 10,
    ) -> None:
        self._employees = employees
        self._documents = documents
        self._extractions = extractions
        self._runs = validation_runs
        self._findings = validation_findings
        self._top_failures_limit = top_failures_limit

    async def execute(
        self,
        *,
        organization_id: UUID,
        year: int,
    ) -> OrgPayrollAnalytics:
        employees = await self._employees.list(
            EmployeeListFilter(organization_id=organization_id, limit=10_000, offset=0)
        )
        docs = []
        for employee in employees:
            docs.extend(
                await self._documents.list_for_employee(
                    organization_id=organization_id,
                    employee_id=employee.id,
                )
            )

        payslips = [d for d in docs if d.document_type == DocumentType.PAYSLIP]
        missing_period = sum(1 for d in payslips if period_from_document(d) is None)
        available_years = sorted(
            {
                p.year
                for d in payslips
                if (p := period_from_document(d)) is not None
            }
            | {year, datetime.utcnow().year},
            reverse=True,
        )

        year_docs = [
            d
            for d in payslips
            if matches_year(period_from_document(d), year)
        ]

        outcome_counts: dict[tuple[int, int], Counter[str]] = {}
        conf_values: dict[tuple[int, int], list[float]] = {}
        failure_findings: dict[tuple[int, int], int] = {}
        failure_runs: dict[tuple[int, int], int] = {}
        error_counter: Counter[tuple[str, str | None]] = Counter()

        doc_ids = [d.id for d in year_docs]
        latest_runs = await self._runs.list_latest_by_document_ids(doc_ids)

        for doc in year_docs:
            period = period_from_document(doc)
            if period is None:
                continue
            key = (period.year, period.month)
            extraction = await self._extractions.get_latest_for_document(doc.id)
            outcome = classify_document_outcome(doc, extraction)
            bucket = outcome_counts.setdefault(key, Counter())
            bucket["documents_processed"] += 1
            bucket[outcome.value] += 1

            confidence = None
            if extraction is not None and extraction.overall_confidence is not None:
                confidence = float(extraction.overall_confidence)
            run = latest_runs.get(doc.id)
            if confidence is None and run is not None and run.overall_confidence is not None:
                confidence = float(run.overall_confidence)
            if confidence is not None:
                conf_values.setdefault(key, []).append(confidence)

            if run is None:
                continue
            findings = list(run.findings or [])
            if not findings:
                findings = await self._findings.list_by_run_id(run.id)
            if not findings:
                continue
            failure_runs[key] = failure_runs.get(key, 0) + 1
            failure_findings[key] = failure_findings.get(key, 0) + len(findings)
            for finding in findings:
                rule_id = str(finding.rule_id or finding.message_key or "unknown")
                category = (
                    finding.rule_category.value
                    if hasattr(finding.rule_category, "value")
                    else str(finding.rule_category) if finding.rule_category else None
                )
                error_counter[(rule_id, category)] += 1

        period_keys = sorted_period_keys(
            set(outcome_counts) | set(conf_values) | set(failure_findings)
        )

        documents_by_month = [
            OutcomeMonthPoint(
                period_year=y,
                period_month=m,
                documents_processed=int(outcome_counts.get((y, m), Counter()).get("documents_processed", 0)),
                success=int(outcome_counts.get((y, m), Counter()).get(DocumentOutcome.SUCCESS.value, 0)),
                review_required=int(
                    outcome_counts.get((y, m), Counter()).get(DocumentOutcome.REVIEW_REQUIRED.value, 0)
                ),
                failed=int(outcome_counts.get((y, m), Counter()).get(DocumentOutcome.FAILED.value, 0)),
            )
            for y, m in period_keys
        ]

        validation_failures_by_month = [
            ValidationFailureMonthPoint(
                period_year=y,
                period_month=m,
                failure_count=int(failure_findings.get((y, m), 0)),
                runs_with_failures=int(failure_runs.get((y, m), 0)),
            )
            for y, m in period_keys
            if (y, m) in failure_findings
        ]

        error_type_distribution = [
            ErrorTypeBucket(key=rule_id, count=count, category=category)
            for (rule_id, category), count in sorted(
                error_counter.items(), key=lambda item: (-item[1], item[0][0])
            )
        ]
        top_validation_failures = [
            ErrorTypeBucket(key=str(rule_id), count=count, category=category)
            for (rule_id, category), count in top_n(error_counter, limit=self._top_failures_limit)
        ]

        average_confidence_by_month = [
            ConfidenceMonthPoint(
                period_year=y,
                period_month=m,
                average_confidence=average(conf_values.get((y, m), [])),
                sample_count=len(conf_values.get((y, m), [])),
            )
            for y, m in period_keys
            if (y, m) in conf_values
        ]

        return OrgPayrollAnalytics(
            organization_id=organization_id,
            year=year,
            documents_by_month=documents_by_month,
            validation_failures_by_month=validation_failures_by_month,
            error_type_distribution=error_type_distribution,
            top_validation_failures=top_validation_failures,
            average_confidence_by_month=average_confidence_by_month,
            documents_missing_period=missing_period,
            available_years=available_years,
        )

    async def compute(self, context):
        if context.organization_id is None or context.year is None:
            raise ValueError("organization_id and year are required")
        return await self.execute(
            organization_id=context.organization_id,
            year=int(context.year),
        )
