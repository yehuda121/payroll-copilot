"""Unit tests for Phase 2 Train 1 AI quality analytics."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.services.analytics.confidence_buckets import (
    bucket_confidence_values,
    rate,
)
from payroll_copilot.application.use_cases.analytics_admin_quality import (
    GetAdminQualityAnalyticsUseCase,
)
from payroll_copilot.application.use_cases.analytics_org_quality import GetOrgQualityAnalyticsUseCase
from payroll_copilot.domain.entities import Document, DocumentExtraction, Employee
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
    ValidationResult,
    ValidationRunStatus,
)
from payroll_copilot.domain.value_objects import PayPeriod


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


class _OrgDir:
    def __init__(self, ids: list) -> None:
        self._ids = ids

    async def list_organization_ids(self):
        return list(self._ids)


def _employee(org_id):
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


def test_confidence_buckets_and_rate() -> None:
    buckets = bucket_confidence_values([0.1, 0.55, 0.8, 1.0, -1, 2])
    assert [b.count for b in buckets] == [1, 1, 1, 1]
    assert rate(1, 0) is None
    assert rate(1, 4) == 0.25


@pytest.mark.asyncio
async def test_org_quality_metrics_from_existing_sot() -> None:
    org_id = uuid4()
    emp = _employee(org_id)
    ok_doc = _payslip(org_id, emp.id, year=2026, month=1, lifecycle="confirmed")
    fail_doc = _payslip(
        org_id,
        emp.id,
        year=2026,
        month=1,
        status=DocumentStatus.FAILED,
        lifecycle="extraction_failed",
    )
    review_doc = _payslip(org_id, emp.id, year=2026, month=2, lifecycle="review_required")

    run_ok = ValidationRunRecord(
        id=uuid4(),
        document_id=ok_doc.id,
        organization_id=org_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=3,
        rules_failed=0,
        overall_result=ValidationResult.PASS,
        overall_confidence=Decimal("0.9"),
        findings=[],
    )
    run_fail = ValidationRunRecord(
        id=uuid4(),
        document_id=fail_doc.id,
        organization_id=org_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=2,
        rules_failed=1,
        overall_result=ValidationResult.CRITICAL,
        overall_confidence=Decimal("0.4"),
        findings=[],
    )

    extractions = {
        ok_doc.id: DocumentExtraction(
            id=uuid4(),
            document_id=ok_doc.id,
            engine="test",
            raw_text="",
            structured_data={},
            overall_confidence=0.92,
            confirmation_status="confirmed",
            ocr_status="completed",
            parser_status="completed",
        ),
        fail_doc.id: DocumentExtraction(
            id=uuid4(),
            document_id=fail_doc.id,
            engine="test",
            raw_text="",
            structured_data={},
            overall_confidence=0.3,
            confirmation_status="review_required",
            ocr_status="failed",
            parser_status="failed",
        ),
        review_doc.id: DocumentExtraction(
            id=uuid4(),
            document_id=review_doc.id,
            engine="test",
            raw_text="",
            structured_data={},
            overall_confidence=0.6,
            confirmation_status="review_required",
            ocr_status="completed",
            parser_status="completed",
        ),
    }

    uc = GetOrgQualityAnalyticsUseCase(
        employees=_EmpRepo([emp]),
        documents=_DocRepo([ok_doc, fail_doc, review_doc]),
        extractions=_ExtRepo(extractions),
        validation_runs=_RunRepo({ok_doc.id: run_ok, fail_doc.id: run_fail}),
    )
    result = await uc.execute(organization_id=org_id, year=2026)

    assert len(result.months) == 2
    assert result.totals is not None
    assert result.totals.documents_processed == 3
    assert result.totals.extraction_attempted == 3
    assert result.totals.extraction_success == 2
    assert result.totals.extraction_success_rate == pytest.approx(2 / 3, rel=1e-3)
    assert result.totals.ocr_success == 2
    assert result.totals.ocr_failed == 1
    assert result.totals.validation_runs == 2
    assert result.totals.validation_pass == 1
    assert result.totals.validation_success_rate == pytest.approx(0.5)
    assert result.totals.failed_documents == 1
    assert result.totals.manual_review >= 2
    assert result.totals.average_confidence == pytest.approx((0.92 + 0.3 + 0.6) / 3)
    assert sum(b.count for b in result.confidence_distribution) == 3


@pytest.mark.asyncio
async def test_admin_quality_aggregates_orgs() -> None:
    org_a = uuid4()
    org_b = uuid4()
    emp_a = _employee(org_a)
    emp_b = _employee(org_b)
    doc_a = _payslip(org_a, emp_a.id, year=2026, month=3)
    doc_b = _payslip(org_b, emp_b.id, year=2026, month=3)

    extractions = {
        doc_a.id: DocumentExtraction(
            id=uuid4(),
            document_id=doc_a.id,
            engine="test",
            raw_text="",
            structured_data={},
            overall_confidence=0.9,
            confirmation_status="confirmed",
            ocr_status="completed",
            parser_status="completed",
        ),
        doc_b.id: DocumentExtraction(
            id=uuid4(),
            document_id=doc_b.id,
            engine="test",
            raw_text="",
            structured_data={},
            overall_confidence=0.4,
            confirmation_status="confirmed",
            ocr_status="completed",
            parser_status="failed",
        ),
    }
    org_quality = GetOrgQualityAnalyticsUseCase(
        employees=_EmpRepo([emp_a, emp_b]),
        documents=_DocRepo([doc_a, doc_b]),
        extractions=_ExtRepo(extractions),
        validation_runs=_RunRepo({}),
    )
    uc = GetAdminQualityAnalyticsUseCase(
        organizations=_OrgDir([org_a, org_b]),
        org_quality=org_quality,
    )
    result = await uc.execute(year=2026)
    assert result.organizations_count == 2
    assert len(result.organizations) == 2
    assert result.totals is not None
    assert result.totals.documents_processed == 2
    assert result.totals.extraction_success == 1
    assert sum(b.count for b in result.confidence_distribution) == 2
