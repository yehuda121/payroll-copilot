"""Analytics API routes (Phase 1A backend foundation).

Public endpoints are documented in docs/analytics.md.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from payroll_copilot.application.services.analytics_service import AnalyticsService
from payroll_copilot.domain.enums import UserRole
from payroll_copilot.presentation.api.dependencies import get_analytics_service
from payroll_copilot.presentation.api.routes.analytics_schemas import (
    AdminOrgCensusResponse,
    AdminQualityAnalyticsResponse,
    EmployeeSalaryAnalyticsResponse,
    OrgPayrollAnalyticsResponse,
    OrgQualityAnalyticsResponse,
)
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    BoundEmployeeContext,
    get_auth_principal,
    require_accountant,
    require_bound_employee,
)

router = APIRouter()


async def require_developer_admin(
    principal: AuthPrincipal = Depends(get_auth_principal),  # noqa: B008
) -> AuthPrincipal:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "admin_role_required",
                "message": "Developer admin role required.",
            },
        )
    return principal


@router.get("/employee/salary", response_model=EmployeeSalaryAnalyticsResponse)
async def employee_salary_analytics(
    year: int | None = Query(default=None, ge=2000, le=2100),
    bound: BoundEmployeeContext = Depends(require_bound_employee),  # noqa: B008
    service: AnalyticsService = Depends(get_analytics_service),  # noqa: B008
) -> EmployeeSalaryAnalyticsResponse:
    result = await service.employee_salary(
        organization_id=bound.employee.organization_id,
        employee_id=bound.employee.id,
        year=year or datetime.utcnow().year,
        include_unpublished=False,
    )
    return EmployeeSalaryAnalyticsResponse.model_validate(result, from_attributes=True)


@router.get("/org/payroll", response_model=OrgPayrollAnalyticsResponse)
async def org_payroll_analytics(
    year: int | None = Query(default=None, ge=2000, le=2100),
    principal: AuthPrincipal = Depends(require_accountant),  # noqa: B008
    service: AnalyticsService = Depends(get_analytics_service),  # noqa: B008
) -> OrgPayrollAnalyticsResponse:
    assert principal.organization_id is not None
    result = await service.org_payroll(
        organization_id=principal.organization_id,
        year=year or datetime.utcnow().year,
    )
    return OrgPayrollAnalyticsResponse.model_validate(result, from_attributes=True)


@router.get("/org/quality", response_model=OrgQualityAnalyticsResponse)
async def org_quality_analytics(
    year: int | None = Query(default=None, ge=2000, le=2100),
    principal: AuthPrincipal = Depends(require_accountant),  # noqa: B008
    service: AnalyticsService = Depends(get_analytics_service),  # noqa: B008
) -> OrgQualityAnalyticsResponse:
    assert principal.organization_id is not None
    result = await service.org_quality(
        organization_id=principal.organization_id,
        year=year or datetime.utcnow().year,
    )
    return OrgQualityAnalyticsResponse.model_validate(result, from_attributes=True)


@router.get("/admin/census", response_model=AdminOrgCensusResponse)
async def admin_org_census(
    _: AuthPrincipal = Depends(require_developer_admin),  # noqa: B008
    service: AnalyticsService = Depends(get_analytics_service),  # noqa: B008
) -> AdminOrgCensusResponse:
    result = await service.admin_census()
    return AdminOrgCensusResponse.model_validate(result, from_attributes=True)


@router.get("/admin/quality", response_model=AdminQualityAnalyticsResponse)
async def admin_quality_analytics(
    year: int | None = Query(default=None, ge=2000, le=2100),
    _: AuthPrincipal = Depends(require_developer_admin),  # noqa: B008
    service: AnalyticsService = Depends(get_analytics_service),  # noqa: B008
) -> AdminQualityAnalyticsResponse:
    result = await service.admin_quality(year=year or datetime.utcnow().year)
    return AdminQualityAnalyticsResponse.model_validate(result, from_attributes=True)
