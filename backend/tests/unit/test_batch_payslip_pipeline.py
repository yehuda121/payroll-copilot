from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.services.batch_payslip_pipeline import (
    BatchPayslipPipelineService,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractedFieldView,
    GuestPayslipExtractionResult,
)
from payroll_copilot.domain.entities import Document, Employee
from payroll_copilot.domain.enums import (
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
    ValidationResult,
    ValidationRunStatus,
)


def _field(key: str, value: object) -> ExtractedFieldView:
    return ExtractedFieldView(
        key=key,
        value=value,
        confidence=0.99,
        source_text=str(value),
        status="FOUND",
    )


def _employee(organization_id, employee_id) -> Employee:
    return Employee(
        id=employee_id,
        organization_id=organization_id,
        employee_number="EMP-7",
        first_name="Dana",
        last_name="Levi",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("12000"),
        metadata={"national_id_masked": "****6782"},
    )


@pytest.mark.asyncio
async def test_batch_slip_reuses_extract_confirm_and_validation_use_cases() -> None:
    organization_id = uuid4()
    actor_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    extraction_id = uuid4()
    employee = _employee(organization_id, employee_id)
    fields = [
        _field("employee_id", "123456782"),
        _field("employee_number", "EMP-7"),
        _field("pay_period", "2026-06"),
    ]
    extract = SimpleNamespace(
        execute=AsyncMock(
            return_value=GuestPayslipExtractionResult(
                document_id=document_id,
                extraction_id=extraction_id,
                ocr_status="completed",
                parser_status="completed",
                language="he",
                ocr_engine="test-ocr",
                parser_model="test-parser",
                warnings=[],
                fields=fields,
                raw_text="payslip",
            )
        )
    )
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/test",
        original_filename="slip.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    documents = SimpleNamespace(
        get_by_id=AsyncMock(return_value=document),
        find_payslip_for_period=AsyncMock(return_value=None),
        save=AsyncMock(side_effect=lambda value: value),
    )
    extractions = SimpleNamespace(
        get_latest_for_document=AsyncMock(
            return_value=SimpleNamespace(
                id=extraction_id,
                structured_data={
                    field.key: {
                        "value": field.value,
                        "confidence": field.confidence,
                        "status": field.status,
                    }
                    for field in fields
                }
            )
        )
    )
    employees = SimpleNamespace(
        get_by_national_id_hash=AsyncMock(return_value=employee),
        get_by_number=AsyncMock(return_value=None),
        get_national_id_encrypted=AsyncMock(return_value=b"encrypted"),
    )
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=organization_id,
        employee_id=employee_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=5,
        rules_failed=0,
        overall_result=ValidationResult.PASS,
        findings=[],
    )
    validation = SimpleNamespace(execute=AsyncMock(return_value=run))
    phases: list[str] = []
    service = BatchPayslipPipelineService(
        extract=extract,
        documents=documents,
        extractions=extractions,
        employees=employees,
        validation=validation,
    )

    result = await service.process(
        content=b"%PDF-test",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=actor_id,
        progress=lambda stage, _details: phases.append(stage),
    )

    assert result.status == "passed"
    assert result.employee_number == "EMP-7"
    assert result.payroll_year == 2026
    assert result.payroll_month == 6
    assert document.employee_id == employee_id
    assert document.period and document.period.year == 2026
    assert document.metadata["publication_status"] == "draft"
    assert document.metadata["review_status"] == "pending_review"
    validation.execute.assert_awaited_once()
    assert phases == ["matching", "matching", "validation"]


@pytest.mark.asyncio
async def test_unknown_employee_is_persisted_without_stopping_pipeline() -> None:
    organization_id = uuid4()
    document_id = uuid4()
    fields = [
        _field("employee_id", "123456782"),
        _field("employee_number", "MISSING-7"),
        _field("pay_period", "06/2026"),
    ]
    extraction_id = uuid4()
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/unknown",
        original_filename="unknown.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    unknown_run = ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=organization_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=2,
        rules_failed=0,
        overall_result=ValidationResult.PASS,
        findings=[],
    )
    service = BatchPayslipPipelineService(
        extract=SimpleNamespace(
            execute=AsyncMock(
                return_value=GuestPayslipExtractionResult(
                    document_id=document_id,
                    extraction_id=extraction_id,
                    ocr_status="completed",
                    parser_status="completed",
                    language="he",
                    ocr_engine="test",
                    parser_model="test",
                    warnings=[],
                    fields=fields,
                    raw_text="payslip",
                )
            )
        ),
        documents=SimpleNamespace(
            get_by_id=AsyncMock(return_value=document),
            save=AsyncMock(side_effect=lambda value: value),
        ),
        extractions=SimpleNamespace(
            get_latest_for_document=AsyncMock(
                return_value=SimpleNamespace(
                    id=extraction_id,
                    structured_data={
                        field.key: {
                            "value": field.value,
                            "confidence": field.confidence,
                            "status": field.status,
                        }
                        for field in fields
                    },
                )
            )
        ),
        employees=SimpleNamespace(
            get_by_national_id_hash=AsyncMock(return_value=None),
            get_by_number=AsyncMock(return_value=None),
        ),
        validation=SimpleNamespace(execute=AsyncMock(return_value=unknown_run)),
    )

    result = await service.process(
        content=b"%PDF-test",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )

    assert result.status == "unknown_employee"
    assert result.document_id == document_id
    assert result.employee_number == "MISSING-7"
    assert result.payroll_year == 2026
    assert result.payroll_month == 6
    assert result.validation_run_id == unknown_run.id
    assert document.employee_id is None
    assert document.metadata["publication_status"] == "draft"
