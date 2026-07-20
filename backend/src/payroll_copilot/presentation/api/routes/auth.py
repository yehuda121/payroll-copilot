"""Authentication routes — Amazon Cognito for users; short-lived guest tokens for landing."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from pydantic import BaseModel, EmailStr, Field

from payroll_copilot.domain.dev_employee_binding import (
    DEMO_ORGANIZATION_ID,
    DEV_EMPLOYEE_USER_EMAIL,
    DEV_EMPLOYEE_USER_ID,
)
from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.auth.cognito import (
    CognitoAuthenticationError,
    CognitoConfigurationError,
    api_role_from_domain,
    cognito_configured,
    get_cognito_auth_client,
    role_from_cognito_claims,
)
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.dynamodb.factory import get_user_store
from payroll_copilot.infrastructure.persistence.dynamodb.user_store import UserRecord
from payroll_copilot.presentation.api.rate_limit_deps import (
    limit_auth_by_ip,
    limit_guest_session_by_ip,
)
from payroll_copilot.presentation.api.security import (
    ensure_dev_employee_user,
    upsert_user_from_cognito_claims,
)

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)
    username: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class GuestSessionResponse(BaseModel):
    guest_token: str
    expires_at: datetime


class DevEmployeeSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


DEV_ACCOUNTANT_USER_ID = UUID("00000000-0000-4000-8000-000000000201")
DEV_ACCOUNTANT_EMAIL = "david.levy@dev.payroll-copilot.local"


def _create_guest_token(subject: str, expires_delta: timedelta) -> str:
    """Issue a short-lived guest JWT (not a Cognito user-pool token)."""
    settings = get_settings()
    payload = {
        "sub": subject,
        "type": "guest",
        "exp": datetime.now(UTC) + expires_delta,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _create_local_access_token(subject: str, expires_delta: timedelta) -> str:
    """HS256 access token used only when Cognito is not configured (local/dev)."""
    settings = get_settings()
    payload = {
        "sub": subject,
        "type": "access",
        "exp": datetime.now(UTC) + expires_delta,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _user_payload_from_model(user, *, claims: dict | None = None) -> dict:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    role = api_role_from_domain(role)
    email = user.email
    full_name = email.split("@")[0] if email else "user"
    if claims:
        full_name = (
            str(claims.get("name") or claims.get("given_name") or full_name).strip() or full_name
        )
    return {
        "id": str(user.id),
        "email": email,
        "role": role,
        "preferred_locale": getattr(user, "preferred_locale", None) or "he",
        "organization_id": str(user.organization_id) if user.organization_id else None,
        "employee_id": str(user.employee_id) if user.employee_id else None,
        "full_name": full_name,
    }


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    _: None = Depends(limit_auth_by_ip),
) -> TokenResponse:
    """Authenticate with Amazon Cognito and return API tokens (same contract as before)."""
    settings = get_settings()
    if not cognito_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "cognito_not_configured",
                "message": "Amazon Cognito is not configured for this environment.",
            },
        )

    try:
        client = get_cognito_auth_client()
        result = client.login(email=str(request.email), password=request.password)
    except CognitoConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "cognito_not_configured", "message": str(exc)},
        ) from exc
    except CognitoAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc

    role_hint = role_from_cognito_claims(result.claims)
    user = await upsert_user_from_cognito_claims(
        result.claims,
        default_role=role_hint,
    )

    refresh = result.refresh_token or ""
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=refresh,
        token_type=result.token_type.lower() if result.token_type else "bearer",
        expires_in=result.expires_in,
        user=_user_payload_from_model(user, claims=result.claims),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    request: RefreshRequest,
    _: None = Depends(limit_auth_by_ip),
) -> TokenResponse:
    """Refresh Cognito tokens. Keeps the same TokenResponse contract."""
    settings = get_settings()
    if not cognito_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "cognito_not_configured",
                "message": "Amazon Cognito is not configured for this environment.",
            },
        )
    try:
        client = get_cognito_auth_client()
        result = client.refresh(
            refresh_token=request.refresh_token,
            username=request.username,
        )
    except CognitoAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh_token", "message": str(exc)},
        ) from exc

    user = await upsert_user_from_cognito_claims(result.claims)
    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token or request.refresh_token,
        token_type="bearer",
        expires_in=result.expires_in,
        user=_user_payload_from_model(user, claims=result.claims),
    )


@router.post("/guest/session", response_model=GuestSessionResponse, status_code=201)
async def create_guest_session(
    _: None = Depends(limit_guest_session_by_ip),
) -> GuestSessionResponse:
    """Issue a short-lived guest token for the public landing flow (unchanged contract)."""
    settings = get_settings()
    guest_id = str(uuid4())
    token = _create_guest_token(guest_id, timedelta(hours=settings.guest_session_ttl_hours))
    expires_at = datetime.now(UTC) + timedelta(hours=settings.guest_session_ttl_hours)
    return GuestSessionResponse(guest_token=token, expires_at=expires_at)


@router.post(
    "/dev/employee-session",
    response_model=DevEmployeeSessionResponse,
    status_code=201,
)
async def create_dev_employee_session() -> DevEmployeeSessionResponse:
    """Local-only HS256 session when Cognito is not configured.

    Unavailable in production and whenever Cognito is enabled.
    """
    settings = get_settings()
    if settings.app_env.lower() in {"production", "prod"} or cognito_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_available", "message": "Dev employee session is not available."},
        )
    user = await ensure_dev_employee_user()
    access_token = _create_local_access_token(
        str(user.id),
        timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )
    return DevEmployeeSessionResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={
            "id": str(DEV_EMPLOYEE_USER_ID),
            "email": DEV_EMPLOYEE_USER_EMAIL,
            "role": UserRole.EMPLOYEE.value,
            "organization_id": str(DEMO_ORGANIZATION_ID),
            "employee_id": str(user.employee_id) if user.employee_id else None,
        },
    )


@router.post(
    "/dev/accountant-session",
    response_model=DevEmployeeSessionResponse,
    status_code=201,
)
async def create_dev_accountant_session() -> DevEmployeeSessionResponse:
    """Issue a local-only accountant token with an explicit organization binding."""
    settings = get_settings()
    if settings.app_env.lower() in {"production", "prod"} or cognito_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_available", "message": "Dev accountant session is not available."},
        )
    store = get_user_store()
    user = await store.get_by_id(DEV_ACCOUNTANT_USER_ID)
    if user is None:
        user = UserRecord(
            id=DEV_ACCOUNTANT_USER_ID,
            organization_id=DEMO_ORGANIZATION_ID,
            email=DEV_ACCOUNTANT_EMAIL,
            password_hash=None,
            role=UserRole.ACCOUNTANT,
            preferred_locale="he",
            is_active=True,
            employee_id=None,
        )
    else:
        user.organization_id = DEMO_ORGANIZATION_ID
        user.email = DEV_ACCOUNTANT_EMAIL
        user.role = UserRole.ACCOUNTANT
        user.is_active = True
        user.employee_id = None
    user = await store.save(user)
    access_token = _create_local_access_token(
        str(user.id),
        timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )
    return DevEmployeeSessionResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={
            "id": str(user.id),
            "email": user.email,
            "role": "payroll_accountant",
            "organization_id": str(user.organization_id),
            "employee_id": None,
        },
    )
