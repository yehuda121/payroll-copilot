"""Application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from payroll_copilot.application.validation.orchestrator import ValidationOrchestrator
from payroll_copilot.application.ports import LegalRulesLoader
from payroll_copilot.domain.entities import (
    Department,
    Employee,
    PayslipData,
)
from payroll_copilot.domain.enums import EmploymentType, EmployeeStatus, SalaryType
from payroll_copilot.domain.rules import ValidationContext
from payroll_copilot.domain.value_objects import Money, PayPeriod, ValidationReport


@dataclass
class RunValidationCommand:
    payslip: PayslipData
    employee: Employee
    department: Department
    period: PayPeriod
    field_confidences: dict[str, float]
    historical_payslips: list[PayslipData] | None = None
    disabled_rule_ids: frozenset[str] = frozenset()


class RunValidationUseCase:
    """Execute deterministic payroll validation."""

    def __init__(self, rules_loader: LegalRulesLoader) -> None:
        self._rules_loader = rules_loader
        self._orchestrator = ValidationOrchestrator()

    def execute(self, command: RunValidationCommand) -> ValidationReport:
        legal_rules = self._rules_loader.load_merged_rules()
        context = ValidationContext(
            payslip=command.payslip,
            employee=command.employee,
            department=command.department,
            period=command.period,
            legal_rules=legal_rules,
            historical_payslips=command.historical_payslips or [],
            field_confidences=command.field_confidences,
            disabled_rule_ids=command.disabled_rule_ids,
        )
        return self._orchestrator.run(context)


@dataclass
class EmployeeImportRow:
    employee_number: str
    first_name: str
    last_name: str
    department_code: str
    employment_type: str
    salary_type: str
    hourly_rate: float | None
    monthly_salary: float | None
    contract_start_date: str
    status: str = "active"
    extra_fields: dict | None = None


class ExcelColumnMapper:
    """Maps Excel headers to canonical field names — never uses column positions."""

    CANONICAL_FIELDS = {
        "employee_number": ["employee_number", "מספר עובד", "מס' עובד", "id", "employee id"],
        "first_name": ["first_name", "שם פרטי", "firstname"],
        "last_name": ["last_name", "שם משפחה", "lastname"],
        "department": ["department", "מחלקה", "dept"],
        "employment_type": ["employment_type", "סוג העסקה", "employment type"],
        "salary_type": ["salary_type", "סוג שכר", "salary type"],
        "hourly_rate": ["hourly_rate", "שכר שעתי", "hourly rate"],
        "monthly_salary": ["monthly_salary", "שכר חודשי", "monthly salary"],
        "contract_start_date": ["contract_start_date", "תאריך תחילת עבודה", "start date"],
        "status": ["status", "סטטוס"],
    }

    def detect_mapping(self, headers: list[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        normalized_headers = {h.strip().lower(): h for h in headers if h}

        for canonical, aliases in self.CANONICAL_FIELDS.items():
            for alias in aliases:
                if alias.lower() in normalized_headers:
                    mapping[canonical] = normalized_headers[alias.lower()]
                    break
        return mapping

    def map_row(self, row: dict[str, str | None], mapping: dict[str, str]) -> EmployeeImportRow:
        def get_field(canonical: str) -> str | None:
            header = mapping.get(canonical)
            if header is None:
                return None
            val = row.get(header)
            return str(val).strip() if val is not None else None

        hourly = get_field("hourly_rate")
        monthly = get_field("monthly_salary")

        return EmployeeImportRow(
            employee_number=get_field("employee_number") or "",
            first_name=get_field("first_name") or "",
            last_name=get_field("last_name") or "",
            department_code=get_field("department") or "",
            employment_type=get_field("employment_type") or "full_time",
            salary_type=get_field("salary_type") or "monthly",
            hourly_rate=float(hourly) if hourly else None,
            monthly_salary=float(monthly) if monthly else None,
            contract_start_date=get_field("contract_start_date") or "",
            status=get_field("status") or "active",
        )
