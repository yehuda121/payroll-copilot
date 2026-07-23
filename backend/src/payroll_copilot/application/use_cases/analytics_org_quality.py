"""Organization AI quality analytics from existing extraction/validation SoT.

On-demand aggregation by payroll period only. No new persistence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from uuid import UUID

from payroll_copilot.application.dto.analytics import (
    OrgQualityAnalytics,
    QualityMonthPoint,
)
from payroll_copilot.application.ports.employee_audit import EmployeeListFilter, EmployeeRepository
from payroll_copilot.application.ports.repositories import (
    DocumentExtractionRepository,
    DocumentRepository,
    ValidationRunRepository,
)
from payroll_copilot.application.services.analytics.aggregation import average, sorted_period_keys
from payroll_copilot.application.services.analytics.confidence_buckets import (
    bucket_confidence_values,
    rate,
)
from payroll_copilot.application.services.analytics.document_outcomes import (
    DocumentOutcome,
    classify_document_outcome,
)
from payroll_copilot.application.services.analytics.period_keys import (
    matches_year,
    period_from_document,
)
from payroll_copilot.application.services.employee_document_lifecycle import (
    CONFIRMATION_REVIEW_REQUIRED,
    LIFECYCLE_ACCOUNTANT_REVIEW,
    LIFECYCLE_REVIEW_REQUIRED,
)
from payroll_copilot.domain.enums import DocumentType, ValidationResult


def _status_value(raw: object | None) -> str:
    if raw is None:
        return ""
    return str(getattr(raw, "value", raw) or "").strip().lower()


def _is_extraction_success(extraction: object | None) -> bool | None:
    """Return True/False when an extraction exists; None when missing."""
    if extraction is None:
        return None
    ocr = _status_value(getattr(extraction, "ocr_status", None))
    parser = _status_value(getattr(extraction, "parser_status", None))
    if not ocr and not parser:
        return None
    return ocr == "completed" and parser == "completed"


def _is_ocr_success(extraction: object | None) -> bool | None:
    if extraction is None:
        return None
    ocr = _status_value(getattr(extraction, "ocr_status", None))
    if not ocr:
        return None
    if ocr == "completed":
        return True
    if ocr == "failed":
        return False
    return None


def _is_manual_review(document: object, extraction: object | None, outcome: DocumentOutcome) -> bool:
    """Extraction/lifecycle review — not Redis employee-match queue."""
    if outcome == DocumentOutcome.REVIEW_REQUIRED:
        return True
    metadata = dict(getattr(document, "metadata", None) or {})
    lifecycle = str(metadata.get("lifecycle_status") or "").strip().lower()
    if lifecycle in {LIFECYCLE_REVIEW_REQUIRED, LIFECYCLE_ACCOUNTANT_REVIEW}:
        return True
    if extraction is not None:
        confirmation = _status_value(getattr(extraction, "confirmation_status", None))
        if confirmation == CONFIRMATION_REVIEW_REQUIRED:
            return True
    return False


def _month_point(
    *,
    year: int,
    month: int,
    processed: int,
    extraction_attempted: int,
    extraction_success: int,
    ocr_attempted: int,
    ocr_success: int,
    ocr_failed: int,
    validation_runs: int,
    validation_pass: int,
    confidences: list[float],
    manual_review: int,
    failed_documents: int,
) -> QualityMonthPoint:
    return QualityMonthPoint(
        period_year=year,
        period_month=month,
        documents_processed=processed,
        extraction_attempted=extraction_attempted,
        extraction_success=extraction_success,
        extraction_success_rate=rate(extraction_success, extraction_attempted),
        ocr_attempted=ocr_attempted,
        ocr_success=ocr_success,
        ocr_failed=ocr_failed,
        validation_runs=validation_runs,
        validation_pass=validation_pass,
        validation_success_rate=rate(validation_pass, validation_runs),
        average_confidence=average(confidences),
        confidence_sample_count=len(confidences),
        manual_review=manual_review,
        manual_review_rate=rate(manual_review, processed),
        failed_documents=failed_documents,
    )


class GetOrgQualityAnalyticsUseCase:
    """AI quality KPIs for one organization by payroll month."""

    metric_name = "org.quality"

    def __init__(
        self,
        *,
        employees: EmployeeRepository,
        documents: DocumentRepository,
        extractions: DocumentExtractionRepository,
        validation_runs: ValidationRunRepository,
    ) -> None:
        self._employees = employees
        self._documents = documents
        self._extractions = extractions
        self._runs = validation_runs

    async def execute(
        self,
        *,
        organization_id: UUID,
        year: int,
    ) -> OrgQualityAnalytics:
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

        year_docs = [d for d in payslips if matches_year(period_from_document(d), year)]
        doc_ids = [d.id for d in year_docs]
        latest_runs = await self._runs.list_latest_by_document_ids(doc_ids)

        counters: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
        confidences: dict[tuple[int, int], list[float]] = defaultdict(list)
        year_confidences: list[float] = []

        for doc in year_docs:
            period = period_from_document(doc)
            if period is None:
                continue
            key = (period.year, period.month)
            bucket = counters[key]
            bucket["documents_processed"] += 1

            extraction = await self._extractions.get_latest_for_document(doc.id)
            outcome = classify_document_outcome(doc, extraction)
            if outcome == DocumentOutcome.FAILED:
                bucket["failed_documents"] += 1
            if _is_manual_review(doc, extraction, outcome):
                bucket["manual_review"] += 1

            extraction_ok = _is_extraction_success(extraction)
            if extraction_ok is not None:
                bucket["extraction_attempted"] += 1
                if extraction_ok:
                    bucket["extraction_success"] += 1

            ocr_ok = _is_ocr_success(extraction)
            if ocr_ok is not None:
                bucket["ocr_attempted"] += 1
                if ocr_ok:
                    bucket["ocr_success"] += 1
                else:
                    bucket["ocr_failed"] += 1

            confidence = None
            if extraction is not None and extraction.overall_confidence is not None:
                confidence = float(extraction.overall_confidence)
            run = latest_runs.get(doc.id)
            if confidence is None and run is not None and run.overall_confidence is not None:
                confidence = float(run.overall_confidence)
            if confidence is not None:
                confidences[key].append(confidence)
                year_confidences.append(confidence)

            if run is None:
                continue
            bucket["validation_runs"] += 1
            result = run.overall_result
            result_value = _status_value(result)
            if result_value == ValidationResult.PASS.value:
                bucket["validation_pass"] += 1

        period_keys = sorted_period_keys(set(counters) | set(confidences))
        months = [
            _month_point(
                year=y,
                month=m,
                processed=int(counters[(y, m)]["documents_processed"]),
                extraction_attempted=int(counters[(y, m)]["extraction_attempted"]),
                extraction_success=int(counters[(y, m)]["extraction_success"]),
                ocr_attempted=int(counters[(y, m)]["ocr_attempted"]),
                ocr_success=int(counters[(y, m)]["ocr_success"]),
                ocr_failed=int(counters[(y, m)]["ocr_failed"]),
                validation_runs=int(counters[(y, m)]["validation_runs"]),
                validation_pass=int(counters[(y, m)]["validation_pass"]),
                confidences=confidences.get((y, m), []),
                manual_review=int(counters[(y, m)]["manual_review"]),
                failed_documents=int(counters[(y, m)]["failed_documents"]),
            )
            for y, m in period_keys
        ]

        totals_counter: Counter[str] = Counter()
        all_conf: list[float] = []
        for point in months:
            totals_counter["documents_processed"] += point.documents_processed
            totals_counter["extraction_attempted"] += point.extraction_attempted
            totals_counter["extraction_success"] += point.extraction_success
            totals_counter["ocr_attempted"] += point.ocr_attempted
            totals_counter["ocr_success"] += point.ocr_success
            totals_counter["ocr_failed"] += point.ocr_failed
            totals_counter["validation_runs"] += point.validation_runs
            totals_counter["validation_pass"] += point.validation_pass
            totals_counter["manual_review"] += point.manual_review
            totals_counter["failed_documents"] += point.failed_documents
            all_conf.extend(confidences.get((point.period_year, point.period_month), []))

        totals = _month_point(
            year=year,
            month=0,
            processed=int(totals_counter["documents_processed"]),
            extraction_attempted=int(totals_counter["extraction_attempted"]),
            extraction_success=int(totals_counter["extraction_success"]),
            ocr_attempted=int(totals_counter["ocr_attempted"]),
            ocr_success=int(totals_counter["ocr_success"]),
            ocr_failed=int(totals_counter["ocr_failed"]),
            validation_runs=int(totals_counter["validation_runs"]),
            validation_pass=int(totals_counter["validation_pass"]),
            confidences=all_conf or year_confidences,
            manual_review=int(totals_counter["manual_review"]),
            failed_documents=int(totals_counter["failed_documents"]),
        )

        return OrgQualityAnalytics(
            organization_id=organization_id,
            year=year,
            months=months,
            confidence_distribution=bucket_confidence_values(year_confidences),
            totals=totals,
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
