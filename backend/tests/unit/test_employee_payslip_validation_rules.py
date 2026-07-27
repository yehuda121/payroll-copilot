"""EMPLOYEE payslip↔profile validation rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

import payroll_copilot.domain.rules.departments  # noqa: F401
import payroll_copilot.domain.rules.employee  # noqa: F401
import payroll_copilot.domain.rules.historical  # noqa: F401
import payroll_copilot.domain.rules.legal  # noqa: F401
import payroll_copilot.domain.rules.sanity  # noqa: F401
from payroll_copilot.application.services.validation_taxonomy import (
    ValidationTaxonomy,
    bound_rule_ids_for_field,
    taxonomy_for_rule_id,
    ui_group_for_taxonomy,
)
from payroll_copilot.application.use_cases.validation import RunValidationCommand, RunValidationUseCase
from payroll_copilot.domain.entities import Department, Employee, PayslipData
from payroll_copilot.domain.enums import (
    EmployeeStatus,
    EmploymentType,
    FindingSeverity,
    SalaryType,
    ValidationResult,
)
from payroll_copilot.domain.value_objects import Money, PayPeriod
from payroll_copilot.infrastructure.rules.yaml_loader import YamlLegalRulesLoader

_VALID_NATIONAL_ID = "313366783"


@pytest.fixture
def rules_loader() -> YamlLegalRulesLoader:
    return YamlLegalRulesLoader("config/rules/labor_law")


@pytest.fixture
def profile_employee() -> Employee:
    return Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="E-1001",
        first_name="Dana",
        last_name="Cohen",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 3, 15),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("12000"),
        metadata={"verified_display_name": "Dana Cohen"},
    )


@pytest.fixture
def department(profile_employee: Employee) -> Department:
    return Department(
        id=profile_employee.department_id,
        organization_id=profile_employee.organization_id,
        code="payroll",
        name={"he": "שכר", "en": "Payroll"},
        rule_profile="payroll",
    )


def _run(
    rules_loader: YamlLegalRulesLoader,
    *,
    payslip: PayslipData,
    employee: Employee,
    department: Department,
    authorized: bool,
    trusted_national_id: str | None = None,
    selected_year: int | None = 2026,
    selected_month: int | None = 6,
) -> object:
    return RunValidationUseCase(rules_loader).execute(
        RunValidationCommand(
            payslip=payslip,
            employee=employee,
            department=department,
            period=payslip.period or PayPeriod(year=2026, month=6),
            field_confidences={},
            authorized_employee=authorized,
            trusted_national_id=trusted_national_id,
            selected_period_year=selected_year,
            selected_period_month=selected_month,
        )
    )


def _ids(report: object) -> set[str]:
    return {f.rule_id for f in report.findings}  # type: ignore[attr-defined]


class TestGuestHasNoEmployeeMismatches:
    def test_unauthorized_context_skips_employee_rules(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        payslip = PayslipData(
            employee_name="Someone Else",
            employee_number="WRONG",
            period=PayPeriod(year=2026, month=1),
            additional_fields={
                "national_id": "123456782",
                "employment_type": "part_time",
                "employment_start_date": "2010-01-01",
            },
        )
        report = _run(
            rules_loader,
            payslip=payslip,
            employee=profile_employee,
            department=department,
            authorized=False,
            trusted_national_id=_VALID_NATIONAL_ID,
        )
        assert not any(rid.startswith("employee.") for rid in _ids(report))


class TestNationalIdMatch:
    def test_match(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"national_id": _VALID_NATIONAL_ID}),
            employee=profile_employee,
            department=department,
            authorized=True,
            trusted_national_id=_VALID_NATIONAL_ID,
        )
        assert "employee.national_id.match" not in _ids(report)

    def test_mismatch_critical(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"national_id": "123456782"}),
            employee=profile_employee,
            department=department,
            authorized=True,
            trusted_national_id=_VALID_NATIONAL_ID,
        )
        findings = [f for f in report.findings if f.rule_id == "employee.national_id.match"]
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.CRITICAL
        assert report.overall_result == ValidationResult.CRITICAL.value

    def test_missing_reference_is_info_not_mismatch(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"national_id": _VALID_NATIONAL_ID}),
            employee=profile_employee,
            department=department,
            authorized=True,
            trusted_national_id=None,
        )
        findings = [f for f in report.findings if f.rule_id == "employee.national_id.match"]
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.INFO
        assert findings[0].message_key == "validation.missing_data"

    def test_missing_payslip_is_uncertain_not_pass_or_fail(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(),
            employee=profile_employee,
            department=department,
            authorized=True,
            trusted_national_id=_VALID_NATIONAL_ID,
        )
        findings = [f for f in report.findings if f.rule_id == "employee.national_id.match"]
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.INFO
        assert findings[0].message_key == "validation.missing_data"
        outcomes = {item.rule_id: item.outcome for item in report.rule_outcomes}
        assert outcomes.get("employee.national_id.match") == "uncertain"

class TestNameMatch:
    def test_order_insensitive_hebrew_match(
        self,
        rules_loader: YamlLegalRulesLoader,
        department: Department,
    ) -> None:
        employee = Employee(
            id=uuid4(),
            organization_id=department.organization_id,
            employee_number="1",
            first_name="יהודה",
            last_name="כהן",
            department_id=department.id,
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2020, 1, 1),
            status=EmployeeStatus.ACTIVE,
            metadata={"verified_display_name": "יהודה כהן"},
        )
        report = _run(
            rules_loader,
            payslip=PayslipData(employee_name="כהן יהודה"),
            employee=employee,
            department=department,
            authorized=True,
        )
        assert "employee.name.match" not in _ids(report)

    def test_mismatch(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(employee_name="Other Person"),
            employee=profile_employee,
            department=department,
            authorized=True,
        )
        findings = [f for f in report.findings if f.rule_id == "employee.name.match"]
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.WARNING

    def test_cross_script_insufficient_not_mismatch(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(employee_name="דנה כהן"),
            employee=profile_employee,
            department=department,
            authorized=True,
        )
        findings = [f for f in report.findings if f.rule_id == "employee.name.match"]
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.INFO


class TestEmployeeNumberMatch:
    def test_match_normalized(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(
                employee_number="e-1001",
                additional_fields={"employee_number": "e-1001"},
            ),
            employee=profile_employee,
            department=department,
            authorized=True,
        )
        assert "employee.employee_number.match" not in _ids(report)

    def test_mismatch(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employee_number": "E-9999"}),
            employee=profile_employee,
            department=department,
            authorized=True,
        )
        findings = [f for f in report.findings if f.rule_id == "employee.employee_number.match"]
        assert len(findings) == 1


class TestEmploymentStartNotComparedToProfile:
    """CASE C: contract_start_date is overloaded — never use it for seniority/start."""

    def test_rule_not_registered(self) -> None:
        from payroll_copilot.domain.rules import get_registered_rules

        assert "employee.employment_start_date.match" not in get_registered_rules()
        assert not any(
            rid.startswith("contract.") and "employment_start" in rid
            for rid in get_registered_rules()
        )

    def test_payslip_start_differs_from_contract_start_date_no_finding(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        # profile_employee.contract_start_date is 2020-03-15 (often create/default).
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_start_date": "2021-01-01"}),
            employee=profile_employee,
            department=department,
            authorized=True,
        )
        assert "employee.employment_start_date.match" not in _ids(report)
        assert not any("employment_start_date.match" in rid for rid in _ids(report))

    def test_system_lifecycle_dates_never_emit_start_match(
        self,
        rules_loader: YamlLegalRulesLoader,
        department: Department,
    ) -> None:
        """Regression: create/onboarding/today placeholders must not drive employment start."""
        onboarded_today = Employee(
            id=uuid4(),
            organization_id=department.organization_id,
            employee_number="E-NEW",
            first_name="New",
            last_name="Hire",
            department_id=department.id,
            employment_type=EmploymentType.FULL_TIME,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date.today(),  # create API default — not employment start
            status=EmployeeStatus.ACTIVE,
            metadata={"imported_at": "2026-07-01T00:00:00Z"},
        )
        report = _run(
            rules_loader,
            payslip=PayslipData(
                additional_fields={
                    "employment_start_date": "2015-06-01",
                    "seniority_years": "10",
                }
            ),
            employee=onboarded_today,
            department=department,
            authorized=True,
        )
        employee_start_findings = [
            rid
            for rid in _ids(report)
            if "employment_start" in rid and rid.startswith(("employee.", "contract."))
        ]
        assert employee_start_findings == []
        assert not any("seniority" in rid for rid in _ids(report))

    def test_binding_excludes_removed_employee_start_rule(self) -> None:
        bound = bound_rule_ids_for_field("employment_start_date")
        assert "employee.employment_start_date.match" not in bound
        assert "sanity.employment_start_date.calendar" in bound
        # Explicit taxonomy map entry removed (historical findings may still carry the old rule_id).
        from payroll_copilot.application.services import validation_taxonomy as vt

        assert "employee.employment_start_date.match" not in vt._RULE_ID_TAXONOMY  # noqa: SLF001


class TestEmploymentType:
    def test_employment_type_match(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_type": "full_time"}),
            employee=profile_employee,
            department=department,
            authorized=True,
        )
        assert "employee.employment_type.match" not in _ids(report)

    def test_employment_type_mismatch(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_type": "part_time"}),
            employee=profile_employee,
            department=department,
            authorized=True,
        )
        assert "employee.employment_type.match" in _ids(report)

    def test_unrecognized_payslip_type_not_employee_mismatch(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(additional_fields={"employment_type": "חודשי"}),
            employee=profile_employee,
            department=department,
            authorized=True,
        )
        employee_findings = [
            f for f in report.findings if f.rule_id == "employee.employment_type.match"
        ]
        assert all(f.severity == FindingSeverity.INFO for f in employee_findings)
        assert not any(
            f.severity in {FindingSeverity.WARNING, FindingSeverity.CRITICAL}
            for f in employee_findings
        )
        assert "sanity.employment_type.recognized" in _ids(report)
        outcomes = {item.rule_id: item.outcome for item in report.rule_outcomes}
        assert outcomes.get("employee.employment_type.match") == "uncertain"


class TestPayPeriodMatch:
    def test_match(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(period=PayPeriod(year=2026, month=6)),
            employee=profile_employee,
            department=department,
            authorized=True,
            selected_year=2026,
            selected_month=6,
        )
        assert "employee.pay_period.match" not in _ids(report)

    def test_mismatch_warning_not_blocking_architecture(
        self,
        rules_loader: YamlLegalRulesLoader,
        profile_employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            payslip=PayslipData(period=PayPeriod(year=2026, month=1)),
            employee=profile_employee,
            department=department,
            authorized=True,
            selected_year=2026,
            selected_month=6,
        )
        findings = [f for f in report.findings if f.rule_id == "employee.pay_period.match"]
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.WARNING


class TestTaxonomyAndBindings:
    def test_employee_rules_map_to_employee_checks(self) -> None:
        assert taxonomy_for_rule_id("employee.national_id.match") == ValidationTaxonomy.EMPLOYEE
        assert ui_group_for_taxonomy(ValidationTaxonomy.EMPLOYEE) == "employee_checks"
        assert "employee.national_id.match" in bound_rule_ids_for_field("national_id")
        assert "employee.name.match" in bound_rule_ids_for_field("employee_name")
        assert "employee.pay_period.match" in bound_rule_ids_for_field("pay_period")
        assert "employee.employment_start_date.match" not in bound_rule_ids_for_field(
            "employment_start_date"
        )
