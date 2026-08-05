"""Batch payslip employee matching and card identity fields."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.services.batch_payslip_pipeline import (
    MATCH_STATUS_CONFLICT,
    MATCH_STATUS_MATCHED,
    MATCH_STATUS_UNKNOWN,
    WARN_IDENTIFIERS_CONFLICT,
    WARN_NATIONAL_ID_OK_NUMBER_MISMATCH,
    WARN_NATIONAL_ID_UNAVAILABLE,
    WARN_NUMBER_OK_NATIONAL_ID_MISMATCH,
    WARN_NUMBER_UNAVAILABLE,
    BatchPayslipPipelineService,
)
from payroll_copilot.application.services.national_id_privacy import (
    hash_national_id,
    normalize_national_id_digits,
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


def _employee(
    organization_id,
    employee_id,
    *,
    number: str = "EMP-7",
    first: str = "Dana",
    last: str = "Levi",
) -> Employee:
    return Employee(
        id=employee_id,
        organization_id=organization_id,
        employee_number=number,
        first_name=first,
        last_name=last,
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("12000"),
        metadata={"national_id_masked": "****6782"},
    )


def _pass_run(document_id, organization_id, employee_id=None) -> ValidationRunRecord:
    return ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=organization_id,
        employee_id=employee_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=2,
        rules_failed=0,
        overall_result=ValidationResult.PASS,
        findings=[],
    )


def _service(
    *,
    fields: list[ExtractedFieldView],
    by_nid: Employee | None,
    by_number: Employee | None,
    document: Document,
    run: ValidationRunRecord,
) -> BatchPayslipPipelineService:
    extraction_id = uuid4()
    return BatchPayslipPipelineService(
        extract=SimpleNamespace(
            execute=AsyncMock(
                return_value=GuestPayslipExtractionResult(
                    document_id=document.id,
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
            find_payslip_for_period=AsyncMock(return_value=None),
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
            get_by_national_id_hash=AsyncMock(return_value=by_nid),
            get_by_number=AsyncMock(return_value=by_number),
        ),
        validation=SimpleNamespace(execute=AsyncMock(return_value=run)),
    )


def test_normalize_national_id_digits_strips_hyphen_and_keeps_leading_zeros() -> None:
    assert normalize_national_id_digits("31336678-3") == "313366783"
    assert normalize_national_id_digits(" 012345678 ") == "012345678"
    assert hash_national_id("31336678-3") == hash_national_id("313366783")


@pytest.mark.asyncio
async def test_unmatched_still_exposes_extracted_employee_name() -> None:
    organization_id = uuid4()
    document_id = uuid4()
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
    fields = [
        _field("employee_name", "יהודה שמולביץ"),
        _field("national_id", "31336678-3"),
        _field("employee_number", "MISSING"),
        _field("pay_period", "2026-06"),
    ]
    service = _service(
        fields=fields,
        by_nid=None,
        by_number=None,
        document=document,
        run=_pass_run(document_id, organization_id),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.status == "unknown_employee"
    assert result.match_status == MATCH_STATUS_UNKNOWN
    assert result.extracted_employee_name == "יהודה שמולביץ"
    assert result.employee_name is None
    assert result.identifier_match_warning is None


@pytest.mark.asyncio
async def test_both_identifiers_match_same_employee() -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    employee = _employee(organization_id, employee_id)
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/ok",
        original_filename="ok.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    fields = [
        _field("employee_name", "יהודה שמולביץ"),
        _field("national_id", "123456782"),
        _field("employee_number", "EMP-7"),
        _field("pay_period", "2026-06"),
    ]
    service = _service(
        fields=fields,
        by_nid=employee,
        by_number=employee,
        document=document,
        run=_pass_run(document_id, organization_id, employee_id),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.status == "passed"
    assert result.match_status == MATCH_STATUS_MATCHED
    assert result.identifier_match_warning is None
    assert result.extracted_employee_name == "יהודה שמולביץ"
    assert result.employee_name == "Dana Levi"
    assert document.employee_id == employee_id


@pytest.mark.asyncio
async def test_national_id_match_with_employee_number_mismatch_warns() -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    employee = _employee(organization_id, employee_id, number="EMP-7")
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/nid",
        original_filename="nid.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    fields = [
        _field("employee_name", "אורית סבירסקי"),
        _field("national_id", "30491361-9"),
        _field("employee_number", "OTHER-99"),
        _field("pay_period", "2026-06"),
    ]
    service = _service(
        fields=fields,
        by_nid=employee,
        by_number=None,
        document=document,
        run=_pass_run(document_id, organization_id, employee_id),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.match_status == MATCH_STATUS_MATCHED
    assert result.identifier_match_warning == WARN_NATIONAL_ID_OK_NUMBER_MISMATCH
    assert document.employee_id == employee_id


@pytest.mark.asyncio
async def test_employee_number_match_with_national_id_mismatch_warns() -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    employee = _employee(organization_id, employee_id)
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/num",
        original_filename="num.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    fields = [
        _field("employee_name", "ויטלין יעל"),
        _field("national_id", "999999999"),
        _field("employee_number", "EMP-7"),
        _field("pay_period", "2026-06"),
    ]
    service = _service(
        fields=fields,
        by_nid=None,
        by_number=employee,
        document=document,
        run=_pass_run(document_id, organization_id, employee_id),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.match_status == MATCH_STATUS_MATCHED
    assert result.identifier_match_warning == WARN_NUMBER_OK_NATIONAL_ID_MISMATCH
    assert document.employee_id == employee_id


@pytest.mark.asyncio
async def test_identifiers_matching_different_employees_is_conflict() -> None:
    organization_id = uuid4()
    document_id = uuid4()
    emp_a = _employee(organization_id, uuid4(), number="A-1", first="A")
    emp_b = _employee(organization_id, uuid4(), number="B-2", first="B")
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/conflict",
        original_filename="conflict.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    fields = [
        _field("employee_name", "שם מהתלוש"),
        _field("national_id", "111111118"),
        _field("employee_number", "B-2"),
        _field("pay_period", "2026-06"),
    ]
    service = _service(
        fields=fields,
        by_nid=emp_a,
        by_number=emp_b,
        document=document,
        run=_pass_run(document_id, organization_id),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.status == "unknown_employee"
    assert result.match_status == MATCH_STATUS_CONFLICT
    assert result.identifier_match_warning == WARN_IDENTIFIERS_CONFLICT
    assert result.extracted_employee_name == "שם מהתלוש"
    assert document.employee_id is None


@pytest.mark.asyncio
async def test_only_national_id_available_warns_number_unavailable() -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    employee = _employee(organization_id, employee_id)
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/nid-only",
        original_filename="nid-only.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    fields = [
        _field("employee_name", "תמר"),
        _field("national_id", "012345678"),
        _field("pay_period", "2026-06"),
    ]
    service = _service(
        fields=fields,
        by_nid=employee,
        by_number=None,
        document=document,
        run=_pass_run(document_id, organization_id, employee_id),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.match_status == MATCH_STATUS_MATCHED
    assert result.identifier_match_warning == WARN_NUMBER_UNAVAILABLE
    service._employees.get_by_number.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_employee_number_available_warns_national_id_unavailable() -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    employee = _employee(organization_id, employee_id)
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/num-only",
        original_filename="num-only.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    fields = [
        _field("employee_name", "רחל"),
        _field("employee_number", "EMP-7"),
        _field("pay_period", "2026-06"),
    ]
    service = _service(
        fields=fields,
        by_nid=None,
        by_number=employee,
        document=document,
        run=_pass_run(document_id, organization_id, employee_id),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.match_status == MATCH_STATUS_MATCHED
    assert result.identifier_match_warning == WARN_NATIONAL_ID_UNAVAILABLE
    service._employees.get_by_national_id_hash.assert_not_awaited()


@pytest.mark.asyncio
async def test_matching_does_not_use_employee_name() -> None:
    organization_id = uuid4()
    document_id = uuid4()
    # Same display name as an org employee would have, but identifiers miss.
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/name",
        original_filename="name.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    fields = [
        _field("employee_name", "Dana Levi"),
        _field("national_id", "000000000"),
        _field("employee_number", "NOPE"),
        _field("pay_period", "2026-06"),
    ]
    service = _service(
        fields=fields,
        by_nid=None,
        by_number=None,
        document=document,
        run=_pass_run(document_id, organization_id),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.status == "unknown_employee"
    assert result.extracted_employee_name == "Dana Levi"
    assert document.employee_id is None
