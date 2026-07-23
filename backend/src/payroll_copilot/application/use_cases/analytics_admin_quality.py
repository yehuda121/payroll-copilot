"""Admin cross-org AI quality analytics (reuses org quality use case)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from uuid import UUID

from payroll_copilot.application.dto.analytics import (
    AdminQualityAnalytics,
    ConfidenceBucket,
    OrgQualityAnalytics,
    QualityMonthPoint,
)
from payroll_copilot.application.ports.organization_directory import OrganizationDirectoryPort
from payroll_copilot.application.services.analytics.aggregation import average, sorted_period_keys
from payroll_copilot.application.services.analytics.confidence_buckets import (
    CONFIDENCE_BUCKET_SPECS,
    bucket_confidence_values,
    rate,
)
from payroll_copilot.application.use_cases.analytics_org_quality import GetOrgQualityAnalyticsUseCase


def _merge_month_points(points: list[QualityMonthPoint], *, year: int, month: int) -> QualityMonthPoint:
    processed = sum(p.documents_processed for p in points)
    extraction_attempted = sum(p.extraction_attempted for p in points)
    extraction_success = sum(p.extraction_success for p in points)
    ocr_attempted = sum(p.ocr_attempted for p in points)
    ocr_success = sum(p.ocr_success for p in points)
    ocr_failed = sum(p.ocr_failed for p in points)
    validation_runs = sum(p.validation_runs for p in points)
    validation_pass = sum(p.validation_pass for p in points)
    manual_review = sum(p.manual_review for p in points)
    failed_documents = sum(p.failed_documents for p in points)
    conf_samples: list[float] = []
    for point in points:
        if point.average_confidence is not None and point.confidence_sample_count > 0:
            # Reconstruct approximate sample list weight for average merge.
            conf_samples.extend(
                [point.average_confidence] * int(point.confidence_sample_count)
            )
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
        average_confidence=average(conf_samples),
        confidence_sample_count=len(conf_samples),
        manual_review=manual_review,
        manual_review_rate=rate(manual_review, processed),
        failed_documents=failed_documents,
    )


class GetAdminQualityAnalyticsUseCase:
    """Aggregate org.quality across known organizations for admin dashboards."""

    metric_name = "admin.quality"

    def __init__(
        self,
        *,
        organizations: OrganizationDirectoryPort,
        org_quality: GetOrgQualityAnalyticsUseCase,
    ) -> None:
        self._organizations = organizations
        self._org_quality = org_quality

    async def execute(self, *, year: int) -> AdminQualityAnalytics:
        org_ids = await self._organizations.list_organization_ids()
        org_results: list[OrgQualityAnalytics] = []
        for org_id in org_ids:
            org_results.append(
                await self._org_quality.execute(organization_id=org_id, year=year)
            )

        by_month: dict[tuple[int, int], list[QualityMonthPoint]] = {}
        available_years: set[int] = {year, datetime.utcnow().year}
        conf_bucket_counts: Counter[str] = Counter()

        for result in org_results:
            available_years.update(result.available_years)
            for point in result.months:
                by_month.setdefault((point.period_year, point.period_month), []).append(point)
            for bucket in result.confidence_distribution:
                conf_bucket_counts[bucket.label] += bucket.count

        months = [
            _merge_month_points(by_month[key], year=key[0], month=key[1])
            for key in sorted_period_keys(by_month)
        ]

        totals = (
            _merge_month_points(months, year=year, month=0)
            if months
            else QualityMonthPoint(period_year=year, period_month=0)
        )

        if conf_bucket_counts:
            confidence_distribution = [
                ConfidenceBucket(
                    label=label,
                    min_inclusive=lo,
                    max_exclusive=hi,
                    count=int(conf_bucket_counts.get(label, 0)),
                )
                for label, lo, hi in CONFIDENCE_BUCKET_SPECS
            ]
        else:
            confidence_distribution = bucket_confidence_values([])

        return AdminQualityAnalytics(
            year=year,
            organizations_count=len(org_ids),
            months=months,
            confidence_distribution=confidence_distribution,
            totals=totals,
            organizations=org_results,
            available_years=sorted(available_years, reverse=True),
        )

    async def compute(self, context):
        if context.year is None:
            raise ValueError("year is required")
        return await self.execute(year=int(context.year))
