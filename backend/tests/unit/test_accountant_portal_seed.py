"""Focused tests for accountant portal development seed dataset."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.use_cases.employee_profile import BuildEmployeeProfileUseCase
from payroll_copilot.application.use_cases.seed_accountant_portal import (
    DATASET_ID,
    SeedAccountantPortalUseCase,
    SeedProductionBlockedError,
    assert_seed_environment_allowed,
    load_dataset,
)
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DEMO_ORGANIZATION_ID,
)
from payroll_copilot.domain.document_types import ExpectedDocumentAvailability
from payroll_copilot.domain.enums import DocumentType
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.repositories.audit_log_repository import (
    SqlAlchemyAuditLogRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.employee_repository import (
    SqlAlchemyEmployeeRepository,
)
from payroll_copilot.infrastructure.security.field_crypto import hash_national_id

DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "data"
    / "accountant_portal_seed.json"
)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _use_case(session: AsyncSession, *, app_env: str = "development") -> SeedAccountantPortalUseCase:
    settings = get_settings()
    return SeedAccountantPortalUseCase(
        session=session,
        employees=SqlAlchemyEmployeeRepository(session),
        documents=SqlAlchemyDocumentRepository(session),
        audit_logs=SqlAlchemyAuditLogRepository(session),
        encryption_key=settings.encryption_key,
        app_env=app_env,
        repo_root=REPO_ROOT,
    )


@pytest.mark.asyncio
async def test_seed_creates_seven_employees_and_fourteen_payslips(db_session: AsyncSession) -> None:
    result = await _use_case(db_session).execute(DATASET_PATH)
    assert result.employees_total == 7
    assert result.payslips_total == 14

    employees = await SqlAlchemyEmployeeRepository(db_session).list_by_dataset_id(
        dataset_id=DATASET_ID
    )
    assert len(employees) == 7
    numbers = sorted(emp.employee_number for emp in employees)
    assert numbers == ["1", "2", "3", "4", "5", "6", "7"]


@pytest.mark.asyncio
async def test_seed_is_idempotent(db_session: AsyncSession) -> None:
    use_case = _use_case(db_session)
    first = await use_case.execute(DATASET_PATH)
    second = await use_case.execute(DATASET_PATH)
    assert first.employees_total == 7
    assert second.employees_total == 7
    assert first.payslips_total == 14
    assert second.payslips_total == 14

    employees = await SqlAlchemyEmployeeRepository(db_session).list_by_dataset_id(
        dataset_id=DATASET_ID
    )
    docs = await SqlAlchemyDocumentRepository(db_session).list_by_dataset_id(dataset_id=DATASET_ID)
    assert len(employees) == 7
    assert len([d for d in docs if d.document_type == DocumentType.PAYSLIP]) == 14


@pytest.mark.asyncio
async def test_every_employee_has_june_and_july_payslips(db_session: AsyncSession) -> None:
    await _use_case(db_session).execute(DATASET_PATH)
    employees = await SqlAlchemyEmployeeRepository(db_session).list_by_dataset_id(
        dataset_id=DATASET_ID
    )
    documents = SqlAlchemyDocumentRepository(db_session)
    for employee in employees:
        docs = await documents.list_for_employee(
            organization_id=DEMO_ORGANIZATION_ID,
            employee_id=employee.id,
        )
        payslips = [d for d in docs if d.document_type == DocumentType.PAYSLIP]
        periods = {(d.period.year, d.period.month) for d in payslips if d.period}
        assert (2026, 6) in periods
        assert (2026, 7) in periods
        assert len(payslips) == 2


@pytest.mark.asyncio
async def test_payslips_map_to_correct_employee_by_national_id(db_session: AsyncSession) -> None:
    dataset = load_dataset(DATASET_PATH)
    await _use_case(db_session).execute(DATASET_PATH)
    employees = SqlAlchemyEmployeeRepository(db_session)
    documents = await SqlAlchemyDocumentRepository(db_session).list_by_dataset_id(
        dataset_id=DATASET_ID
    )
    by_key = {doc.metadata.get("document_key"): doc for doc in documents}
    for slip in dataset["payslips"]:
        doc = by_key[slip["document_key"]]
        assert doc.employee_id is not None
        employee = await employees.get_by_id(doc.employee_id)
        assert employee is not None
        assert employee.metadata.get("national_id_hash") == hash_national_id(slip["national_id"])
        assert employee.employee_number == str(slip["employee_number"])
        assert doc.metadata.get("gross_salary") == slip["gross_salary"]
        assert doc.metadata.get("net_salary") == slip["net_salary"]


@pytest.mark.asyncio
async def test_source_pdf_page_metadata_preserved(db_session: AsyncSession) -> None:
    await _use_case(db_session).execute(DATASET_PATH)
    docs = await SqlAlchemyDocumentRepository(db_session).list_by_dataset_id(dataset_id=DATASET_ID)
    sample = next(d for d in docs if d.metadata.get("document_key") == "payslip_valid_2026_06_p01")
    assert sample.metadata["source_page"] == 1
    assert sample.metadata["fixture_path"].endswith(
        "payslips/valid/payslips_valid_2026_06_multi.pdf"
    )
    assert sample.metadata["fixture_classification"] == "valid"
    assert sample.period is not None
    assert sample.period.year == 2026 and sample.period.month == 6


@pytest.mark.asyncio
async def test_png_does_not_create_duplicate_payslip(db_session: AsyncSession) -> None:
    dataset = load_dataset(DATASET_PATH)
    png = next(s for s in dataset["source_documents"] if s["source_document_key"].endswith("png"))
    assert png.get("seed_as_payslip") is False
    await _use_case(db_session).execute(DATASET_PATH)
    docs = await SqlAlchemyDocumentRepository(db_session).list_by_dataset_id(dataset_id=DATASET_ID)
    assert len(docs) == 14
    assert not any(
        "employee_001.png" in str((d.metadata or {}).get("fixture_path") or "") for d in docs
    )


@pytest.mark.asyncio
async def test_missing_document_types_remain_missing(db_session: AsyncSession) -> None:
    await _use_case(db_session).execute(DATASET_PATH)
    employee = (
        await SqlAlchemyEmployeeRepository(db_session).list_by_dataset_id(dataset_id=DATASET_ID)
    )[0]
    profile = await BuildEmployeeProfileUseCase(
        SqlAlchemyEmployeeRepository(db_session),
        SqlAlchemyAuditLogRepository(db_session),
        SqlAlchemyDocumentRepository(db_session),
    ).execute(DEMO_ORGANIZATION_ID, employee.employee_number)

    by_type: dict[str, list[dict]] = {}
    for collection in profile["document_collections"]:
        for item in collection["items"]:
            by_type.setdefault(item["type_key"], []).append(item)

    assert any(
        item["availability"] == ExpectedDocumentAvailability.AVAILABLE.value
        for item in by_type["payslip"]
    )
    for missing_key in ("attendance", "contract", "national_id"):
        assert by_type[missing_key]
        assert all(
            item["availability"] == ExpectedDocumentAvailability.MISSING.value
            for item in by_type[missing_key]
        )


@pytest.mark.asyncio
async def test_cleanup_removes_only_seed_dataset(db_session: AsyncSession) -> None:
    settings = get_settings()
    employees = SqlAlchemyEmployeeRepository(db_session)
    # Unrelated employee outside the dataset
    from payroll_copilot.domain.entities import Employee
    from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
    from payroll_copilot.infrastructure.persistence.repositories.workspace_bootstrap import (
        OrganizationWorkspaceBootstrap,
    )
    from datetime import date

    dept_id = await OrganizationWorkspaceBootstrap(db_session).ensure_default_department(
        DEMO_ORGANIZATION_ID
    )
    outsider = Employee(
        id=uuid4(),
        organization_id=DEMO_ORGANIZATION_ID,
        employee_number="outsider-99",
        first_name="Out",
        last_name="Sider",
        department_id=dept_id,
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2020, 1, 1),
        status=EmployeeStatus.ACTIVE,
        metadata={"dataset_id": "other_dataset"},
    )
    await employees.save(outsider)

    use_case = _use_case(db_session)
    await use_case.execute(DATASET_PATH)
    cleanup = await use_case.cleanup()
    assert cleanup.employees_deleted == 7
    assert cleanup.payslips_deleted == 14

    assert await employees.get_by_number(DEMO_ORGANIZATION_ID, "outsider-99") is not None
    seed_employees = await employees.list_by_dataset_id(dataset_id=DATASET_ID)
    assert seed_employees == []
    seed_docs = await SqlAlchemyDocumentRepository(db_session).list_by_dataset_id(
        dataset_id=DATASET_ID
    )
    assert seed_docs == []


def test_production_execution_blocked() -> None:
    with pytest.raises(SeedProductionBlockedError):
        assert_seed_environment_allowed("production")
    with pytest.raises(SeedProductionBlockedError):
        assert_seed_environment_allowed("prod")
    assert_seed_environment_allowed("development")


@pytest.mark.asyncio
async def test_production_seed_execute_blocked(db_session: AsyncSession) -> None:
    with pytest.raises(SeedProductionBlockedError):
        await _use_case(db_session, app_env="production").execute(DATASET_PATH)
