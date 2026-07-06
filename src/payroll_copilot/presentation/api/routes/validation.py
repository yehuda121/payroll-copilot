"""Validation routes."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from payroll_copilot.application.use_cases.validation import RunValidationCommand, RunValidationUseCase
from payroll_copilot.domain.entities import Department, Employee
from payroll_copilot.domain.enums import EmploymentType, EmployeeStatus, SalaryType
from payroll_copilot.domain.value_objects import Money, PayPeriod
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader

router = APIRouter()


class ValidationRunRequest(BaseModel):
    document_id: str
    employee_id: str | None = None
    include_historical: bool = True
    include_contract_rag: bool = True


class FindingResponse(BaseModel):
    rule_id: str
    severity: str
    message_key: str
    expected_value: str | None
    actual_value: str | None
    confidence: float
    legal_reference: str | None = None


class ValidationRunResponse(BaseModel):
    id: str
    status: str
    overall_result: str | None = None
    overall_confidence: float | None = None
    findings: list[FindingResponse] = Field(default_factory=list)


def _get_validation_use_case() -> RunValidationUseCase:
    settings = get_settings()
    loader = YamlLegalRulesLoader(settings.legal_rules_path)
    return RunValidationUseCase(loader)


@router.post("/run", response_model=ValidationRunResponse, status_code=202)
async def run_validation(request: ValidationRunRequest) -> ValidationRunResponse:
    """Trigger deterministic validation for a payslip document."""
    use_case = _get_validation_use_case()

    # Demo validation with sample data when document processing not yet complete
    from payroll_copilot.domain.entities import PayslipData

    demo_employee = Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="12345",
        first_name="Demo",
        last_name="Employee",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.HOURLY,
        hourly_rate=Decimal("35.00"),
        contract_start_date=__import__("datetime").date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
    )
    demo_department = Department(
        id=uuid4(),
        organization_id=demo_employee.organization_id,
        code="payroll",
        name={"he": "שכר", "en": "Payroll"},
        rule_profile="payroll",
    )
    demo_payslip = PayslipData(
        employee_number="12345",
        period=PayPeriod(year=2026, month=6),
        gross_salary=Money(Decimal("15000")),
        overtime_hours=Decimal("3"),
        pension_employee=Money(Decimal("600")),
    )

    report = use_case.execute(
        RunValidationCommand(
            payslip=demo_payslip,
            employee=demo_employee,
            department=demo_department,
            period=PayPeriod(year=2026, month=6),
            field_confidences={"overtime_hours": 0.95, "gross_salary": 0.98, "hourly_rate": 1.0},
        )
    )

    return ValidationRunResponse(
        id=str(report.validation_run_id),
        status="completed",
        overall_result=report.overall_result,
        overall_confidence=report.overall_confidence.value,
        findings=[
            FindingResponse(
                rule_id=f.rule_id,
                severity=f.severity.value,
                message_key=f.message_key,
                expected_value=f.expected_value,
                actual_value=f.actual_value,
                confidence=f.confidence.value,
                legal_reference=f.legal_reference,
            )
            for f in report.findings
        ],
    )


@router.get("/runs/{validation_run_id}", response_model=ValidationRunResponse)
async def get_validation_run(validation_run_id: str) -> ValidationRunResponse:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Validation run {validation_run_id} not found",
    )
