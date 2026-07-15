"""Ownership and immutability checks for employee finding explanations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from payroll_copilot.application.exceptions import DocumentNotOwnedError
from payroll_copilot.application.use_cases.explain_employee_finding import (
    ExplainEmployeeFindingUseCase,
    FindingNotFoundError,
)
from payroll_copilot.application.dto.validation_run import ValidationFindingRecord, ValidationRunRecord
from payroll_copilot.domain.entities import Document, Employee
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    FindingSeverity,
    RuleCategory,
    SalaryType,
    ValidationRunStatus,
)
from datetime import date

ORG = uuid4()
EMP = uuid4()
OTHER = uuid4()
USER = uuid4()
RUN = uuid4()
FINDING = uuid4()
DOC = uuid4()


class _Docs:
    def __init__(self, doc: Document) -> None:
        self.doc = doc

    async def get_by_id(self, document_id):  # noqa: ANN001
        return self.doc if self.doc.id == document_id else None


class _Runs:
    def __init__(self, run: ValidationRunRecord) -> None:
        self.run = run

    async def get_by_id(self, run_id):  # noqa: ANN001
        return self.run if self.run.id == run_id else None


class _Findings:
    def __init__(self, finding: ValidationFindingRecord) -> None:
        self.finding = finding

    async def list_by_run_id(self, run_id):  # noqa: ANN001
        return [self.finding] if run_id == self.finding.validation_run_id else []


def _employee(emp_id=EMP) -> Employee:
    return Employee(
        id=emp_id,
        organization_id=ORG,
        employee_number="5",
        first_name="Yehuda",
        last_name="Shmulovitz",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 1, 1),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("1"),
    )


@pytest.mark.asyncio
async def test_explain_rejects_other_employees_run() -> None:
    doc = Document(
        id=DOC,
        document_type=DocumentType.PAYSLIP,
        storage_key="k",
        original_filename="a.pdf",
        mime_type="application/pdf",
        file_size_bytes=1,
        checksum_sha256="x",
        status=DocumentStatus.PROCESSED,
        organization_id=ORG,
        employee_id=OTHER,
        created_at=datetime.utcnow(),
    )
    run = ValidationRunRecord(
        id=RUN,
        document_id=DOC,
        organization_id=ORG,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=1,
        rules_failed=1,
        employee_id=OTHER,
    )
    finding = ValidationFindingRecord(
        id=FINDING,
        validation_run_id=RUN,
        rule_id="r1",
        rule_category=RuleCategory.LEGAL,
        severity=FindingSeverity.CRITICAL,
        message_key="fail.nid",
        message_params={},
        expected_value="a",
        actual_value="b",
        confidence=Decimal("1"),
    )
    use_case = ExplainEmployeeFindingUseCase(
        documents=_Docs(doc),  # type: ignore[arg-type]
        validation_runs=_Runs(run),  # type: ignore[arg-type]
        validation_findings=_Findings(finding),  # type: ignore[arg-type]
    )
    with pytest.raises(DocumentNotOwnedError):
        await use_case.execute(
            employee=_employee(),
            user_id=USER,
            validation_run_id=RUN,
            finding_id=FINDING,
        )


@pytest.mark.asyncio
async def test_explain_does_not_change_finding_status() -> None:
    doc = Document(
        id=DOC,
        document_type=DocumentType.PAYSLIP,
        storage_key="k",
        original_filename="a.pdf",
        mime_type="application/pdf",
        file_size_bytes=1,
        checksum_sha256="x",
        status=DocumentStatus.PROCESSED,
        organization_id=ORG,
        employee_id=EMP,
        created_at=datetime.utcnow(),
    )
    run = ValidationRunRecord(
        id=RUN,
        document_id=DOC,
        organization_id=ORG,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=1,
        rules_failed=1,
        employee_id=EMP,
    )
    finding = ValidationFindingRecord(
        id=FINDING,
        validation_run_id=RUN,
        rule_id="r1",
        rule_category=RuleCategory.LEGAL,
        severity=FindingSeverity.CRITICAL,
        message_key="fail.nid",
        message_params={},
        expected_value="a",
        actual_value="b",
        confidence=Decimal("1"),
        legal_reference="Rule pack X",
    )
    use_case = ExplainEmployeeFindingUseCase(
        documents=_Docs(doc),  # type: ignore[arg-type]
        validation_runs=_Runs(run),  # type: ignore[arg-type]
        validation_findings=_Findings(finding),  # type: ignore[arg-type]
    )
    result = await use_case.execute(
        employee=_employee(),
        user_id=USER,
        validation_run_id=RUN,
        finding_id=FINDING,
    )
    assert result["validation_status"] == "failed"
    assert finding.severity == FindingSeverity.CRITICAL
    assert result["disclaimer_key"] == "employee.validation.aiExplanationDisclaimer"
    assert result["explanation"]


@pytest.mark.asyncio
async def test_explain_missing_finding() -> None:
    doc = Document(
        id=DOC,
        document_type=DocumentType.PAYSLIP,
        storage_key="k",
        original_filename="a.pdf",
        mime_type="application/pdf",
        file_size_bytes=1,
        checksum_sha256="x",
        status=DocumentStatus.PROCESSED,
        organization_id=ORG,
        employee_id=EMP,
        created_at=datetime.utcnow(),
    )
    run = ValidationRunRecord(
        id=RUN,
        document_id=DOC,
        organization_id=ORG,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=0,
        rules_failed=0,
        employee_id=EMP,
    )
    finding = ValidationFindingRecord(
        id=FINDING,
        validation_run_id=RUN,
        rule_id="r1",
        rule_category=RuleCategory.LEGAL,
        severity=FindingSeverity.WARNING,
        message_key="warn",
        message_params={},
        expected_value=None,
        actual_value=None,
        confidence=Decimal("1"),
    )
    use_case = ExplainEmployeeFindingUseCase(
        documents=_Docs(doc),  # type: ignore[arg-type]
        validation_runs=_Runs(run),  # type: ignore[arg-type]
        validation_findings=_Findings(finding),  # type: ignore[arg-type]
    )
    with pytest.raises(FindingNotFoundError):
        await use_case.execute(
            employee=_employee(),
            user_id=USER,
            validation_run_id=RUN,
            finding_id=uuid4(),
        )
