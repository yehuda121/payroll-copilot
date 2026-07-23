"""Unit tests for Phase 1A analytics foundation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from payroll_copilot.application.dto.validation_run import (
    ValidationFindingRecord,
    ValidationRunRecord,
)
from payroll_copilot.application.services.analytics.document_outcomes import (
    DocumentOutcome,
    classify_document_outcome,
)
from payroll_copilot.application.services.analytics.salary_values import salary_amounts_from_sources
from payroll_copilot.application.services.analytics_service import AnalyticsService
from payroll_copilot.application.use_cases.analytics_admin_census import GetAdminOrgCensusUseCase
from payroll_copilot.application.use_cases.analytics_admin_quality import (
    GetAdminQualityAnalyticsUseCase,
)
from payroll_copilot.application.use_cases.analytics_employee_salary import (
    GetEmployeeSalaryAnalyticsUseCase,
)
from payroll_copilot.application.use_cases.analytics_org_payroll import GetOrgPayrollAnalyticsUseCase
from payroll_copilot.application.use_cases.analytics_org_quality import GetOrgQualityAnalyticsUseCase
from payroll_copilot.domain.entities import Document, DocumentExtraction, Employee
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    FindingSeverity,
    RuleCategory,
    SalaryType,
    UserRole,
    ValidationResult,
    ValidationRunStatus,
)
from payroll_copilot.domain.value_objects import PayPeriod
from payroll_copilot.infrastructure.persistence.dynamodb.user_store import UserRecord


class _DocRepo:
    def __init__(self, docs: list[Document]) -> None:
        self._docs = docs

    async def list_for_employee(self, *, organization_id, employee_id):
        return [
            d
            for d in self._docs
            if d.organization_id == organization_id and d.employee_id == employee_id
        ]


class _ExtRepo:
    def __init__(self, by_doc: dict) -> None:
        self._by_doc = by_doc

    async def get_latest_for_document(self, document_id):
        return self._by_doc.get(document_id)


class _EmpRepo:
    def __init__(self, employees: list[Employee]) -> None:
        self._employees = employees

    async def list(self, filters):
        return [e for e in self._employees if e.organization_id == filters.organization_id]


class _RunRepo:
    def __init__(self, by_doc: dict) -> None:
        self._by_doc = by_doc

    async def list_latest_by_document_ids(self, document_ids):
        return {did: self._by_doc[did] for did in document_ids if did in self._by_doc}


class _FindingRepo:
    def __init__(self, by_run: dict) -> None:
        self._by_run = by_run

    async def list_by_run_id(self, run_id):
        return list(self._by_run.get(run_id, []))


class _UserStore:
    def __init__(self, users: list[UserRecord]) -> None:
        self._users = users

    async def list_for_organization(self, organization_id):
        return [u for u in self._users if u.organization_id == organization_id]


class _OrgDir:
    def __init__(self, ids: list) -> None:
        self._ids = ids

    async def list_organization_ids(self):
        return list(self._ids)


def _employee(org_id, *, accountant_id=None):
    return Employee(
        id=uuid4(),
        organization_id=org_id,
        employee_number="E-1",
        first_name="A",
        last_name="B",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        payroll_accountant_id=accountant_id,
    )


def _payslip(org_id, emp_id, *, year, month, status=DocumentStatus.PROCESSED, lifecycle="confirmed"):
    return Document(
        id=uuid4(),
        document_type=DocumentType.PAYSLIP,
        storage_key="k",
        original_filename="p.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="abc",
        status=status,
        organization_id=org_id,
        employee_id=emp_id,
        period=PayPeriod(year=year, month=month),
        metadata={"lifecycle_status": lifecycle, "publication_status": "published"},
        created_at=datetime(year, month, 1),
    )


def test_salary_amounts_prefer_structured_effective_value() -> None:
    net, gross, currency = salary_amounts_from_sources(
        structured_data={
            "net_salary": {"value": 9000, "status": "FOUND", "confidence": 0.9},
            "gross_salary": {"value": 12000, "status": "FOUND", "confidence": 0.9},
        },
        document_metadata={"net_salary": 1, "gross_salary": 2},
    )
    assert net == Decimal("9000")
    assert gross == Decimal("12000")
    assert currency == "ILS"


def test_classify_document_outcome_buckets() -> None:
    failed = SimpleNamespace(
        status=DocumentStatus.FAILED,
        metadata={"lifecycle_status": "extraction_failed"},
    )
    assert classify_document_outcome(failed, None) == DocumentOutcome.FAILED

    confirmed_ext = SimpleNamespace(confirmation_status="confirmed")
    ok = SimpleNamespace(status=DocumentStatus.PROCESSED, metadata={"lifecycle_status": "confirmed"})
    assert classify_document_outcome(ok, confirmed_ext) == DocumentOutcome.SUCCESS

    review = SimpleNamespace(
        status=DocumentStatus.PROCESSED,
        metadata={"lifecycle_status": "review_required"},
    )
    review_ext = SimpleNamespace(confirmation_status="review_required")
    assert classify_document_outcome(review, review_ext) == DocumentOutcome.REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_employee_salary_analytics_groups_by_period_year_month() -> None:
    org_id = uuid4()
    emp = _employee(org_id)
    d1 = _payslip(org_id, emp.id, year=2026, month=1)
    d2 = _payslip(org_id, emp.id, year=2026, month=2)
    d_other_year = _payslip(org_id, emp.id, year=2025, month=12)
    d_missing = Document(
        id=uuid4(),
        document_type=DocumentType.PAYSLIP,
        storage_key="k",
        original_filename="p.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="abc",
        status=DocumentStatus.PROCESSED,
        organization_id=org_id,
        employee_id=emp.id,
        period=None,
        metadata={"publication_status": "published"},
    )
    extractions = {
        d1.id: DocumentExtraction(
            id=uuid4(),
            document_id=d1.id,
            engine="test",
            raw_text="",
            structured_data={
                "net_salary": {"value": 8000, "status": "FOUND"},
                "gross_salary": {"value": 10000, "status": "FOUND"},
            },
            overall_confidence=0.91,
            confirmation_status="confirmed",
        ),
        d2.id: DocumentExtraction(
            id=uuid4(),
            document_id=d2.id,
            engine="test",
            raw_text="",
            structured_data={
                "net_salary": {"value": 8100, "status": "FOUND"},
                "gross_salary": {"value": 10100, "status": "FOUND"},
            },
            overall_confidence=0.88,
            confirmation_status="confirmed",
        ),
    }
    uc = GetEmployeeSalaryAnalyticsUseCase(
        documents=_DocRepo([d1, d2, d_other_year, d_missing]),
        extractions=_ExtRepo(extractions),
    )
    result = await uc.execute(organization_id=org_id, employee_id=emp.id, year=2026)
    assert result.year == 2026
    assert len(result.months) == 2
    assert result.months[0].period_month == 1
    assert result.months[0].net_salary == Decimal("8000")
    assert result.months[1].gross_salary == Decimal("10100")
    assert result.documents_missing_period == 1
    assert 2026 in result.available_years


@pytest.mark.asyncio
async def test_org_payroll_analytics_outcomes_and_validation() -> None:
    org_id = uuid4()
    emp = _employee(org_id)
    success_doc = _payslip(org_id, emp.id, year=2026, month=3, lifecycle="confirmed")
    failed_doc = _payslip(
        org_id,
        emp.id,
        year=2026,
        month=3,
        status=DocumentStatus.FAILED,
        lifecycle="extraction_failed",
    )
    run_id = uuid4()
    finding = ValidationFindingRecord(
        id=uuid4(),
        validation_run_id=run_id,
        rule_id="minimum_wage",
        rule_category=RuleCategory.LEGAL,
        severity=FindingSeverity.CRITICAL,
        message_key="validation.minimum_wage.below_threshold",
        message_params={},
        expected_value="5300",
        actual_value="4000",
        confidence=Decimal("0.9"),
    )
    run = ValidationRunRecord(
        id=run_id,
        document_id=success_doc.id,
        organization_id=org_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=5,
        rules_failed=1,
        overall_result=ValidationResult.CRITICAL,
        overall_confidence=Decimal("0.8"),
        findings=[],
    )
    extractions = {
        success_doc.id: DocumentExtraction(
            id=uuid4(),
            document_id=success_doc.id,
            engine="test",
            raw_text="",
            structured_data={},
            overall_confidence=0.77,
            confirmation_status="confirmed",
        ),
        failed_doc.id: DocumentExtraction(
            id=uuid4(),
            document_id=failed_doc.id,
            engine="test",
            raw_text="",
            structured_data={},
            overall_confidence=0.2,
            confirmation_status="review_required",
        ),
    }
    uc = GetOrgPayrollAnalyticsUseCase(
        employees=_EmpRepo([emp]),
        documents=_DocRepo([success_doc, failed_doc]),
        extractions=_ExtRepo(extractions),
        validation_runs=_RunRepo({success_doc.id: run}),
        validation_findings=_FindingRepo({run_id: [finding]}),
    )
    result = await uc.execute(organization_id=org_id, year=2026)
    assert len(result.documents_by_month) == 1
    point = result.documents_by_month[0]
    assert point.documents_processed == 2
    assert point.success == 1
    assert point.failed == 1
    assert result.validation_failures_by_month[0].failure_count == 1
    assert result.top_validation_failures[0].key == "minimum_wage"
    assert result.average_confidence_by_month[0].average_confidence == pytest.approx(0.485)


@pytest.mark.asyncio
async def test_admin_census_uses_payroll_accountant_id() -> None:
    org_id = uuid4()
    accountant_id = uuid4()
    employees = [
        _employee(org_id, accountant_id=accountant_id),
        _employee(org_id, accountant_id=accountant_id),
        _employee(org_id, accountant_id=None),
    ]
    users = [
        UserRecord(
            id=accountant_id,
            email="a@x.com",
            role=UserRole.ACCOUNTANT,
            organization_id=org_id,
        )
    ]
    uc = GetAdminOrgCensusUseCase(
        employees=_EmpRepo(employees),
        users=_UserStore(users),
        organizations=_OrgDir([org_id]),
    )
    result = await uc.execute()
    assert result.companies_count == 1
    assert result.employees_count == 3
    assert result.payroll_accountants_count == 1
    assert result.employees_without_payroll_accountant == 1
    assert result.employees_per_payroll_accountant[0].employee_count == 2


@pytest.mark.asyncio
async def test_analytics_service_registry_exposes_metric_names() -> None:
    org_id = uuid4()
    emp = _employee(org_id)
    org_quality = GetOrgQualityAnalyticsUseCase(
        employees=_EmpRepo([emp]),
        documents=_DocRepo([]),
        extractions=_ExtRepo({}),
        validation_runs=_RunRepo({}),
    )
    service = AnalyticsService(
        employee_salary=GetEmployeeSalaryAnalyticsUseCase(
            documents=_DocRepo([]),
            extractions=_ExtRepo({}),
        ),
        org_payroll=GetOrgPayrollAnalyticsUseCase(
            employees=_EmpRepo([emp]),
            documents=_DocRepo([]),
            extractions=_ExtRepo({}),
            validation_runs=_RunRepo({}),
            validation_findings=_FindingRepo({}),
        ),
        admin_census=GetAdminOrgCensusUseCase(
            employees=_EmpRepo([]),
            users=_UserStore([]),
            organizations=_OrgDir([]),
        ),
        org_quality=org_quality,
        admin_quality=GetAdminQualityAnalyticsUseCase(
            organizations=_OrgDir([]),
            org_quality=org_quality,
        ),
    )
    names = service.registry.names()
    assert "employee.salary" in names
    assert "org.payroll" in names
    assert "admin.census" in names
    assert "org.quality" in names
    assert "admin.quality" in names
