"""Developer-only AI monitoring APIs (dashboard + model comparison)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.ai.ai_metrics import get_ai_metrics_recorder
from payroll_copilot.presentation.api.security import AuthPrincipal, get_auth_principal

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


class AIDashboardResponse(BaseModel):
    total_tokens: int = 0
    tokens_by_provider: dict[str, int] = Field(default_factory=dict)
    tokens_by_model: dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    average_latency_ms: float = 0.0
    error_rate: float = 0.0
    retry_rate: float = 0.0
    fallback_rate: float = 0.0
    request_count: int = 0
    window_hours: int = 24


class ModelComparisonItem(BaseModel):
    provider: str
    model: str
    request_count: int
    average_latency_ms: float
    average_tokens: float
    estimated_cost_usd: float
    success_rate: float


class ModelComparisonResponse(BaseModel):
    items: list[ModelComparisonItem] = Field(default_factory=list)
    window_hours: int = 24


@router.get("/dashboard", response_model=AIDashboardResponse)
async def ai_dashboard(
    window_hours: int = Query(default=24, ge=1, le=168),
    _: AuthPrincipal = Depends(require_developer_admin),  # noqa: B008
) -> AIDashboardResponse:
    summary = get_ai_metrics_recorder().summary(window_hours=window_hours)
    return AIDashboardResponse(
        total_tokens=summary.total_tokens,
        tokens_by_provider=summary.tokens_by_provider,
        tokens_by_model=summary.tokens_by_model,
        estimated_cost_usd=summary.estimated_cost_usd,
        average_latency_ms=summary.average_latency_ms,
        error_rate=summary.error_rate,
        retry_rate=summary.retry_rate,
        fallback_rate=summary.fallback_rate,
        request_count=summary.request_count,
        window_hours=summary.window_hours,
    )


@router.get("/models/comparison", response_model=ModelComparisonResponse)
async def ai_model_comparison(
    window_hours: int = Query(default=24, ge=1, le=168),
    _: AuthPrincipal = Depends(require_developer_admin),  # noqa: B008
) -> ModelComparisonResponse:
    rows = get_ai_metrics_recorder().model_comparison(window_hours=window_hours)
    return ModelComparisonResponse(
        window_hours=window_hours,
        items=[
            ModelComparisonItem(
                provider=row.provider,
                model=row.model,
                request_count=row.request_count,
                average_latency_ms=row.average_latency_ms,
                average_tokens=row.average_tokens,
                estimated_cost_usd=row.estimated_cost_usd,
                success_rate=row.success_rate,
            )
            for row in rows
        ],
    )
