from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from payroll_copilot.application.dto.validation_run import ValidationRunRecord
from payroll_copilot.application.exceptions import ConfirmationBlockedError
from payroll_copilot.application.use_cases.publish_batch_payslip import (
    PublishBatchPayslipUseCase,
)
from payroll_copilot.domain.entities import Document, Employee
from payroll_copilot.domain.enums import (
    DocumentType,
    EmployeeStatus,
    EmploymentType,
    SalaryType,
    ValidationRunStatus,
)
from payroll_copilot.domain.value_objects import PayPeriod


def _employee(organization_id, employee_id) -> Employee:
    return Employee(
        id=employee_id,
        organization_id=organization_id,
        employee_number="EMP-42",
        first_name="Dana",
        last_name="Levi",
        department_id=uuid4(),
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2024, 1, 1),
        status=EmployeeStatus.ACTIVE,
        monthly_salary=Decimal("12000"),
    )


@pytest.mark.asyncio
async def test_publish_requires_current_confirmed_extraction_and_validation() -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    extraction_id = uuid4()
    employee = _employee(organization_id, employee_id)
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/draft",
        original_filename="payslip.pdf",
        mime_type="application/pdf",
        file_size_bytes=20,
        checksum_sha256="checksum",
        organization_id=organization_id,
        employee_id=employee_id,
        period=PayPeriod(year=2026, month=6),
        metadata={
            "publication_status": "draft",
            "review_status": "pending_review",
        },
    )
    extraction = SimpleNamespace(
        id=extraction_id,
        confirmation_status="confirmed",
    )
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=organization_id,
        employee_id=employee_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=5,
        rules_failed=0,
        extraction_id=extraction_id,
    )
    documents = SimpleNamespace(
        get_by_id=AsyncMock(return_value=document),
        list_for_employee=AsyncMock(return_value=[document]),
        save=AsyncMock(side_effect=lambda row: row),
    )
    service = PublishBatchPayslipUseCase(
        documents=documents,
        extractions=SimpleNamespace(
            get_latest_for_document=AsyncMock(return_value=extraction)
        ),
        validation_runs=SimpleNamespace(
            list_for_document=AsyncMock(return_value=[run])
        ),
    )

    result = await service.execute(
        document_id=document_id,
        employee=employee,
        actor_user_id=uuid4(),
    )

    assert result.validation_run_id == run.id
    assert document.metadata["publication_status"] == "published"
    assert document.metadata["review_status"] == "approved"
    assert document.metadata["provisional_employee_match"] is False


@pytest.mark.asyncio
async def test_publish_supersedes_previous_published_payslip_for_same_month() -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    previous_id = uuid4()
    extraction_id = uuid4()
    employee = _employee(organization_id, employee_id)
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/draft",
        original_filename="payslip-new.pdf",
        mime_type="application/pdf",
        file_size_bytes=20,
        checksum_sha256="checksum-new",
        organization_id=organization_id,
        employee_id=employee_id,
        period=PayPeriod(year=2026, month=6),
        metadata={
            "source": "accountant_bulk_upload",
            "publication_status": "draft",
            "review_status": "pending_review",
        },
    )
    previous = Document(
        id=previous_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/published",
        original_filename="payslip-old.pdf",
        mime_type="application/pdf",
        file_size_bytes=20,
        checksum_sha256="checksum-old",
        organization_id=organization_id,
        employee_id=employee_id,
        period=PayPeriod(year=2026, month=6),
        metadata={
            "source": "accountant_bulk_upload",
            "publication_status": "published",
            "lifecycle_status": "published",
            "review_status": "approved",
        },
    )
    run = ValidationRunRecord(
        id=uuid4(),
        document_id=document_id,
        organization_id=organization_id,
        employee_id=employee_id,
        status=ValidationRunStatus.COMPLETED,
        rules_evaluated=5,
        rules_failed=0,
        extraction_id=extraction_id,
    )
    documents = SimpleNamespace(
        get_by_id=AsyncMock(return_value=document),
        list_for_employee=AsyncMock(return_value=[previous, document]),
        save=AsyncMock(side_effect=lambda row: row),
    )
    service = PublishBatchPayslipUseCase(
        documents=documents,
        extractions=SimpleNamespace(
            get_latest_for_document=AsyncMock(
                return_value=SimpleNamespace(
                    id=extraction_id,
                    confirmation_status="confirmed",
                )
            )
        ),
        validation_runs=SimpleNamespace(
            list_for_document=AsyncMock(return_value=[run])
        ),
    )

    await service.execute(
        document_id=document_id,
        employee=employee,
        actor_user_id=uuid4(),
    )

    assert previous.metadata["lifecycle_status"] == "superseded"
    assert previous.metadata["publication_status"] == "draft"
    assert previous.metadata["superseded_by_document_id"] == str(document_id)
    assert document.metadata["publication_status"] == "published"


@pytest.mark.asyncio
async def test_publish_rejects_unconfirmed_current_digital_payslip() -> None:
    organization_id = uuid4()
    employee_id = uuid4()
    document_id = uuid4()
    employee = _employee(organization_id, employee_id)
    document = Document(
        id=document_id,
        document_type=DocumentType.PAYSLIP,
        storage_key="documents/draft",
        original_filename="payslip.pdf",
        mime_type="application/pdf",
        file_size_bytes=20,
        checksum_sha256="checksum",
        organization_id=organization_id,
        employee_id=employee_id,
        period=PayPeriod(year=2026, month=6),
        metadata={"publication_status": "draft"},
    )
    service = PublishBatchPayslipUseCase(
        documents=SimpleNamespace(
            get_by_id=AsyncMock(return_value=document),
            list_for_employee=AsyncMock(return_value=[document]),
        ),
        extractions=SimpleNamespace(
            get_latest_for_document=AsyncMock(
                return_value=SimpleNamespace(
                    id=uuid4(),
                    confirmation_status="review_required",
                )
            )
        ),
        validation_runs=SimpleNamespace(list_for_document=AsyncMock(return_value=[])),
    )

    with pytest.raises(ConfirmationBlockedError) as exc:
        await service.execute(
            document_id=document_id,
            employee=employee,
            actor_user_id=uuid4(),
        )

    assert exc.value.code == "current_extraction_not_confirmed"
