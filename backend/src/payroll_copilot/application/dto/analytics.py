"""Application DTOs for analytics query results.

These are the Stable contract shapes future dashboards consume.
New metrics should add new DTOs rather than mutating existing ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PeriodPoint:
    """One payroll period bucket (period_year + period_month only)."""

    period_year: int
    period_month: int

    @property
    def label(self) -> str:
        return f"{self.period_year:04d}-{self.period_month:02d}"


@dataclass(frozen=True, slots=True)
class SalaryMonthPoint:
    period_year: int
    period_month: int
    net_salary: Decimal | None = None
    gross_salary: Decimal | None = None
    currency: str = "ILS"
    document_id: UUID | None = None
    extraction_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class EmployeeSalaryAnalytics:
    employee_id: UUID
    organization_id: UUID
    year: int
    months: list[SalaryMonthPoint] = field(default_factory=list)
    available_years: list[int] = field(default_factory=list)
    documents_missing_period: int = 0


@dataclass(frozen=True, slots=True)
class OutcomeMonthPoint:
    period_year: int
    period_month: int
    documents_processed: int = 0
    success: int = 0
    review_required: int = 0
    failed: int = 0


@dataclass(frozen=True, slots=True)
class ValidationFailureMonthPoint:
    period_year: int
    period_month: int
    failure_count: int = 0
    runs_with_failures: int = 0


@dataclass(frozen=True, slots=True)
class ErrorTypeBucket:
    key: str
    count: int
    category: str | None = None


@dataclass(frozen=True, slots=True)
class ConfidenceMonthPoint:
    period_year: int
    period_month: int
    average_confidence: float | None = None
    sample_count: int = 0


@dataclass(frozen=True, slots=True)
class OrgPayrollAnalytics:
    organization_id: UUID
    year: int
    documents_by_month: list[OutcomeMonthPoint] = field(default_factory=list)
    validation_failures_by_month: list[ValidationFailureMonthPoint] = field(default_factory=list)
    error_type_distribution: list[ErrorTypeBucket] = field(default_factory=list)
    top_validation_failures: list[ErrorTypeBucket] = field(default_factory=list)
    average_confidence_by_month: list[ConfidenceMonthPoint] = field(default_factory=list)
    documents_missing_period: int = 0
    available_years: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AccountantCaseload:
    payroll_accountant_id: UUID
    employee_count: int


@dataclass(frozen=True, slots=True)
class OrganizationCensusSlice:
    organization_id: UUID
    employees_count: int = 0
    payroll_accountants_count: int = 0
    employees_without_payroll_accountant: int = 0
    employees_per_payroll_accountant: list[AccountantCaseload] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AdminOrgCensus:
    companies_count: int
    employees_count: int
    payroll_accountants_count: int
    employees_without_payroll_accountant: int
    employees_per_payroll_accountant: list[AccountantCaseload] = field(default_factory=list)
    organizations: list[OrganizationCensusSlice] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
