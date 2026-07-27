"""Employee month detail exposes persisted rule_outcomes + finding rule_id."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from payroll_copilot.application.dto.validation_run import (
    ValidationFindingRecord,
    ValidationRunRecord,
)
from payroll_copilot.application.use_cases.employee_payroll_months import (
    BuildEmployeePayrollMonthsUseCase,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction, Employee
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    FindingSeverity,
    RuleCategory,
    SalaryType,
    ValidationResult,
    ValidationRunStatus,
)
from payroll_copilot.domain.value_objects import PayPeriod

ORG = uuid4()
EMP = uuid4()
DOC = uuid4()
RUN = uuid4()


class _Docs:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs

    async def list_for_employee(self, *, organization_id, employee_id):  # noqa: ANN001
        return [
            d
            for d in self.docs
            if d.organization_id == organization_id and d.employee_id == employee_id
        ]

    async def save(self, document):  # noqa: ANN001
        self.docs = [document if d.id == document.id else d for d in self.docs]
        if not any(d.id == document.id for d in self.docs):
            self.docs.append(document)
        return document


class _Runs:
    def __init__(self, run: ValidationRunRecord) -> None:
        self.run = run

    async def list_latest_by_document_ids(self, document_ids):  # noqa: ANN001
        out = {}
        for did in document_ids:
            if did == self.run.document_id:
                out[did] = self.run
        return out

    async def list_for_document(self, document_id):  # noqa: ANN001
        return [self.run] if document_id == self.run.document_id else []


class _Findings:
    def __init__(self, findings: list[ValidationFindingRecord]) -> None:
        self.findings = findings

    async def list_by_run_id(self, run_id):  # noqa: ANN001
        return [f for f in self.findings if f.validation_run_id == run_id]


class _Extractions:
    async def get_latest_for_document(self, document_id):  # noqa: ANN001
        return DocumentExtraction(
            id=uuid4(),
            document_id=document_id,
            engine="test",
            raw_text="x",
            structured_data={"employee_name": {"value": "Dana", "status": "FOUND"}},
            confirmation_status="confirmed",
        )


@pytest.mark.asyncio
async def test_month_detail_includes_rule_outcomes_and_finding_rule_id() -> None:
    doc = Document(
        id=DOC,
        document_type=DocumentType.PAYSLIP,
        storage_key="k",
        original_filename="f.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="x",
        status=DocumentStatus.PROCESSED,
        organization_id=ORG,
        employee_id=EMP,
        period=PayPeriod(year=2026, month=6),
        created_at=datetime.utcnow(),
        metadata={"manual_approvals": []},
    )
    finding = ValidationFindingRecord(
        id=uuid4(),
        validation_run_id=RUN,
        rule_id="employee.national_id.match",
        rule_category=RuleCategory.EMPLOYEE,
        severity=FindingSeverity.CRITICAL,
        message_key="validation.employee.national_id.mismatch",
        message_params={},
        expected_value=None,
        actual_value=None,
        confidence=Decimal("0.9"),
    )
    run = ValidationRunRecord(
        id=RUN,
        document_id=DOC,
        organization_id=ORG,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=3,
        rules_failed=1,
        employee_id=EMP,
        overall_result=ValidationResult.CRITICAL,
        overall_confidence=Decimal("0.8"),
        context_snapshot={
            "rule_outcomes": [
                {
                    "rule_id": "employee.national_id.match",
                    "outcome": "failed",
                    "skip_reason": None,
                    "reason_code": None,
                    "message": None,
                },
                {
                    "rule_id": "legal.minimum_wage",
                    "outcome": "passed",
                    "skip_reason": None,
                    "reason_code": None,
                    "message": None,
                },
                {
                    "rule_id": "employee.name.match",
                    "outcome": "uncertain",
                    "skip_reason": None,
                    "reason_code": "MISSING_PAYSLIP_DATA",
                    "message": "missing",
                },
            ]
        },
        completed_at=datetime.utcnow(),
    )
    employee = Employee(
        id=EMP,
        organization_id=ORG,
        employee_number="1",
        first_name="A",
        last_name="B",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=datetime.utcnow().date(),
        status=EmployeeStatus.ACTIVE,
    )
    uc = BuildEmployeePayrollMonthsUseCase(
        documents=_Docs([doc]),
        validation_runs=_Runs(run),
        validation_findings=_Findings([finding]),
        extractions=_Extractions(),
    )
    detail = await uc.month_detail(
        organization_id=ORG,
        employee_id=EMP,
        year=2026,
        month=6,
        employee=employee,
        national_id_encrypted=None,
    )
    latest = detail["latest_validation"]
    assert latest["exists"] is True
    outcomes = {item["rule_id"]: item for item in latest["rule_outcomes"]}
    assert outcomes["employee.national_id.match"]["outcome"] == "failed"
    assert outcomes["legal.minimum_wage"]["outcome"] == "passed"
    assert latest["findings"][0]["rule_id"] == "employee.national_id.match"
    # Legacy field preserved.
    assert latest["findings"][0]["code"] == "validation.employee.national_id.mismatch"
