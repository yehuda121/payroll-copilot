"""Accountant portal employee master-data API.

Employee records are business data — separate from authentication User accounts.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_audit_log_repository,
    get_document_extraction_repository,
    get_document_repository,
    get_employee_repository,
    get_validation_finding_repository,
    get_validation_run_repository,
    get_workspace_bootstrap,
)

from payroll_copilot.application.ports.employee_audit import EmployeeListFilter
from payroll_copilot.application.use_cases.employee_profile import BuildEmployeeProfileUseCase
from payroll_copilot.application.use_cases.manage_employees import (
    CreateEmployeeCommand,
    EmployeeConflictError,
    EmployeeNotFoundError,
    ManageEmployeesUseCase,
    UpdateEmployeeCommand,
)
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    BoundEmployeeContext,
    bind_accountant_selected_employee,
    require_accountant,
    require_bound_employee,
)

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
    metadata: dict[str, Any] = Field(default_factory=dict)

class EmployeeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = None
    last_name: str | None = None
    employment_type: EmploymentType | None = None
    salary_type: SalaryType | None = None
    contract_start_date: date | None = None
    contract_end_date: date | None = None
    hourly_rate: Decimal | None = None
    monthly_salary: Decimal | None = None
    national_id: str | None = None
    department_id: UUID | None = None
    status: EmployeeStatus | None = None
    metadata: dict[str, Any] | None = None

class NationalIdMatchRequest(BaseModel):
    national_id: str = Field(min_length=5, max_length=32)

def _use_case() -> ManageEmployeesUseCase:
    settings = get_settings()
    return ManageEmployeesUseCase(
        get_employee_repository(),
        get_audit_log_repository(),
        encryption_key=settings.encryption_key,
    )


def _accountant_organization(principal: AuthPrincipal) -> UUID:
    # require_accountant guarantees this; keep the invariant explicit here.
    if principal.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return principal.organization_id


@router.get("")
async def list_employees(
    q: str | None = Query(default=None),
    status_filter: EmployeeStatus | None = Query(default=None, alias="status"),
    include_disabled: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: AuthPrincipal = Depends(require_accountant),
) -> list[dict[str, Any]]:
    organization_id = _accountant_organization(principal)
    bootstrap = get_workspace_bootstrap()
    await bootstrap.ensure_default_department(organization_id)
    return await _use_case().list_employees(
        EmployeeListFilter(
            organization_id=organization_id,
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
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    matched = await _use_case().match_by_national_id(
        _accountant_organization(principal), body.national_id
    )
    return {"matched": matched is not None, "employee": matched}

@router.get("/me")
async def get_my_employee(
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> dict[str, Any]:
    """Trusted employee context for the authenticated employee principal."""
    employee = bound.employee
    meta = employee.metadata or {}
    display_en = meta.get("display_name_en")
    display_localized = meta.get("verified_display_name") or f"{employee.first_name} {employee.last_name}"
    full_name = str(display_en) if display_en else str(display_localized)
    return {
        "employee_id": str(employee.id),
        "employee_number": employee.employee_number,
        "full_name": full_name,
        "full_name_localized": str(display_localized),
        "national_id_masked": meta.get("national_id_masked"),
        "organization_id": str(employee.organization_id),
        "status": employee.status.value
        if hasattr(employee.status, "value")
        else str(employee.status),
    }


@router.get("/me/documents")
async def list_my_documents(
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> dict[str, Any]:
    """Employee Document Center: persistent documents + monthly access pointer."""
    from payroll_copilot.application.use_cases.list_employee_documents import (
        ListEmployeeDocumentsUseCase,
    )
    
    use_case = ListEmployeeDocumentsUseCase(
        documents=get_document_repository(),
        extractions=get_document_extraction_repository(),
    )
    return await use_case.execute(
        organization_id=bound.employee.organization_id,
        employee_id=bound.employee.id,
    )

@router.get("/me/documents/national-id/review")
async def get_national_id_review(
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> dict[str, Any]:
    """National ID digital review foundation (parser not connected — no fabricated fields)."""
    from payroll_copilot.domain.enums import DocumentType

    docs = await get_document_repository().list_for_employee(
        organization_id=bound.employee.organization_id,
        employee_id=bound.employee.id,
    )
    identity = [
        d for d in docs if d.document_type == DocumentType.NATIONAL_ID
    ]
    identity.sort(key=lambda d: d.created_at or d.id, reverse=True)
    latest = identity[0] if identity else None
    return {
        "document_type": "national_id",
        "exists": latest is not None,
        "document_id": str(latest.id) if latest else None,
        "original_filename": latest.original_filename if latest else None,
        "uploaded_at": latest.created_at.isoformat() if latest and latest.created_at else None,
        "processing_status": (
            latest.status.value if latest and hasattr(latest.status, "value") else "missing"
        ),
        "extraction_status": "extraction_not_connected",
        "parser_status": "extraction_not_connected",
        "confirmation_status": "missing",
        "fields": [],
        "supported_fields": [],
        "national_id_masked": (bound.employee.metadata or {}).get("national_id_masked"),
        "note_code": "national_id_extraction_not_connected",
    }

@router.post(
    "/me/validation-runs/{validation_run_id}/findings/{finding_id}/explanation"
)
async def explain_my_finding(
    validation_run_id: UUID,
    finding_id: UUID,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    locale: str = Query(default="en"),
) -> dict[str, Any]:
    """On-demand AI/deterministic explanation for an owned validation finding."""
    from payroll_copilot.application.exceptions import DocumentNotOwnedError
    from payroll_copilot.application.use_cases.explain_employee_finding import (
        ExplainEmployeeFindingUseCase,
        FindingNotFoundError,
        ValidationRunNotFoundError,
    )
    
    runner = None
    try:
        from payroll_copilot.presentation.api.routes.assistant import _get_assistant_use_case
        from payroll_copilot.application.use_cases.payroll_assistant import AssistantChatCommand

        chat_uc = _get_assistant_use_case()

        class _AssistantAdapter:
            async def run(self, **kwargs):  # noqa: ANN003
                result = await chat_uc.execute(
                    AssistantChatCommand(
                        message=str(kwargs.get("message") or ""),
                        session_id=str(kwargs.get("session_id") or ""),
                        document_ids=list(kwargs.get("document_ids") or []),
                        validation_run_id=kwargs.get("validation_run_id"),
                        locale=str(kwargs.get("locale") or "en"),
                    )
                )
                return {
                    "answer": result.answer,
                    "sources": [
                        {
                            "title": s.get("title") if isinstance(s, dict) else getattr(s, "title", None),
                            "type": s.get("type") if isinstance(s, dict) else getattr(s, "type", None),
                            "id": s.get("reference") if isinstance(s, dict) else getattr(s, "reference", None),
                        }
                        for s in (result.sources or [])
                    ],
                }

        runner = _AssistantAdapter()
    except Exception:  # noqa: BLE001 — AI optional
        runner = None

    use_case = ExplainEmployeeFindingUseCase(
        documents=get_document_repository(),
        validation_runs=get_validation_run_repository(),
        validation_findings=get_validation_finding_repository(),
        audit_logs=get_audit_log_repository(),
        assistant_runner=runner,
    )
    try:
        result = await use_case.execute(
            employee=bound.employee,
            user_id=bound.principal.user_id,
            validation_run_id=validation_run_id,
            finding_id=finding_id,
            locale=locale,
        )
        return result
    except DocumentNotOwnedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "document_not_owned", "message": "Finding is not owned by this employee."},
        ) from exc
    except ValidationRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except FindingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

@router.get("/me/payroll-months")
async def list_my_payroll_months(
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    year: int | None = Query(default=None),
) -> dict[str, Any]:
    """Year overview of payslip/attendance/validation for the authenticated employee."""
    from datetime import datetime

    from payroll_copilot.application.use_cases.employee_payroll_months import (
        BuildEmployeePayrollMonthsUseCase,
    )
    
    selected_year = year or datetime.utcnow().year
    if selected_year < 2000 or selected_year > 2100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_year", "message": "Invalid year."},
        )
    use_case = BuildEmployeePayrollMonthsUseCase(
        documents=get_document_repository(),
        validation_runs=get_validation_run_repository(),
        validation_findings=get_validation_finding_repository(),
        extractions=get_document_extraction_repository(),
    )
    return await use_case.execute(
        organization_id=bound.employee.organization_id,
        employee_id=bound.employee.id,
        year=selected_year,
    )

@router.get("/me/payroll-months/{year}/{month}")
async def get_my_payroll_month_detail(
    year: int,
    month: int,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> dict[str, Any]:
    """Month detail for the authenticated employee only."""
    from payroll_copilot.application.use_cases.employee_payroll_months import (
        BuildEmployeePayrollMonthsUseCase,
    )
    
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_period", "message": "Invalid year or month."},
        )
    use_case = BuildEmployeePayrollMonthsUseCase(
        documents=get_document_repository(),
        validation_runs=get_validation_run_repository(),
        validation_findings=get_validation_finding_repository(),
        extractions=get_document_extraction_repository(),
    )
    return await use_case.month_detail(
        organization_id=bound.employee.organization_id,
        employee_id=bound.employee.id,
        year=year,
        month=month,
        employee=bound.employee,
        national_id_encrypted=bound.national_id_encrypted,
    )

@router.get("/me/payslips")
async def list_my_payslips(
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    year: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List payslip documents owned by the authenticated employee."""
    from payroll_copilot.application.services.employee_document_lifecycle import (
        is_employee_visible_document,
    )
    from payroll_copilot.domain.enums import DocumentType

    docs = await get_document_repository().list_for_employee(
        organization_id=bound.employee.organization_id,
        employee_id=bound.employee.id,
    )
    rows: list[dict[str, Any]] = []
    for doc in docs:
        if doc.document_type != DocumentType.PAYSLIP:
            continue
        if not is_employee_visible_document(doc):
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


@router.get("/{employee_number}/workspace/me")
async def get_accountant_workspace_employee(
    employee_number: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    selected = await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )
    employee = selected.employee
    meta = employee.metadata or {}
    localized = meta.get("verified_display_name") or (
        f"{employee.first_name} {employee.last_name}".strip()
    )
    return {
        "employee_id": str(employee.id),
        "employee_number": employee.employee_number,
        "full_name": str(meta.get("display_name_en") or localized),
        "full_name_localized": str(localized),
        "national_id_masked": meta.get("national_id_masked"),
        "organization_id": str(employee.organization_id),
        "status": employee.status.value
        if hasattr(employee.status, "value")
        else str(employee.status),
    }


@router.get("/{employee_number}/workspace/documents")
async def list_accountant_workspace_documents(
    employee_number: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    from payroll_copilot.application.use_cases.list_employee_documents import (
        ListEmployeeDocumentsUseCase,
    )

    selected = await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )
    return await ListEmployeeDocumentsUseCase(
        documents=get_document_repository(),
        extractions=get_document_extraction_repository(),
    ).execute(
        organization_id=selected.employee.organization_id,
        employee_id=selected.employee.id,
        include_unpublished=True,
    )


@router.post(
    "/{employee_number}/workspace/validation-runs/{validation_run_id}/findings/{finding_id}/explanation"
)
async def explain_accountant_workspace_finding(
    employee_number: str,
    validation_run_id: UUID,
    finding_id: UUID,
    locale: str = Query(default="en"),
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    selected = await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )
    return await explain_my_finding(
        validation_run_id=validation_run_id,
        finding_id=finding_id,
        bound=selected,
        locale=locale,
    )


@router.get("/{employee_number}/workspace/payroll-months")
async def list_accountant_workspace_payroll_months(
    employee_number: str,
    year: int | None = Query(default=None),
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    from payroll_copilot.application.use_cases.employee_payroll_months import (
        BuildEmployeePayrollMonthsUseCase,
    )

    selected = await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )
    selected_year = year or date.today().year
    if selected_year < 2000 or selected_year > 2100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_year", "message": "Invalid year."},
        )
    return await BuildEmployeePayrollMonthsUseCase(
        documents=get_document_repository(),
        validation_runs=get_validation_run_repository(),
        validation_findings=get_validation_finding_repository(),
        extractions=get_document_extraction_repository(),
    ).execute(
        organization_id=selected.employee.organization_id,
        employee_id=selected.employee.id,
        year=selected_year,
        include_unpublished=True,
    )


@router.get("/{employee_number}/workspace/payroll-months/{year}/{month}")
async def get_accountant_workspace_payroll_month_detail(
    employee_number: str,
    year: int,
    month: int,
    document_id: UUID | None = Query(default=None),
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    from payroll_copilot.application.use_cases.employee_payroll_months import (
        BuildEmployeePayrollMonthsUseCase,
    )

    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_period", "message": "Invalid year or month."},
        )
    selected = await bind_accountant_selected_employee(
        employee_number=employee_number,
        principal=principal,
    )
    return await BuildEmployeePayrollMonthsUseCase(
        documents=get_document_repository(),
        validation_runs=get_validation_run_repository(),
        validation_findings=get_validation_finding_repository(),
        extractions=get_document_extraction_repository(),
    ).month_detail(
        organization_id=selected.employee.organization_id,
        employee_id=selected.employee.id,
        year=year,
        month=month,
        employee=selected.employee,
        national_id_encrypted=selected.national_id_encrypted,
        include_unpublished=True,
        document_id=document_id,
    )


@router.get("/{employee_number}")
async def get_employee(
    employee_number: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        return await _use_case().get_by_number(
            _accountant_organization(principal), employee_number
        )
    except EmployeeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc

@router.get("/{employee_number}/profile")
async def get_employee_profile(
    employee_number: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    use_case = BuildEmployeeProfileUseCase(
        get_employee_repository(),
        get_audit_log_repository(),
        get_document_repository(),
    )
    try:
        return await use_case.execute(
            _accountant_organization(principal), employee_number
        )
    except EmployeeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreateRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    organization_id = _accountant_organization(principal)
    bootstrap = get_workspace_bootstrap()
    department_id = body.department_id or await bootstrap.ensure_default_department(
        organization_id
    )
    try:
        created = await _use_case().create(
            CreateEmployeeCommand(
                organization_id=organization_id,
                employee_number=body.employee_number,
                first_name=body.first_name,
                last_name=body.last_name,
                department_id=department_id,
                employment_type=body.employment_type,
                salary_type=body.salary_type,
                contract_start_date=body.contract_start_date or date.today(),
                actor_user_id=principal.user_id,
                national_id=body.national_id,
                email=body.email,
                hourly_rate=body.hourly_rate,
                monthly_salary=body.monthly_salary,
                contract_end_date=body.contract_end_date,
                metadata=body.metadata,
            )
        )
        return created
    except EmployeeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc

@router.patch("/{employee_number}")
async def update_employee(
    employee_number: str,
    body: EmployeeUpdateRequest,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        updated = await _use_case().update(
            UpdateEmployeeCommand(
                organization_id=_accountant_organization(principal),
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
                status=body.status,
                metadata=body.metadata,
            )
        )
        return updated
    except EmployeeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
    except EmployeeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc

@router.post("/{employee_number}/disable")
async def disable_employee(
    employee_number: str,
    principal: AuthPrincipal = Depends(require_accountant),
) -> dict[str, Any]:
    try:
        updated = await _use_case().disable(
            _accountant_organization(principal),
            employee_number,
            actor_user_id=principal.user_id,
        )
        return updated
    except EmployeeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
