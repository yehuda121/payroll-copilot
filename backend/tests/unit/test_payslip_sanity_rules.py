"""Deterministic payslip SANITY rules — document-only."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

import payroll_copilot.domain.rules.departments  # noqa: F401
import payroll_copilot.domain.rules.historical  # noqa: F401
import payroll_copilot.domain.rules.legal  # noqa: F401
import payroll_copilot.domain.rules.sanity  # noqa: F401
from payroll_copilot.application.services.validation_taxonomy import (
    ValidationTaxonomy,
    bound_rule_ids_for_field,
    taxonomy_for_rule_id,
)
from payroll_copilot.application.use_cases.validation import RunValidationCommand, RunValidationUseCase
from payroll_copilot.application.validation.structured_payslip_mapper import (
    map_structured_payslip_to_validation_inputs,
)
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

# Known-good Israeli ID used across the codebase (checksum valid).
_VALID_NATIONAL_ID = "313366783"
_BAD_CHECKSUM_ID = "313366784"


@pytest.fixture
def rules_loader() -> YamlLegalRulesLoader:
    return YamlLegalRulesLoader("config/rules/labor_law")


@pytest.fixture
def employee() -> Employee:
    return Employee(
        id=uuid4(),
        organization_id=uuid4(),
        employee_number="1001",
        first_name="Dana",
        last_name="Cohen",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("12000"),
    )


@pytest.fixture
def department(employee: Employee) -> Department:
    return Department(
        id=employee.department_id,
        organization_id=employee.organization_id,
        code="payroll",
        name={"he": "שכר", "en": "Payroll"},
        rule_profile="payroll",
    )


def _run(
    rules_loader: YamlLegalRulesLoader,
    employee: Employee,
    department: Department,
    payslip: PayslipData,
) -> object:
    return RunValidationUseCase(rules_loader).execute(
        RunValidationCommand(
            payslip=payslip,
            employee=employee,
            department=department,
            period=payslip.period or PayPeriod(year=2026, month=6),
            field_confidences={},
        )
    )


def _finding_ids(report: object) -> set[str]:
    return {f.rule_id for f in report.findings}  # type: ignore[attr-defined]


class TestNationalIdSanity:
    def test_valid_national_id_passes_structural_rules(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        payslip = PayslipData(
            employee_name="דנה כהן",
            period=PayPeriod(year=2026, month=6),
            gross_salary=Money(Decimal("10000")),
            net_salary=Money(Decimal("8000")),
            additional_fields={"national_id": _VALID_NATIONAL_ID},
        )
        report = _run(rules_loader, employee, department, payslip)
        ids = _finding_ids(report)
        assert "sanity.national_id.length" not in ids
        assert "sanity.national_id.checksum" not in ids

    def test_wrong_length_fails(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        payslip = PayslipData(additional_fields={"national_id": "1234567"})
        report = _run(rules_loader, employee, department, payslip)
        length = [f for f in report.findings if f.rule_id == "sanity.national_id.length"]
        assert len(length) == 1
        assert length[0].severity == FindingSeverity.WARNING

    def test_bad_checksum_fails(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        payslip = PayslipData(additional_fields={"national_id": _BAD_CHECKSUM_ID})
        report = _run(rules_loader, employee, department, payslip)
        checksum = [f for f in report.findings if f.rule_id == "sanity.national_id.checksum"]
        assert len(checksum) == 1

    def test_legacy_employee_id_eight_or_nine_digits(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        payslip = PayslipData(additional_fields={"employee_id": _VALID_NATIONAL_ID})
        report = _run(rules_loader, employee, department, payslip)
        assert "sanity.national_id.checksum" not in _finding_ids(report)

    def test_short_payroll_employee_id_not_treated_as_national_id(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        payslip = PayslipData(additional_fields={"employee_id": "1001"})
        report = _run(rules_loader, employee, department, payslip)
        assert "sanity.national_id.length" not in _finding_ids(report)


class TestEmployeeNameSanity:
    @pytest.mark.parametrize(
        "name",
        ["Dana Cohen", "דנה כהן", "دانا كوهين", "Anne-Marie O'Neil"],
    )
    def test_unicode_names_pass(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
        name: str,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(employee_name=name),
        )
        assert "sanity.employee_name.structure" not in _finding_ids(report)

    def test_numeric_name_fails(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(employee_name="123456"),
        )
        findings = [f for f in report.findings if f.rule_id == "sanity.employee_name.structure"]
        assert len(findings) == 1


class TestPayPeriodSanity:
    def test_valid_period_passes(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(period=PayPeriod(year=2026, month=6)),
        )
        ids = _finding_ids(report)
        assert "sanity.pay_period.parseable" not in ids
        assert "sanity.pay_period.calendar" not in ids

    def test_invalid_month_in_raw_fails(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(additional_fields={"pay_period_raw": "13/2024"}),
        )
        findings = [f for f in report.findings if f.rule_id == "sanity.pay_period.parseable"]
        assert len(findings) == 1
        assert findings[0].message_key == "validation.sanity.pay_period.month"

    def test_hebrew_freeform_not_structural_fail(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(additional_fields={"pay_period_raw": "יוני 2024"}),
        )
        assert "sanity.pay_period.parseable" not in _finding_ids(report)

    def test_year_out_of_window_fails(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(period=PayPeriod(year=1800, month=6)),
        )
        findings = [f for f in report.findings if f.rule_id == "sanity.pay_period.calendar"]
        assert len(findings) == 1


class TestEmploymentStartDateSanity:
    def test_valid_date_passes(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(additional_fields={"employment_start_date": "2020-03-15"}),
        )
        assert "sanity.employment_start_date.calendar" not in _finding_ids(report)

    def test_invalid_calendar_date_fails(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(additional_fields={"employment_start_date": "2020-02-30"}),
        )
        findings = [
            f for f in report.findings if f.rule_id == "sanity.employment_start_date.calendar"
        ]
        assert len(findings) == 1


class TestNetGrossSanity:
    def test_net_exceeds_gross_fails(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(
                gross_salary=Money(Decimal("8000")),
                net_salary=Money(Decimal("9000")),
            ),
        )
        findings = [
            f for f in report.findings if f.rule_id == "sanity.net_salary.not_exceed_gross"
        ]
        assert len(findings) == 1
        assert report.overall_result == ValidationResult.WARNINGS.value

    def test_net_within_gross_passes(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(
                gross_salary=Money(Decimal("9000")),
                net_salary=Money(Decimal("8000")),
            ),
        )
        assert "sanity.net_salary.not_exceed_gross" not in _finding_ids(report)


class TestRequiredPresenceSanity:
    def test_missing_required_is_info_not_blocker(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(rules_loader, employee, department, PayslipData())
        missing = [
            f
            for f in report.findings
            if f.rule_id.startswith("sanity.required.")
            and f.message_key == "validation.sanity.required_field_missing"
        ]
        assert len(missing) >= 1
        assert all(f.severity == FindingSeverity.INFO for f in missing)
        # INFO does not escalate overall result by itself.
        assert report.overall_result == ValidationResult.PASS.value
        # INFO required findings must not inflate rules_failed.
        assert report.rules_failed == 0
        assert report.rules_failed < len(report.findings)

    def test_present_required_national_id_no_missing_finding(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(additional_fields={"national_id": _VALID_NATIONAL_ID}),
        )
        assert "sanity.required.national_id" not in _finding_ids(report)

    def test_warning_still_counts_as_rules_failed(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(
                gross_salary=Money(Decimal("8000")),
                net_salary=Money(Decimal("9000")),
            ),
        )
        assert report.rules_failed >= 1
        assert any(
            f.severity == FindingSeverity.WARNING and f.rule_id == "sanity.net_salary.not_exceed_gross"
            for f in report.findings
        )
        info_count = sum(1 for f in report.findings if f.severity == FindingSeverity.INFO)
        warning_or_critical = sum(
            1
            for f in report.findings
            if f.severity in (FindingSeverity.WARNING, FindingSeverity.CRITICAL)
        )
        assert report.rules_failed == warning_or_critical
        assert info_count > 0  # required-field INFO still present alongside the warning


class TestEmploymentTypeMapping:
    def test_recognized_maps_and_preserves_raw(self) -> None:
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=uuid4(),
            structured_data={
                "employment_type": {
                    "value": "part_time",
                    "status": "FOUND",
                    "confidence": 0.9,
                }
            },
        )
        assert mapped.command.employee.employment_type == EmploymentType.PART_TIME
        assert mapped.command.payslip.additional_fields.get("employment_type") == "part_time"

    def test_unknown_does_not_become_full_time(self) -> None:
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=uuid4(),
            structured_data={
                "employment_type": {
                    "value": "חודשי",
                    "status": "FOUND",
                    "confidence": 0.9,
                }
            },
        )
        assert mapped.command.employee.employment_type == EmploymentType.UNKNOWN
        assert mapped.command.payslip.additional_fields.get("employment_type") == "חודשי"
        assert "employment_type_unrecognized" in mapped.mapping_warnings

    def test_missing_employment_type_is_unknown_not_full_time(self) -> None:
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=uuid4(),
            structured_data={},
        )
        assert mapped.command.employee.employment_type == EmploymentType.UNKNOWN
        assert "employment_type" not in mapped.command.payslip.additional_fields

    def test_hourly_salary_mode_is_not_invented_employment_type(self) -> None:
        # "hourly" is a salary mode, not EmploymentType — must not crash or become FULL_TIME.
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=uuid4(),
            structured_data={
                "employment_type": {
                    "value": "hourly",
                    "status": "FOUND",
                    "confidence": 0.9,
                }
            },
        )
        assert mapped.command.employee.employment_type == EmploymentType.UNKNOWN

    def test_unrecognized_employment_type_sanity_warning(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(additional_fields={"employment_type": "not-a-real-type"}),
        )
        findings = [
            f for f in report.findings if f.rule_id == "sanity.employment_type.recognized"
        ]
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.WARNING

    def test_recognized_employment_type_no_sanity_finding(
        self,
        rules_loader: YamlLegalRulesLoader,
        employee: Employee,
        department: Department,
    ) -> None:
        report = _run(
            rules_loader,
            employee,
            department,
            PayslipData(additional_fields={"employment_type": "intern"}),
        )
        assert "sanity.employment_type.recognized" not in _finding_ids(report)

    def test_unknown_does_not_activate_full_time_overtime_rule(
        self,
        rules_loader: YamlLegalRulesLoader,
        department: Department,
    ) -> None:
        """Synthetic UNKNOWN must not inherit FULL_TIME overtime applicability."""
        unknown_employee = Employee(
            id=uuid4(),
            organization_id=department.organization_id,
            employee_number="u1",
            first_name="U",
            last_name="N",
            department_id=department.id,
            employment_type=EmploymentType.UNKNOWN,
            salary_type=SalaryType.MONTHLY,
            contract_start_date=date(2024, 1, 1),
            status=EmployeeStatus.ACTIVE,
        )
        report = RunValidationUseCase(rules_loader).execute(
            RunValidationCommand(
                payslip=PayslipData(overtime_hours=Decimal("10")),
                employee=unknown_employee,
                department=department,
                period=PayPeriod(year=2026, month=6),
                field_confidences={"overtime_hours": 1.0},
            )
        )
        assert "legal.overtime.daily_limit" not in _finding_ids(report)


class TestMapperPreservesSanityInputs:
    def test_unparseable_period_preserved_as_raw(self) -> None:
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=uuid4(),
            structured_data={
                "pay_period": {
                    "value": "13/2024",
                    "status": "FOUND",
                    "confidence": 0.9,
                }
            },
        )
        assert mapped.command.payslip.period is None
        assert mapped.command.payslip.additional_fields.get("pay_period_raw") == "13/2024"

    def test_missing_name_not_invented(self) -> None:
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=uuid4(),
            structured_data={},
        )
        assert mapped.command.payslip.employee_name is None

    def test_employee_id_preserved_for_legacy_national_id(self) -> None:
        mapped = map_structured_payslip_to_validation_inputs(
            document_id=uuid4(),
            structured_data={
                "employee_id": {
                    "value": _VALID_NATIONAL_ID,
                    "status": "FOUND",
                    "confidence": 0.9,
                }
            },
        )
        assert mapped.command.payslip.additional_fields.get("employee_id") == _VALID_NATIONAL_ID


class TestSanityTaxonomyBindings:
    def test_sanity_rules_map_to_sanity_taxonomy(self) -> None:
        assert taxonomy_for_rule_id("sanity.national_id.checksum") == ValidationTaxonomy.SANITY
        assert taxonomy_for_rule_id("sanity.required.base_salary") == ValidationTaxonomy.SANITY
        assert taxonomy_for_rule_id("sanity.unknown.future") == ValidationTaxonomy.SANITY

    def test_field_bindings_include_sanity(self) -> None:
        assert "sanity.national_id.length" in bound_rule_ids_for_field("national_id")
        assert "sanity.required.national_id" in bound_rule_ids_for_field("national_id")
        assert "sanity.net_salary.not_exceed_gross" in bound_rule_ids_for_field("net_salary")
        assert "sanity.required.base_salary" in bound_rule_ids_for_field("base_salary")
