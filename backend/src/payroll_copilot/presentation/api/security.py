"""Authentication principal resolution (Amazon Cognito + guest tokens)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from payroll_copilot.application.ports.employee_audit import EmployeeRepository
from payroll_copilot.domain.dev_employee_binding import (
    DEMO_ORGANIZATION_ID,
    DEV_EMPLOYEE_DISPLAY_NAME_EN,
    DEV_EMPLOYEE_DISPLAY_NAME_HE,
    DEV_EMPLOYEE_NUMBER,
    DEV_EMPLOYEE_SEED_NATIONAL_ID,
    DEV_EMPLOYEE_USER_EMAIL,
    DEV_EMPLOYEE_USER_ID,
    get_dev_bound_employee_id,
)
from payroll_copilot.domain.entities import Employee
from payroll_copilot.domain.enums import EmployeeStatus, EmploymentType, SalaryType, UserRole
from payroll_copilot.infrastructure.auth.cognito import (
    CognitoConfigurationError,
    cognito_configured,
    employee_id_from_cognito_claims,
    get_cognito_token_verifier,
    organization_id_from_cognito_claims,
    role_from_cognito_claims,
)
from payroll_copilot.infrastructure.config.org_resolution import (
    allow_demo_organization_fallback,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_employee_repository,
    get_user_store,
    get_workspace_bootstrap,
)
from payroll_copilot.infrastructure.persistence.dynamodb.user_store import UserRecord
from payroll_copilot.infrastructure.security.field_crypto import (
    encrypt_national_id,
    hash_national_id,
    mask_national_id,
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


@dataclass(frozen=True, slots=True)
class GuestPrincipal:
    """Authenticated guest landing session (HS256 guest JWT)."""

    guest_id: str


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_authorization", "message": "Authorization Bearer token required."},
        )
    return authorization.split(" ", 1)[1].strip()


def _decode_guest_or_legacy_hs256(token: str) -> dict:
    """Decode guest (and rare local HS256) tokens signed with JWT_SECRET_KEY."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Invalid or expired access token."},
        ) from exc


def _decode_cognito_token(token: str) -> dict:
    try:
        verifier = get_cognito_token_verifier()
        return verifier.verify(token)
    except CognitoConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "cognito_not_configured", "message": str(exc)},
        ) from exc
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Invalid or expired Cognito token."},
        ) from exc


async def upsert_user_from_cognito_claims(
    claims: dict,
    *,
    default_role: str | None = None,
) -> UserRecord:
    """Create or update the local user mirror from Cognito claims (sub = user id)."""
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Token subject is invalid."},
        ) from exc

    raw_email = claims.get("email")
    email = str(raw_email).strip().lower() if raw_email else ""
    if not email:
        username = claims.get("username") or claims.get("cognito:username")
        candidate = str(username).strip().lower() if username else ""
        if candidate and "@" in candidate:
            email = candidate

    role_value = role_from_cognito_claims(claims) or default_role or UserRole.EMPLOYEE.value
    try:
        role = UserRole(role_value)
    except ValueError:
        role = UserRole.EMPLOYEE

    settings = get_settings()
    claim_org_id = organization_id_from_cognito_claims(claims)
    claim_employee_id = employee_id_from_cognito_claims(claims)
    demo_allowed = allow_demo_organization_fallback(settings)

    store = get_user_store()
    user = await store.get_by_id(user_id)
    if user is None:
        organization_id = claim_org_id
        if organization_id is None:
            if demo_allowed:
                organization_id = DEMO_ORGANIZATION_ID
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "organization_binding_missing",
                        "message": "Authenticated user is not bound to an organization.",
                    },
                )
        user = UserRecord(
            id=user_id,
            organization_id=organization_id,
            email=email or f"{user_id}@cognito.local",
            password_hash=None,
            role=role,
            preferred_locale="he",
            is_active=True,
            employee_id=claim_employee_id,
        )
    else:
        if email:
            user.email = email
        user.is_active = True
        user.password_hash = None
        if role_from_cognito_claims(claims):
            user.role = role
        if claim_org_id is not None:
            user.organization_id = claim_org_id
        elif user.organization_id is None:
            if demo_allowed:
                user.organization_id = DEMO_ORGANIZATION_ID
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "organization_binding_missing",
                        "message": "Authenticated user is not bound to an organization.",
                    },
                )
        if claim_employee_id is not None:
            user.employee_id = claim_employee_id

    if cognito_configured(settings) and not demo_allowed:
        if user.organization_id is None or user.organization_id == DEMO_ORGANIZATION_ID:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "organization_binding_missing",
                    "message": "Authenticated user is not bound to an organization.",
                },
            )

    return await store.save(user)


async def get_auth_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthPrincipal:
    token = _extract_bearer(authorization)
    settings = get_settings()

    try:
        unverified = jwt.get_unverified_claims(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "Malformed bearer token."},
        ) from exc

    token_type = str(unverified.get("type") or "")
    if token_type == "guest":
        payload = _decode_guest_or_legacy_hs256(token)
        if str(payload.get("type") or "") != "guest":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "invalid_token", "message": "Invalid guest token."},
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "guest_not_allowed", "message": "Guest token cannot access employee routes."},
        )

    store = get_user_store()
    if cognito_configured(settings):
        claims = _decode_cognito_token(token)
        user = await upsert_user_from_cognito_claims(claims)
    else:
        payload = _decode_guest_or_legacy_hs256(token)
        if str(payload.get("type") or "access") == "guest":
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
        user = await store.get_by_id(user_id)
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


async def require_guest(
    authorization: Annotated[str | None, Header()] = None,
) -> GuestPrincipal:
    """Require a valid guest landing JWT (not a Cognito / employee token)."""
    token = _extract_bearer(authorization)
    payload = _decode_guest_or_legacy_hs256(token)
    if str(payload.get("type") or "") != "guest":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "guest_token_required",
                "message": "A valid guest session token is required.",
            },
        )
    guest_id = str(payload.get("sub") or "").strip()
    if not guest_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_token",
                "message": "Guest token subject is invalid.",
            },
        )
    return GuestPrincipal(guest_id=guest_id)


async def require_accountant(
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> AuthPrincipal:
    """Require an authenticated payroll accountant with an organization scope."""
    if principal.role != UserRole.ACCOUNTANT.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "accountant_role_required",
                "message": "Payroll accountant role required.",
            },
        )
    if principal.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "organization_binding_missing",
                "message": "Authenticated accountant is not bound to an organization.",
            },
        )
    return principal


async def require_org_operator(
    principal: AuthPrincipal = Depends(get_auth_principal),
) -> AuthPrincipal:
    """Require an accountant or admin bound to an organization."""
    if principal.role not in {UserRole.ACCOUNTANT.value, UserRole.ADMIN.value}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "operator_role_required",
                "message": "Accountant or admin role required.",
            },
        )
    if principal.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "organization_binding_missing",
                "message": "Authenticated operator is not bound to an organization.",
            },
        )
    return principal


async def bind_accountant_selected_employee(
    *,
    employee_number: str,
    principal: AuthPrincipal,
) -> BoundEmployeeContext:
    """Resolve a selected employee strictly inside an accountant's organization."""
    if principal.role != UserRole.ACCOUNTANT.value or principal.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "accountant_scope_required",
                "message": "Accountant organization scope is required.",
            },
        )
    employees: EmployeeRepository = get_employee_repository()
    employee = await employees.get_by_number(
        principal.organization_id,
        employee_number,
    )
    if employee is None:
        # Return 404 for both missing and foreign employees to prevent tenant enumeration.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "employee_not_found", "message": "Employee not found."},
        )
    encrypted = await employees.get_national_id_encrypted(employee.id)
    return BoundEmployeeContext(
        principal=principal,
        employee=employee,
        national_id_encrypted=encrypted,
    )


async def require_bound_employee(
    principal: AuthPrincipal = Depends(get_auth_principal),
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
    employees: EmployeeRepository = get_employee_repository()
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


async def ensure_dev_employee_user() -> UserRecord:
    """Idempotently create the development employee auth user bound to seed employee #5.

    Also ensures the bound Employee record exists in DynamoDB so ``/employees/me``
    and related portal routes succeed locally. Only for local environments when
    Cognito is not configured.
    """
    settings = get_settings()
    if settings.app_env.lower() in {"production", "prod"}:
        raise RuntimeError("Dev employee user bootstrap is blocked in production.")
    if cognito_configured(settings):
        raise RuntimeError("Dev employee user bootstrap is blocked when Cognito is configured.")

    employee_id = get_dev_bound_employee_id()
    await _ensure_dev_bound_employee_record(employee_id)

    store = get_user_store()
    user = await store.get_by_id(DEV_EMPLOYEE_USER_ID)
    if user is None:
        user = UserRecord(
            id=DEV_EMPLOYEE_USER_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            email=DEV_EMPLOYEE_USER_EMAIL,
            password_hash=None,
            role=UserRole.EMPLOYEE,
            preferred_locale="he",
            is_active=True,
            employee_id=employee_id,
        )
    else:
        user.organization_id = DEMO_ORGANIZATION_ID
        user.role = UserRole.EMPLOYEE
        user.employee_id = employee_id
        user.email = DEV_EMPLOYEE_USER_EMAIL
        user.is_active = True
    return await store.save(user)


async def _ensure_dev_bound_employee_record(employee_id: UUID) -> Employee:
    """Create or refresh the seed employee #5 record used by the local employee portal."""
    employees = get_employee_repository()
    existing = await employees.get_by_id(employee_id)
    if existing is not None and existing.status != EmployeeStatus.DISABLED:
        return existing

    bootstrap = get_workspace_bootstrap()
    department_id = await bootstrap.ensure_default_department(DEMO_ORGANIZATION_ID)
    national_id = DEV_EMPLOYEE_SEED_NATIONAL_ID
    nid_hash = hash_national_id(national_id)
    metadata = {
        "dataset_id": "accountant_portal_seed_v1",
        "fixture_dataset_marker": "DEVELOPMENT_SEED",
        "verified_display_name": DEV_EMPLOYEE_DISPLAY_NAME_HE,
        "display_name_en": DEV_EMPLOYEE_DISPLAY_NAME_EN,
        "national_id_hash": nid_hash,
        "national_id_masked": mask_national_id(national_id),
        "profile_incomplete": True,
        "dev_bootstrap": True,
    }
    employee = Employee(
        id=employee_id,
        organization_id=DEMO_ORGANIZATION_ID,
        employee_number=DEV_EMPLOYEE_NUMBER,
        first_name="יהודה",
        last_name="שמולביץ",
        department_id=department_id,
        employment_type=EmploymentType.FULL_TIME,
        salary_type=SalaryType.MONTHLY,
        contract_start_date=date(2026, 1, 1),
        status=EmployeeStatus.ACTIVE,
        metadata=metadata,
    )
    encrypted = encrypt_national_id(national_id, encryption_key=get_settings().encryption_key)
    return await employees.save_with_national_id(employee, national_id_encrypted=encrypted)
