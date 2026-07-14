"""Accountant portal employee master-data API.

Employee records are business data — separate from authentication User accounts.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.employee_audit import EmployeeListFilter
from payroll_copilot.application.use_cases.employee_profile import BuildEmployeeProfileUseCase
from payroll_copilot.application.use_cases.manage_employees import (
    CreateEmployeeCommand,
    EmployeeConflictError,
    EmployeeNotFoundError,
    ManageEmployeesUseCase,
    UpdateEmployeeCommand,
)
from payroll_copilot.application.validation.demo_validation_context_builder import (
    DEMO_ORGANIZATION_ID,
)
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.database import get_db_session
from payroll_copilot.infrastructure.persistence.repositories.audit_log_repository import (
    SqlAlchemyAuditLogRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.employee_repository import (
    SqlAlchemyEmployeeRepository,
)
from payroll_copilot.infrastructure.persistence.repositories.workspace_bootstrap import (
    OrganizationWorkspaceBootstrap,
)
from payroll_copilot.presentation.api.security import BoundEmployeeContext, require_bound_employee

router = APIRouter()


class EmployeeCreateRequest(BaseModel):
    employee_number: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    salary_type: SalaryType = SalaryType.MONTHLY
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    hourly_rate: Decimal | None = None
    monthly_salary: Decimal | None = None
    email: str | None = None
    national_id: str | None = None
    department_id: UUID | None = None
    profile_incomplete: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmployeeUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    employment_type: EmploymentType | None = None
    salary_type: SalaryType | None = None
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    hourly_rate: Decimal | None = None
    monthly_salary: Decimal | None = None
    email: str | None = None
    national_id: str | None = None
    department_id: UUID | None = None
    status: EmployeeStatus | None = None
    profile_incomplete: bool | None = None
    metadata: dict[str, Any] | None = None


class NationalIdMatchRequest(BaseModel):
    national_id: str = Field(min_length=5, max_length=32)


def _use_case(session: AsyncSession) -> ManageEmployeesUseCase:
    settings = get_settings()
    return ManageEmployeesUseCase(
        SqlAlchemyEmployeeRepository(session),
        SqlAlchemyAuditLogRepository(session),
        encryption_key=settings.encryption_key,
    )


@router.get("")
async def list_employees(
    q: str | None = Query(default=None),
    status_filter: EmployeeStatus | None = Query(default=None, alias="status"),
    include_disabled: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    bootstrap = OrganizationWorkspaceBootstrap(session)
    await bootstrap.ensure_default_department(DEMO_ORGANIZATION_ID)
    await session.commit()
    return await _use_case(session).list_employees(
        EmployeeListFilter(
            organization_id=DEMO_ORGANIZATION_ID,
            query=q,
            status=status_filter,
            include_disabled=include_disabled,
            limit=limit,
            offset=offset,
        )
    )


@router.post("/match/national-id")
async def match_national_id(
    body: NationalIdMatchRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    matched = await _use_case(session).match_by_national_id(
        DEMO_ORGANIZATION_ID, body.national_id
    )
    return {"matched": matched is not None, "employee": matched}


@router.get("/me")
async def get_my_employee(
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> dict[str, Any]:
    """Trusted employee context for the authenticated employee principal."""
    employee = bound.employee
    return {
        "employee_id": str(employee.id),
        "employee_number": employee.employee_number,
        "full_name": (employee.metadata or {}).get("verified_display_name")
        or f"{employee.first_name} {employee.last_name}",
        "national_id_masked": (employee.metadata or {}).get("national_id_masked"),
        "organization_id": str(employee.organization_id),
        "status": employee.status.value
        if hasattr(employee.status, "value")
        else str(employee.status),
        "profile_incomplete": bool((employee.metadata or {}).get("profile_incomplete", False)),
    }


@router.get("/me/payslips")
async def list_my_payslips(
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    session: AsyncSession = Depends(get_db_session),
    year: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List payslip documents owned by the authenticated employee."""
    from payroll_copilot.domain.enums import DocumentType

    docs = await SqlAlchemyDocumentRepository(session).list_for_employee(
        organization_id=bound.employee.organization_id,
        employee_id=bound.employee.id,
    )
    rows: list[dict[str, Any]] = []
    for doc in docs:
        if doc.document_type != DocumentType.PAYSLIP:
            continue
        if year is not None and doc.period and doc.period.year != year:
            continue
        meta = dict(doc.metadata or {})
        rows.append(
            {
                "document_id": str(doc.id),
                "original_filename": doc.original_filename,
                "status": doc.status.value if hasattr(doc.status, "value") else str(doc.status),
                "period_year": doc.period.year if doc.period else meta.get("selected_period_year"),
                "period_month": doc.period.month if doc.period else meta.get("selected_period_month"),
                "extracted_period_year": meta.get("extracted_period_year"),
                "extracted_period_month": meta.get("extracted_period_month"),
                "uploaded_at": doc.created_at.isoformat() if doc.created_at else None,
                "manual_corrections": bool(meta.get("has_manual_corrections")),
            }
        )
    return rows


@router.get("/{employee_number}")
async def get_employee(
    employee_number: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        return await _use_case(session).get_by_number(DEMO_ORGANIZATION_ID, employee_number)
    except EmployeeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc


@router.get("/{employee_number}/profile")
async def get_employee_profile(
    employee_number: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    use_case = BuildEmployeeProfileUseCase(
        SqlAlchemyEmployeeRepository(session),
        SqlAlchemyAuditLogRepository(session),
        SqlAlchemyDocumentRepository(session),
    )
    try:
        return await use_case.execute(DEMO_ORGANIZATION_ID, employee_number)
    except EmployeeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    bootstrap = OrganizationWorkspaceBootstrap(session)
    department_id = body.department_id or await bootstrap.ensure_default_department(
        DEMO_ORGANIZATION_ID
    )
    try:
        created = await _use_case(session).create(
            CreateEmployeeCommand(
                organization_id=DEMO_ORGANIZATION_ID,
                employee_number=body.employee_number,
                first_name=body.first_name,
                last_name=body.last_name,
                department_id=department_id,
                employment_type=body.employment_type,
                salary_type=body.salary_type,
                contract_start_date=body.contract_start_date or date.today(),
                national_id=body.national_id,
                email=body.email,
                hourly_rate=body.hourly_rate,
                monthly_salary=body.monthly_salary,
                contract_end_date=body.contract_end_date,
                profile_incomplete=body.profile_incomplete,
                metadata=body.metadata,
            )
        )
        await session.commit()
        return created
    except EmployeeConflictError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc


@router.patch("/{employee_number}")
async def update_employee(
    employee_number: str,
    body: EmployeeUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        updated = await _use_case(session).update(
            UpdateEmployeeCommand(
                organization_id=DEMO_ORGANIZATION_ID,
                employee_number=employee_number,
                first_name=body.first_name,
                last_name=body.last_name,
                department_id=body.department_id,
                employment_type=body.employment_type,
                salary_type=body.salary_type,
                contract_start_date=body.contract_start_date,
                contract_end_date=body.contract_end_date,
                hourly_rate=body.hourly_rate,
                monthly_salary=body.monthly_salary,
                national_id=body.national_id,
                email=body.email,
                status=body.status,
                profile_incomplete=body.profile_incomplete,
                metadata=body.metadata,
            )
        )
        await session.commit()
        return updated
    except EmployeeNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
    except EmployeeConflictError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc


@router.post("/{employee_number}/disable")
async def disable_employee(
    employee_number: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    try:
        updated = await _use_case(session).disable(
            DEMO_ORGANIZATION_ID, employee_number, actor_user_id=None
        )
        await session.commit()
        return updated
    except EmployeeNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
