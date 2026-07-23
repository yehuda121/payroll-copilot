"""Pydantic response schemas for analytics APIs."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SalaryMonthPointSchema(BaseModel):
    period_year: int
    period_month: int
    net_salary: Decimal | None = None
    gross_salary: Decimal | None = None
    currency: str = "ILS"
    document_id: UUID | None = None
    extraction_id: UUID | None = None


class EmployeeSalaryAnalyticsResponse(BaseModel):
    employee_id: UUID
    organization_id: UUID
    year: int
    months: list[SalaryMonthPointSchema] = Field(default_factory=list)
    available_years: list[int] = Field(default_factory=list)
    documents_missing_period: int = 0


class OutcomeMonthPointSchema(BaseModel):
    period_year: int
    period_month: int
    documents_processed: int = 0
    success: int = 0
    review_required: int = 0
    failed: int = 0


class ValidationFailureMonthPointSchema(BaseModel):
    period_year: int
    period_month: int
    failure_count: int = 0
    runs_with_failures: int = 0


class ErrorTypeBucketSchema(BaseModel):
    key: str
    count: int
    category: str | None = None


class ConfidenceMonthPointSchema(BaseModel):
    period_year: int
    period_month: int
    average_confidence: float | None = None
    sample_count: int = 0


class OrgPayrollAnalyticsResponse(BaseModel):
    organization_id: UUID
    year: int
    documents_by_month: list[OutcomeMonthPointSchema] = Field(default_factory=list)
    validation_failures_by_month: list[ValidationFailureMonthPointSchema] = Field(
        default_factory=list
    )
    error_type_distribution: list[ErrorTypeBucketSchema] = Field(default_factory=list)
    top_validation_failures: list[ErrorTypeBucketSchema] = Field(default_factory=list)
    average_confidence_by_month: list[ConfidenceMonthPointSchema] = Field(default_factory=list)
    documents_missing_period: int = 0
    available_years: list[int] = Field(default_factory=list)


class AccountantCaseloadSchema(BaseModel):
    payroll_accountant_id: UUID
    employee_count: int


class OrganizationCensusSliceSchema(BaseModel):
    organization_id: UUID
    employees_count: int = 0
    payroll_accountants_count: int = 0
    employees_without_payroll_accountant: int = 0
    employees_per_payroll_accountant: list[AccountantCaseloadSchema] = Field(default_factory=list)


class AdminOrgCensusResponse(BaseModel):
    companies_count: int
    employees_count: int
    payroll_accountants_count: int
    employees_without_payroll_accountant: int
    employees_per_payroll_accountant: list[AccountantCaseloadSchema] = Field(default_factory=list)
    organizations: list[OrganizationCensusSliceSchema] = Field(default_factory=list)


class ConfidenceBucketSchema(BaseModel):
    label: str
    min_inclusive: float
    max_exclusive: float
    count: int = 0


class QualityMonthPointSchema(BaseModel):
    period_year: int
    period_month: int
    documents_processed: int = 0
    extraction_attempted: int = 0
    extraction_success: int = 0
    extraction_success_rate: float | None = None
    ocr_attempted: int = 0
    ocr_success: int = 0
    ocr_failed: int = 0
    validation_runs: int = 0
    validation_pass: int = 0
    validation_success_rate: float | None = None
    average_confidence: float | None = None
    confidence_sample_count: int = 0
    manual_review: int = 0
    manual_review_rate: float | None = None
    failed_documents: int = 0


class OrgQualityAnalyticsResponse(BaseModel):
    organization_id: UUID
    year: int
    months: list[QualityMonthPointSchema] = Field(default_factory=list)
    confidence_distribution: list[ConfidenceBucketSchema] = Field(default_factory=list)
    totals: QualityMonthPointSchema | None = None
    documents_missing_period: int = 0
    available_years: list[int] = Field(default_factory=list)


class AdminQualityAnalyticsResponse(BaseModel):
    year: int
    organizations_count: int = 0
    months: list[QualityMonthPointSchema] = Field(default_factory=list)
    confidence_distribution: list[ConfidenceBucketSchema] = Field(default_factory=list)
    totals: QualityMonthPointSchema | None = None
    organizations: list[OrgQualityAnalyticsResponse] = Field(default_factory=list)
    available_years: list[int] = Field(default_factory=list)
