"""Tests for employee extraction confirmation gating."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from payroll_copilot.application.exceptions import ExtractionNotConfirmedError
from payroll_copilot.application.use_cases.validate_employee_payslip import (
    ValidateEmployeePayslipUseCase,
)
from payroll_copilot.domain.entities import Document, DocumentExtraction, Employee
from payroll_copilot.domain.enums import (
    DocumentStatus,
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
)
from payroll_copilot.domain.value_objects import PayPeriod

ORG = uuid4()
EMP = uuid4()
USER = uuid4()


class _Docs:
    def __init__(self, doc: Document) -> None:
        self.doc = doc

    async def get_by_id(self, document_id):  # noqa: ANN001
        return self.doc if self.doc.id == document_id else None


class _Extractions:
    def __init__(self, extraction: DocumentExtraction) -> None:
        self.extraction = extraction

    async def get_latest_for_document(self, document_id):  # noqa: ANN001
        return self.extraction if self.extraction.document_id == document_id else None


@pytest.mark.asyncio
async def test_validation_rejects_unconfirmed_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "payroll_copilot.application.use_cases.validate_employee_payslip.decrypt_national_id",
        lambda *a, **k: "313366783",
    )
    doc = Document(
        id=uuid4(),
        document_type=DocumentType.PAYSLIP,
        storage_key="k",
        original_filename="a.pdf",
        mime_type="application/pdf",
        file_size_bytes=1,
        checksum_sha256="x",
        status=DocumentStatus.PROCESSED,
        organization_id=ORG,
        employee_id=EMP,
        period=PayPeriod(year=2026, month=6),
        metadata={"selected_period_year": 2026, "selected_period_month": 6},
        created_at=datetime.utcnow(),
    )
    extraction = DocumentExtraction(
        id=uuid4(),
        document_id=doc.id,
        engine="fake",
        raw_text="x",
        structured_data={
            "employee_id": {"value": "313366783", "status": "FOUND", "confidence": 0.95},
            "pay_period": {"value": "06/2026", "status": "FOUND", "confidence": 0.95},
        },
        confirmation_status="review_required",
    )
    employee = Employee(
        id=EMP,
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
        metadata={"national_id_masked": "****6783"},
    )

    class _Never:
        async def execute(self, command):  # noqa: ANN001
            raise AssertionError("must not run")

    use_case = ValidateEmployeePayslipUseCase(
        documents=_Docs(doc),  # type: ignore[arg-type]
        extractions=_Extractions(extraction),  # type: ignore[arg-type]
        validation=_Never(),  # type: ignore[arg-type]
    )
    with pytest.raises(ExtractionNotConfirmedError):
        await use_case.execute(
            document_id=doc.id,
            employee=employee,
            user_id=USER,
            national_id_encrypted=b"x",
        )
