"""Domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
)
from payroll_copilot.domain.value_objects import Money, PayPeriod


@dataclass
class Organization:
    id: UUID
    name: str
    slug: str
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Department:
    id: UUID
    organization_id: UUID
    code: str
    name: dict[str, str]
    rule_profile: str
    is_active: bool = True


@dataclass
class Employee:
    id: UUID
    organization_id: UUID
    employee_number: str
    first_name: str
    last_name: str
    department_id: UUID
    employment_type: EmploymentType
    salary_type: SalaryType
    contract_start_date: date
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    hourly_rate: Decimal | None = None
    monthly_salary: Decimal | None = None
    contract_end_date: date | None = None
    manager_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


@dataclass
class PayslipData:
    """Structured payslip fields extracted from OCR/LLM."""

    employee_number: str | None = None
    employee_name: str | None = None
    period: PayPeriod | None = None
    gross_salary: Money | None = None
    net_salary: Money | None = None
    base_salary: Money | None = None
    overtime_hours: Decimal | None = None
    overtime_pay: Money | None = None
    vacation_days_used: Decimal | None = None
    sick_days_used: Decimal | None = None
    tax_deducted: Money | None = None
    pension_employee: Money | None = None
    pension_employer: Money | None = None
    transportation_allowance: Money | None = None
    work_days: int | None = None
    work_hours: Decimal | None = None
    deductions: dict[str, Money] = field(default_factory=dict)
    additional_fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Document:
    id: UUID
    document_type: DocumentType
    storage_key: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    checksum_sha256: str
    status: DocumentStatus = DocumentStatus.UPLOADED
    organization_id: UUID | None = None
    uploaded_by: UUID | None = None
    employee_id: UUID | None = None
    period: PayPeriod | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None


@dataclass
class DocumentExtraction:
    """Persisted OCR + AI parser output for a document.

    Never feeds the Rule Engine directly. Structured fields are consumed by
    future validation context mapping / guest review UI.
    """

    id: UUID
    document_id: UUID
    engine: str
    raw_text: str
    structured_data: dict[str, Any]
    overall_confidence: float | None = None
    field_confidences: dict[str, float] = field(default_factory=dict)
    extraction_version: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)
    ocr_result: dict[str, Any] = field(default_factory=dict)
    parser_model: str | None = None
    language: str = "auto"
    ocr_status: str = "completed"
    parser_status: str = "completed"
    warnings: list[str] = field(default_factory=list)
    error_message: str | None = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
    confirmation_status: str = "review_required"
    confirmed_at: datetime | None = None
    confirmed_by: UUID | None = None


@dataclass
class AttendanceRecord:
    id: UUID
    organization_id: UUID
    employee_id: UUID
    record_type: str
    start_date: date
    end_date: date
    hours: Decimal | None = None
    source: str = "manual"
    confidence: float = 1.0
    review_status: str = "approved"


def new_uuid() -> UUID:
    return uuid4()
