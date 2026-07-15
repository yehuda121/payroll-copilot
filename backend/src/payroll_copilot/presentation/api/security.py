"""JWT principal resolution for employee-bound routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.employee_audit import EmployeeRepository
from payroll_copilot.domain.dev_employee_binding import (
    DEMO_ORGANIZATION_ID,
    DEV_EMPLOYEE_USER_EMAIL,
    DEV_EMPLOYEE_USER_ID,
    get_dev_bound_employee_id,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus, UserRole
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.database import get_db_session
from payroll_copilot.infrastructure.persistence.models import UserModel
from payroll_copilot.infrastructure.persistence.repositories.employee_repository import (
    SqlAlchemyEmployeeRepository,
)


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    user_id: UUID
    role: str
    organization_id: UUID | None
    employee_id: UUID | None
    email: str | None = None


@dataclass(frozen=True, slots=True)
class BoundEmployeeContext:
    principal: AuthPrincipal
    employee: Employee
    national_id_encrypted: bytes | None


def _decode_bearer(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_authorization", "message": "Authorization Bearer token required."},
        )
    token = authorization.split(" ", 1)[1].strip()
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Invalid or expired access token."},
        ) from exc
    return payload


async def get_auth_principal(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_db_session),
) -> AuthPrincipal:
    payload = _decode_bearer(authorization)
    token_type = str(payload.get("type") or "access")
    if token_type == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "guest_not_allowed", "message": "Guest token cannot access employee routes."},
        )
    try:
        user_id = UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Token subject is invalid."},
        ) from exc

    result = await session.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "user_not_found", "message": "Authenticated user was not found."},
        )
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return AuthPrincipal(
        user_id=user.id,
        role=role,
        organization_id=user.organization_id,
        employee_id=user.employee_id,
        email=user.email,
    )


async def require_bound_employee(
    principal: AuthPrincipal = Depends(get_auth_principal),
    session: AsyncSession = Depends(get_db_session),
) -> BoundEmployeeContext:
    if principal.role != UserRole.EMPLOYEE.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "employee_role_required", "message": "Employee role required."},
        )
    if principal.employee_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "employee_binding_missing",
                "message": "Authenticated user is not bound to an employee record.",
            },
        )
    employees: EmployeeRepository = SqlAlchemyEmployeeRepository(session)
    employee = await employees.get_by_id(principal.employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "employee_not_found",
                "message": "Bound employee record was not found.",
            },
        )
    if employee.status == EmployeeStatus.DISABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "employee_disabled", "message": "Employee account is disabled."},
        )
    if (
        principal.organization_id is not None
        and employee.organization_id != principal.organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "organization_mismatch",
                "message": "User organization does not match employee organization.",
            },
        )
    encrypted = await employees.get_national_id_encrypted(employee.id)
    return BoundEmployeeContext(
        principal=principal,
        employee=employee,
        national_id_encrypted=encrypted,
    )


async def ensure_dev_employee_user(session: AsyncSession) -> UserModel:
    """Idempotently create the development employee auth user bound to seed employee #5."""
    settings = get_settings()
    if settings.app_env.lower() in {"production", "prod"}:
        raise RuntimeError("Dev employee user bootstrap is blocked in production.")

    employee_id = get_dev_bound_employee_id()
    result = await session.execute(select(UserModel).where(UserModel.id == DEV_EMPLOYEE_USER_ID))
    user = result.scalar_one_or_none()
    if user is None:
        user = UserModel(
            id=DEV_EMPLOYEE_USER_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            email=DEV_EMPLOYEE_USER_EMAIL,
            password_hash=None,
            role=UserRole.EMPLOYEE,
            preferred_locale="he",
            is_active=True,
            employee_id=employee_id,
        )
        session.add(user)
    else:
        user.organization_id = DEMO_ORGANIZATION_ID
        user.role = UserRole.EMPLOYEE
        user.employee_id = employee_id
        user.email = DEV_EMPLOYEE_USER_EMAIL
        user.is_active = True
    await session.flush()
    return user
