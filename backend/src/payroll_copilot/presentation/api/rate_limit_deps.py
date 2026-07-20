"""FastAPI dependencies for production rate limiting."""

from __future__ import annotations

from fastapi import Depends, Request

from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.security.rate_limiter import get_rate_limiter
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    BoundEmployeeContext,
    GuestPrincipal,
    get_auth_principal,
    require_accountant,
    require_bound_employee,
    require_guest,
    require_org_operator,
)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def limit_auth_by_ip(request: Request) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "auth",
        client_ip(request),
        settings.rate_limit_auth_per_minute_per_ip,
        60,
    )


async def limit_guest_session_by_ip(request: Request) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "guest_session",
        client_ip(request),
        settings.rate_limit_guest_session_per_hour_per_ip,
        3600,
    )


async def limit_guest_extract_by_ip(request: Request) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "guest_extract",
        client_ip(request),
        settings.rate_limit_guest_extract_per_hour_per_ip,
        3600,
    )


async def limit_guest_extract_by_guest(
    request: Request,
    guest: GuestPrincipal = Depends(require_guest),
) -> None:
    del request
    settings = get_settings()
    get_rate_limiter().enforce(
        "guest_extract",
        guest.guest_id,
        settings.rate_limit_guest_extract_per_hour_per_ip,
        3600,
    )


async def limit_guest_upload_by_ip(request: Request) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "guest_upload",
        client_ip(request),
        settings.rate_limit_guest_uploads_per_hour,
        3600,
    )


async def limit_org_operator_upload(
    request: Request,
    principal: AuthPrincipal = Depends(require_org_operator),
) -> None:
    settings = get_settings()
    limit = (
        settings.rate_limit_accountant_uploads_per_hour
        if principal.role in {"accountant", "payroll_accountant", "admin", "developer_admin"}
        else settings.rate_limit_employee_uploads_per_hour
    )
    get_rate_limiter().enforce("upload:ip", client_ip(request), limit, 3600)
    get_rate_limiter().enforce("upload:user", str(principal.user_id), limit, 3600)


async def limit_employee_upload(
    request: Request,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
) -> None:
    settings = get_settings()
    limit = settings.rate_limit_employee_uploads_per_hour
    get_rate_limiter().enforce("upload:ip", client_ip(request), limit, 3600)
    get_rate_limiter().enforce("upload:user", str(bound.principal.user_id), limit, 3600)


async def limit_accountant_upload(
    request: Request,
    principal: AuthPrincipal = Depends(require_accountant),
) -> None:
    settings = get_settings()
    limit = settings.rate_limit_accountant_uploads_per_hour
    get_rate_limiter().enforce("upload:ip", client_ip(request), limit, 3600)
    get_rate_limiter().enforce("upload:user", str(principal.user_id), limit, 3600)


async def limit_ocr_by_ip(request: Request) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "ocr",
        client_ip(request),
        settings.rate_limit_ocr_per_hour_per_ip,
        3600,
    )


async def limit_ocr_by_user(principal: AuthPrincipal = Depends(get_auth_principal)) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "ocr:user",
        str(principal.user_id),
        settings.rate_limit_ocr_per_hour_per_user,
        3600,
    )


async def limit_parser_by_ip(request: Request) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "parser",
        client_ip(request),
        settings.rate_limit_parser_per_hour_per_ip,
        3600,
    )


async def limit_parser_by_user(principal: AuthPrincipal = Depends(get_auth_principal)) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "parser:user",
        str(principal.user_id),
        settings.rate_limit_parser_per_hour_per_user,
        3600,
    )


async def limit_validation_guest_by_ip(request: Request) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "validation",
        client_ip(request),
        settings.rate_limit_validation_per_hour_per_ip,
        3600,
    )


async def limit_validation_guest_by_guest(
    guest: GuestPrincipal = Depends(require_guest),
) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "validation:guest",
        guest.guest_id,
        settings.rate_limit_validation_per_hour_per_ip,
        3600,
    )


async def limit_validation_by_user(principal: AuthPrincipal = Depends(get_auth_principal)) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "validation:user",
        str(principal.user_id),
        settings.rate_limit_validation_per_hour_per_user,
        3600,
    )


async def limit_chat_by_ip(request: Request) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "chat",
        client_ip(request),
        settings.rate_limit_chat_per_hour_per_ip,
        3600,
    )


async def limit_chat_by_user(principal: AuthPrincipal = Depends(get_auth_principal)) -> None:
    settings = get_settings()
    get_rate_limiter().enforce(
        "chat:user",
        str(principal.user_id),
        settings.rate_limit_chat_per_hour_per_user,
        3600,
    )


async def limit_public_chat_by_ip(request: Request) -> None:
    """Guest/public assistant chat — IP only."""
    settings = get_settings()
    get_rate_limiter().enforce(
        "chat:public",
        client_ip(request),
        settings.rate_limit_chat_per_hour_per_ip,
        3600,
    )
