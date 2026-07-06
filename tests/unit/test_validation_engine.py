"""Tests for the validation rule engine."""

from decimal import Decimal
from uuid import uuid4

import pytest

import payroll_copilot.domain.rules.departments  # noqa: F401
import payroll_copilot.domain.rules.historical  # noqa: F401
import payroll_copilot.domain.rules.legal  # noqa: F401
from payroll_copilot.application.use_cases.validation import RunValidationCommand, RunValidationUseCase
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import (
    EmploymentType,
    EmployeeStatus,
    FindingSeverity,
    SalaryType,
    ValidationResult,
)
from payroll_copilot.domain.value_objects import Money, PayPeriod
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader


@pytest.fixture
def rules_loader() -> YamlLegalRulesLoader:
    return YamlLegalRulesLoader("config/rules/labor_law")


@pytest.fixture
def hourly_employee() -> Employee:
    return Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="1001",
        first_name="Test",
        last_name="Employee",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.HOURLY,
        hourly_rate=Decimal("35.00"),
        contract_start_date=__import__("datetime").date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
    )


@pytest.fixture
def payroll_department(hourly_employee: Employee) -> Department:
    return Department(
        id=hourly_employee.department_id,
        organization_id=hourly_employee.organization_id,
        code="payroll",
        name={"he": "שכר", "en": "Payroll"},
        rule_profile="payroll",
    )


class TestYamlRulesLoader:
    def test_loads_all_yaml_files(self, rules_loader: YamlLegalRulesLoader) -> None:
        bundles = rules_loader.load_all()
        assert "labor_law" in bundles
        assert "overtime" in bundles
        assert "vacation" in bundles

    def test_merged_rules_contain_overtime(self, rules_loader: YamlLegalRulesLoader) -> None:
        merged = rules_loader.load_merged_rules()
        assert "daily_overtime_limit" in merged.rules
        assert merged.rules["daily_overtime_limit"].parameters["max_hours"] == 2


class TestValidationEngine:
    def test_overtime_exceeds_limit_produces_warning(
        self,
        rules_loader: YamlLegalRulesLoader,
        hourly_employee: Employee,
        payroll_department: Department,
    ) -> None:
        use_case = RunValidationUseCase(rules_loader)
        payslip = PayslipData(
            employee_number="1001",
            period=PayPeriod(year=2026, month=6),
            gross_salary=Money(Decimal("15000")),
            overtime_hours=Decimal("3"),
            pension_employee=Money(Decimal("900")),
        )

        report = use_case.execute(
            RunValidationCommand(
                payslip=payslip,
                employee=hourly_employee,
                department=payroll_department,
                period=PayPeriod(year=2026, month=6),
                field_confidences={"overtime_hours": 0.95, "gross_salary": 0.98},
            )
        )

        overtime_findings = [f for f in report.findings if "overtime" in f.rule_id]
        assert len(overtime_findings) >= 1
        assert overtime_findings[0].severity == FindingSeverity.WARNING

    def test_compliant_payslip_passes(
        self,
        rules_loader: YamlLegalRulesLoader,
        hourly_employee: Employee,
        payroll_department: Department,
    ) -> None:
        use_case = RunValidationUseCase(rules_loader)
        payslip = PayslipData(
            employee_number="1001",
            period=PayPeriod(year=2026, month=6),
            gross_salary=Money(Decimal("15000")),
            overtime_hours=Decimal("1"),
            pension_employee=Money(Decimal("900")),
        )

        report = use_case.execute(
            RunValidationCommand(
                payslip=payslip,
                employee=hourly_employee,
                department=payroll_department,
                period=PayPeriod(year=2026, month=6),
                field_confidences={"overtime_hours": 0.95, "gross_salary": 0.98},
            )
        )

        critical = [f for f in report.findings if f.severity == FindingSeverity.CRITICAL]
        assert report.overall_result in (ValidationResult.PASS.value, ValidationResult.WARNINGS.value)
        assert len(critical) == 0

    def test_below_minimum_wage_is_critical(
        self,
        rules_loader: YamlLegalRulesLoader,
        payroll_department: Department,
    ) -> None:
        low_wage_employee = Employee(
            id=uuid4(),
            organization_id=uuid4(),
            employee_number="1002",
            first_name="Low",
            last_name="Wage",
            department_id=payroll_department.id,
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.HOURLY,
            hourly_rate=Decimal("28.00"),
            contract_start_date=__import__("datetime").date(2024, 1, 1),
            status=EmployeeStatus.ACTIVE,
        )

        use_case = RunValidationUseCase(rules_loader)
        payslip = PayslipData(
            gross_salary=Money(Decimal("5000")),
            pension_employee=Money(Decimal("300")),
        )

        report = use_case.execute(
            RunValidationCommand(
                payslip=payslip,
                employee=low_wage_employee,
                department=payroll_department,
                period=PayPeriod(year=2026, month=6),
                field_confidences={"hourly_rate": 1.0},
            )
        )

        min_wage_findings = [f for f in report.findings if f.rule_id == "legal.minimum_wage"]
        assert len(min_wage_findings) == 1
        assert min_wage_findings[0].severity == FindingSeverity.CRITICAL


class TestExcelColumnMapper:
    def test_detects_hebrew_headers(self) -> None:
        from payroll_copilot.application.use_cases.validation import ExcelColumnMapper

        mapper = ExcelColumnMapper()
        headers = ["מספר עובד", "שם פרטי", "שם משפחה", "מחלקה", "שכר שעתי"]
        mapping = mapper.detect_mapping(headers)

        assert mapping["employee_number"] == "מספר עובד"
        assert mapping["first_name"] == "שם פרטי"
        assert mapping["hourly_rate"] == "שכר שעתי"

    def test_never_uses_column_position(self) -> None:
        from payroll_copilot.application.use_cases.validation import ExcelColumnMapper

        mapper = ExcelColumnMapper()
        headers_reordered = ["שכר שעתי", "מספר עובד", "שם פרטי"]
        mapping = mapper.detect_mapping(headers_reordered)

        assert mapping["employee_number"] == "מספר עובד"
        assert mapping["hourly_rate"] == "שכר שעתי"
