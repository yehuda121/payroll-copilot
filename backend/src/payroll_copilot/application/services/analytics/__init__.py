"""Analytics package — on-demand aggregation over existing payroll entities."""

from payroll_copilot.application.services.analytics.aggregation import (
    average,
    count_by,
    group_by,
    sorted_period_keys,
    top_n,
)
from payroll_copilot.application.services.analytics.document_outcomes import (
    DocumentOutcome,
    classify_document_outcome,
)
from payroll_copilot.application.services.analytics.period_keys import (
    matches_year,
    period_from_document,
    period_key,
)
from payroll_copilot.application.services.analytics.registry import (
    AnalyticsContext,
    AnalyticsMetricProvider,
    AnalyticsRegistry,
)
from payroll_copilot.application.services.analytics.salary_values import salary_amounts_from_sources

__all__ = [
    "AnalyticsContext",
    "AnalyticsMetricProvider",
    "AnalyticsRegistry",
    "DocumentOutcome",
    "average",
    "classify_document_outcome",
    "count_by",
    "group_by",
    "matches_year",
    "period_from_document",
    "period_key",
    "salary_amounts_from_sources",
    "sorted_period_keys",
    "top_n",
]
