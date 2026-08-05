"""Admin-only reset of company employee business data."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from payroll_copilot.application.use_cases.reset_company_employee_data import (
    CONFIRMATION_PHRASE,
    ResetCompanyEmployeeDataError,
    ResetCompanyEmployeeDataUseCase,
    ResetConfirmationError,
    ResetNotEnabledError,
    ResetOrganizationAmbiguousError,
)
from payroll_copilot.infrastructure.config.service_resolver import get_resolved_redis_url
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb import factory as dynamo_persistence
from payroll_copilot.infrastructure.persistence.dynamodb.client import get_dynamo_table
from payroll_copilot.infrastructure.storage import create_object_storage
from payroll_copilot.presentation.api.routes.legal_knowledge import require_developer_admin
from payroll_copilot.presentation.api.security import AuthPrincipal

logger = logging.getLogger(__name__)

router = APIRouter()


class ResetEmployeeDataRequest(BaseModel):
    confirmation_phrase: str = Field(min_length=1, max_length=64)
    confirm_destruction: bool = False


class ResetEmployeeDataResponse(BaseModel):
    organization_id: str
    confirmation_phrase_required: str = CONFIRMATION_PHRASE
    idempotent: bool
    counts: dict[str, Any]


def _optional_redis() -> Any | None:
    try:
        import redis

        client = redis.Redis.from_url(
            get_resolved_redis_url(get_settings()),
            decode_responses=True,
        )
        client.ping()
        return client
    except Exception:
        logger.warning("Redis unavailable for admin employee reset cleanup.", exc_info=True)
        return None


def get_reset_company_employee_data_use_case() -> ResetCompanyEmployeeDataUseCase:
    settings = get_settings()
    return ResetCompanyEmployeeDataUseCase(
        organizations=dynamo_persistence.get_organization_directory(),
        employees=dynamo_persistence.get_employee_repository(),
        users=dynamo_persistence.get_user_store(),
        documents=dynamo_persistence.get_document_repository(),
        extractions=dynamo_persistence.get_document_extraction_repository(),
        validation_runs=dynamo_persistence.get_validation_run_repository(),
        validation_findings=dynamo_persistence.get_validation_finding_repository(),
        vacations=dynamo_persistence.get_vacation_request_repository(),
        sick_leaves=dynamo_persistence.get_sick_leave_request_repository(),
        audit=dynamo_persistence.get_audit_log_repository(),
        storage=create_object_storage(settings),
        dynamo_table=get_dynamo_table(),
        redis=_optional_redis(),
        enabled=bool(settings.admin_employee_reset_enabled),
    )


@router.post(
    "/reset-employee-data",
    response_model=ResetEmployeeDataResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_company_employee_data(
    body: ResetEmployeeDataRequest,
    principal: AuthPrincipal = Depends(require_developer_admin),
) -> ResetEmployeeDataResponse:
    """Delete all employees and employee-related data for the sole company.

    Requires ``ADMIN_EMPLOYEE_RESET_ENABLED=true``, developer admin role,
    confirmation phrase ``RESET_EMPLOYEE_DATA``, and ``confirm_destruction=true``.
    """
    settings = get_settings()
    if not settings.admin_employee_reset_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "admin_employee_reset_disabled",
                "message": "Admin employee data reset is disabled.",
            },
        )

    use_case = get_reset_company_employee_data_use_case()
    try:
        result = await use_case.execute(
            actor_user_id=principal.user_id,
            confirmation_phrase=body.confirmation_phrase,
            confirm_destruction=body.confirm_destruction,
        )
    except ResetNotEnabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except ResetConfirmationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except ResetOrganizationAmbiguousError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except ResetCompanyEmployeeDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return ResetEmployeeDataResponse(
        organization_id=str(result.organization_id),
        idempotent=result.idempotent,
        counts=result.counts.to_dict(),
    )
