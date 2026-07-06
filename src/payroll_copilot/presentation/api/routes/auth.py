"""Authentication routes."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel, EmailStr

from payroll_copilot.infrastructure.config.settings import get_settings

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
