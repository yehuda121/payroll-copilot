"""Unit tests for employee payroll-month status aggregation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.services.employee_payroll_month_status import (
    PRESENTATION_ERROR,
    PRESENTATION_PASSED,
    PRESENTATION_UNAVAILABLE,
    PRESENTATION_WARNING,
    compute_presentation_status,
)
from payroll_copilot.application.use_cases.employee_payroll_months import (
    BuildEmployeePayrollMonthsUseCase,
)
from payroll_copilot.domain.entities import Document
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    ValidationResult,
    ValidationRunStatus,
)
from payroll_copilot.domain.value_objects import PayPeriod

ORG = uuid4()
EMP_A = uuid4()
EMP_B = uuid4()


class _Docs:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs

    async def list_for_employee(self, *, organization_id, employee_id):  # noqa: ANN001
        return [
            d
            for d in self.docs
            if d.organization_id == organization_id and d.employee_id == employee_id
        ]


class _Runs:
    def __init__(self, mapping: dict) -> None:
        self.mapping = mapping

    async def list_latest_by_document_ids(self, document_ids):  # noqa: ANN001
        return {did: self.mapping[did] for did in document_ids if did in self.mapping}


class _Findings:
    async def list_by_run_id(self, run_id):  # noqa: ANN001
        return []


def _doc(employee_id, year, month, dtype=DocumentType.PAYSLIP) -> Document:
    return Document(
        id=uuid4(),
        document_type=dtype,
        storage_key="k",
        original_filename="f.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="x",
        status=DocumentStatus.UPLOADED,
        organization_id=ORG,
        employee_id=employee_id,
        period=PayPeriod(year=year, month=month),
        created_at=datetime.utcnow(),
    )


def test_presentation_priority():
    assert (
        compute_presentation_status(
            payslip_exists=False,
            validation_exists=False,
            overall_result=None,
            highest_finding_severity=None,
            overall_confidence=None,
        )
        == PRESENTATION_UNAVAILABLE
    )
    assert (
        compute_presentation_status(
            payslip_exists=True,
            validation_exists=False,
            overall_result=None,
            highest_finding_severity=None,
            overall_confidence=None,
        )
        == PRESENTATION_UNAVAILABLE
    )
    assert (
        compute_presentation_status(
            payslip_exists=True,
            validation_exists=True,
            overall_result="critical",
            highest_finding_severity="warning",
            overall_confidence=0.9,
        )
        == PRESENTATION_ERROR
    )
    assert (
        compute_presentation_status(
            payslip_exists=True,
            validation_exists=True,
            overall_result="warnings",
            highest_finding_severity="warning",
            overall_confidence=0.9,
        )
        == PRESENTATION_WARNING
    )
    assert (
        compute_presentation_status(
            payslip_exists=True,
            validation_exists=True,
            overall_result="pass",
            highest_finding_severity=None,
            overall_confidence=0.5,
        )
        == PRESENTATION_WARNING
    )
    assert (
        compute_presentation_status(
            payslip_exists=True,
            validation_exists=True,
            overall_result="pass",
            highest_finding_severity=None,
            overall_confidence=0.9,
        )
        == PRESENTATION_PASSED
    )


@pytest.mark.asyncio
async def test_year_returns_twelve_months_and_current_year_when_empty():
    use_case = BuildEmployeePayrollMonthsUseCase(
        documents=_Docs([]),  # type: ignore[arg-type]
        validation_runs=_Runs({}),  # type: ignore[arg-type]
        validation_findings=_Findings(),  # type: ignore[arg-type]
    )
    result = await use_case.execute(
        organization_id=ORG,
        employee_id=EMP_A,
        year=2026,
        current_year=2026,
    )
    assert result["year"] == 2026
    assert result["available_years"] == [2026]
    assert len(result["months"]) == 12
    assert all(m["presentation_status"] == PRESENTATION_UNAVAILABLE for m in result["months"])


@pytest.mark.asyncio
async def test_employee_isolation_and_latest_validation():
    payslip_a = _doc(EMP_A, 2026, 6)
    payslip_b = _doc(EMP_B, 2026, 6)
    attendance = _doc(EMP_A, 2026, 6, DocumentType.ATTENDANCE)
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=payslip_a.id,
        organization_id=ORG,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=3,
        rules_failed=0,
        employee_id=EMP_A,
        overall_result=ValidationResult.PASS,
        overall_confidence=Decimal("0.91"),
        completed_at=datetime.utcnow(),
    )
    use_case = BuildEmployeePayrollMonthsUseCase(
        documents=_Docs([payslip_a, payslip_b, attendance]),  # type: ignore[arg-type]
        validation_runs=_Runs({payslip_a.id: run}),  # type: ignore[arg-type]
        validation_findings=_Findings(),  # type: ignore[arg-type]
    )
    result = await use_case.execute(organization_id=ORG, employee_id=EMP_A, year=2026)
    june = result["months"][5]
    assert june["payslip"]["exists"] is True
    assert june["payslip"]["document_id"] == str(payslip_a.id)
    assert june["attendance"]["exists"] is True
    assert june["attendance"]["analysis_status"] == "not_connected"
    assert june["latest_validation"]["exists"] is True
    assert june["presentation_status"] == PRESENTATION_PASSED

    other = await use_case.execute(organization_id=ORG, employee_id=EMP_B, year=2026)
    other_june = other["months"][5]
    assert other_june["payslip"]["document_id"] == str(payslip_b.id)
    assert other_june["latest_validation"]["exists"] is False


@pytest.mark.asyncio
async def test_accountant_draft_is_hidden_from_employee_until_published():
    draft = _doc(EMP_A, 2026, 7)
    draft.metadata = {
        "publication_status": "draft",
        "review_status": "pending_review",
    }
    use_case = BuildEmployeePayrollMonthsUseCase(
        documents=_Docs([draft]),  # type: ignore[arg-type]
        validation_runs=_Runs({}),  # type: ignore[arg-type]
        validation_findings=_Findings(),  # type: ignore[arg-type]
    )

    employee_view = await use_case.execute(
        organization_id=ORG,
        employee_id=EMP_A,
        year=2026,
    )
    accountant_view = await use_case.execute(
        organization_id=ORG,
        employee_id=EMP_A,
        year=2026,
        include_unpublished=True,
    )

    assert employee_view["months"][6]["payslip"]["exists"] is False
    assert accountant_view["months"][6]["payslip"]["document_id"] == str(draft.id)
