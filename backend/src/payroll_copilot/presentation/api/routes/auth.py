"""Authentication routes."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.domain.dev_employee_binding import (
    DEMO_ORGANIZATION_ID,
    DEV_EMPLOYEE_USER_EMAIL,
    DEV_EMPLOYEE_USER_ID,
)
from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.persistence.database import get_db_session
from payroll_copilot.presentation.api.security import ensure_dev_employee_user

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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


def _create_token(subject: str, expires_delta: timedelta, token_type: str = "access") -> str:
    settings = get_settings()
    payload = {
        "sub": subject,
        "type": token_type,
        "exp": datetime.now(UTC) + expires_delta,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest) -> TokenResponse:
    settings = get_settings()
    # Production: validate against database. Bootstrap accepts demo credentials.
    if request.email != "accountant@demo.co.il" or request.password != "demo":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_id = str(uuid4())
    access_token = _create_token(
        user_id, timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    refresh_token = _create_token(
        user_id, timedelta(days=settings.jwt_refresh_token_expire_days), "refresh"
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user={
            "id": user_id,
            "email": request.email,
            "role": "accountant",
            "preferred_locale": "he",
        },
    )


@router.post("/guest/session", response_model=GuestSessionResponse, status_code=201)
async def create_guest_session() -> GuestSessionResponse:
    settings = get_settings()
    guest_id = str(uuid4())
    token = _create_token(guest_id, timedelta(hours=settings.guest_session_ttl_hours), "guest")
    expires_at = datetime.now(UTC) + timedelta(hours=settings.guest_session_ttl_hours)
    return GuestSessionResponse(guest_token=token, expires_at=expires_at)


@router.post(
    "/dev/employee-session",
    response_model=DevEmployeeSessionResponse,
    status_code=201,
)
async def create_dev_employee_session(
    session: AsyncSession = Depends(get_db_session),
) -> DevEmployeeSessionResponse:
    """Development-only: issue a JWT for the stable employee↔user binding.

    Blocked when APP_ENV is production. Does not accept client employee_id.
    """
    settings = get_settings()
    if settings.app_env.lower() in {"production", "prod"}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_available", "message": "Dev employee session is not available."},
        )
    user = await ensure_dev_employee_user(session)
    await session.commit()
    access_token = _create_token(
        str(user.id),
        timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "access",
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
