"""Unit tests for employee document storage key helper."""

from uuid import uuid4

from payroll_copilot.application.services.employee_document_lifecycle import (
    build_employee_storage_key,
    field_view_from_payload,
)
from payroll_copilot.domain.enums import DocumentType


def test_monthly_payslip_storage_key_shape() -> None:
    org = uuid4()
    emp = uuid4()
    doc = uuid4()
    key = build_employee_storage_key(
        organization_id=org,
        employee_id=emp,
        document_type=DocumentType.PAYSLIP,
        document_id=doc,
        filename="June.pdf",
        period_year=2026,
        period_month=6,
    )
    assert key == (
        f"organizations/{org}/employees/{emp}/payroll/2026/06/payslip/{doc}/June.pdf"
    )


def test_persistent_national_id_storage_key_shape() -> None:
    org = uuid4()
    emp = uuid4()
    doc = uuid4()
    key = build_employee_storage_key(
        organization_id=org,
        employee_id=emp,
        document_type=DocumentType.NATIONAL_ID,
        document_id=doc,
        filename="id.png",
    )
    assert key == (
        f"organizations/{org}/employees/{emp}/documents/national_id/{doc}/id.png"
    )


def test_corrected_value_becomes_effective() -> None:
    view = field_view_from_payload(
        "base_salary",
        {
            "value": "10000",
            "original_value": "9000",
            "edited_by_user": True,
            "status": "FOUND",
            "confidence": 0.8,
        },
    )
    assert view["extracted_value"] == "9000"
    assert view["corrected_value"] == "10000"
    assert view["effective_value"] == "10000"
    assert view["edited_by_employee"] is True
