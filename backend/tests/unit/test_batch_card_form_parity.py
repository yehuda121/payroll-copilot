"""Regression: batch card identity matches digital-form Document Model values."""

from __future__ import annotations

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
from payroll_copilot.application.services.national_id_privacy import (
    hash_national_id,
    normalize_national_id_digits,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import (
    ExtractedFieldView,
    GuestPayslipExtractionResult,
    _fields_from_structured,
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


def test_normalize_national_id_variants_are_equal() -> None:
    assert normalize_national_id_digits("31336678-3") == "313366783"
    assert normalize_national_id_digits("313 366 783") == "313366783"
    assert normalize_national_id_digits("313366783") == "313366783"
    assert normalize_national_id_digits("012345678") == "012345678"
    assert hash_national_id("31336678-3") == hash_national_id("313 366 78-3")


def test_fields_from_structured_same_name_and_period_as_form() -> None:
    structured = {
        "dynamic_entries": [
            {
                "id": "a",
                "key": "employee_name",
                "value": "יהודה שמולביץ",
                "kind": "document_field",
                "source": "extractor",
            },
            {
                "id": "b",
                "key": "pay_period",
                "value": "2026-06",
                "kind": "document_field",
                "source": "extractor",
            },
            {
                "id": "c",
                "key": "national_id",
                "value": "31336678-3",
                "kind": "document_field",
                "source": "extractor",
            },
        ],
        "additional_fields": {
            "national_id": {"value": "31336678-3", "status": "FOUND"},
        },
        "employee_name": {"value": "יהודה שמולביץ", "status": "FOUND"},
        "pay_period": {"value": "2026-06", "status": "FOUND"},
    }
    fields, _ = _fields_from_structured(structured)
    by_key = {f.key: f.value for f in fields}
    assert by_key["employee_name"] == "יהודה שמולביץ"
    assert by_key["pay_period"] == "2026-06"
    year, month = BatchPayslipPipelineService._pay_period(fields)
    assert (year, month) == (2026, 6)


@pytest.mark.asyncio
async def test_batch_pipeline_uses_form_name_and_period_not_missing_failure() -> None:
    organization_id = uuid4()
    document_id = uuid4()
    extraction_id = uuid4()
    # Simulate broken additional-only field list (historical bug) while
    # structured Document Model still has the digital-form values.
    guest_fields = [
        _field("national_id", "31336678-3"),
    ]
    structured = {
        "dynamic_entries": [
            {
                "id": "1",
                "key": "employee_name",
                "value": "יהודה שמולביץ",
                "kind": "document_field",
                "source": "extractor",
            },
            {
                "id": "2",
                "key": "pay_period",
                "value": "2026-06",
                "kind": "document_field",
                "source": "extractor",
            },
            {
                "id": "3",
                "key": "national_id",
                "value": "31336678-3",
                "kind": "document_field",
                "source": "extractor",
            },
        ],
        "additional_fields": {
            "national_id": {
                "value": "31336678-3",
                "status": "FOUND",
                "confidence": 0.9,
            }
        },
        "employee_name": {"value": "יהודה שמולביץ", "status": "FOUND"},
        "pay_period": {"value": "2026-06", "status": "FOUND"},
    }
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/x",
        original_filename="x.pdf",
        mime_type="application/pdf",
        file_size_bytes=10,
        checksum_sha256="checksum",
        organization_id=organization_id,
    )
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=organization_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=1,
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
                    fields=guest_fields,
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
                    structured_data=structured,
                )
            )
        ),
        employees=SimpleNamespace(
            get_by_national_id_hash=AsyncMock(return_value=None),
            get_by_number=AsyncMock(return_value=None),
        ),
        validation=SimpleNamespace(execute=AsyncMock(return_value=run)),
    )
    result = await service.process(
        content=b"%PDF",
        original_filename="slip.pdf",
        organization_id=organization_id,
        actor_user_id=uuid4(),
    )
    assert result.extracted_employee_name == "יהודה שמולביץ"
    assert result.payroll_year == 2026
    assert result.payroll_month == 6
    assert result.error_message != "The payroll period could not be extracted."
    assert result.status == "unknown_employee"
