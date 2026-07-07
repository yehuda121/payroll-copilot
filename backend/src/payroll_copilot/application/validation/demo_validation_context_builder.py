"""Temporary demo validation context builder.

TODO: Replace with OCR/extraction pipeline when document processing is ready.
      DemoValidationContextBuilder must be removed once payslip fields are loaded
      from persisted document extractions instead of hardcoded sample data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from payroll_copilot.application.use_cases.validation import RunValidationCommand
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import EmploymentType, EmployeeStatus, SalaryType
from payroll_copilot.domain.value_objects import Money, PayPeriod

# Fixed demo organization used until real org resolution is wired.
DEMO_ORGANIZATION_ID = UUID("00000000-0000-4000-8000-000000000001")


@dataclass(frozen=True, slots=True)
class DemoValidationBundle:
    command: RunValidationCommand
    organization_id: UUID
    document_id: UUID


class DemoValidationContextBuilder:
    """Builds a deterministic demo ValidationContext payload for validation runs.

    This is NOT production extraction logic. It exists only while OCR/payslip
    extraction is not yet integrated with the validation pipeline.
    """

    def build(self, document_id: UUID, employee_id: UUID | None = None) -> DemoValidationBundle:
        demo_employee = Employee(
            id=employee_id or uuid4(),
            organization_id=DEMO_ORGANIZATION_ID,
            employee_number="12345",
            first_name="Demo",
            last_name="Employee",
            department_id=uuid4(),
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.HOURLY,
            hourly_rate=Decimal("35.00"),
            contract_start_date=date(2024, 1, 1),
            status=EmployeeStatus.ACTIVE,
        )
        demo_department = Department(
            id=uuid4(),
            organization_id=DEMO_ORGANIZATION_ID,
            code="payroll",
            name={"he": "שכר", "en": "Payroll"},
            rule_profile="payroll",
        )
        period = PayPeriod(year=2026, month=6)
        demo_payslip = PayslipData(
            employee_number="12345",
            period=period,
            gross_salary=Money(Decimal("15000")),
            overtime_hours=Decimal("3"),
            pension_employee=Money(Decimal("600")),
        )

        command = RunValidationCommand(
            payslip=demo_payslip,
            employee=demo_employee,
            department=demo_department,
            period=period,
            field_confidences={
                "overtime_hours": 0.95,
                "gross_salary": 0.98,
                "hourly_rate": 1.0,
            },
        )
        return DemoValidationBundle(
            command=command,
            organization_id=DEMO_ORGANIZATION_ID,
            document_id=document_id,
        )
