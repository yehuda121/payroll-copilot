"""Developer-only AI monitoring APIs (dashboard + comparison + history)."""

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
    tokens_by_capability: dict[str, int] = Field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    average_latency_ms: float = 0.0
    error_rate: float = 0.0
    retry_rate: float = 0.0
    fallback_rate: float = 0.0
    request_count: int = 0
    window_hours: int = 24
    prompt_versions: dict[str, int] = Field(default_factory=dict)
    source: str = "process_local"


class ModelComparisonItem(BaseModel):
    provider: str
    model: str
    capability: str = ""
    request_count: int
    average_latency_ms: float
    average_tokens: float
    estimated_cost_usd: float
    success_rate: float
    error_rate: float = 0.0
    retry_rate: float = 0.0
    fallback_rate: float = 0.0


class ModelComparisonResponse(BaseModel):
    items: list[ModelComparisonItem] = Field(default_factory=list)
    window_hours: int = 24


class HistoryPointSchema(BaseModel):
    timestamp: str
    value: float


class ProviderHistoryItem(BaseModel):
    provider: str
    tokens: float = 0.0
    estimated_cost_usd: float = 0.0
    average_latency_ms: float = 0.0
    success_count: float = 0.0
    error_count: float = 0.0
    retry_count: float = 0.0
    fallback_count: float = 0.0
    request_count: float = 0.0
    success_rate: float = 0.0


class AIHistoryResponse(BaseModel):
    source: str
    window_hours: int
    period_seconds: int
    tokens: list[HistoryPointSchema] = Field(default_factory=list)
    cost_usd: list[HistoryPointSchema] = Field(default_factory=list)
    latency_ms: list[HistoryPointSchema] = Field(default_factory=list)
    successes: list[HistoryPointSchema] = Field(default_factory=list)
    errors: list[HistoryPointSchema] = Field(default_factory=list)
    retries: list[HistoryPointSchema] = Field(default_factory=list)
    fallbacks: list[HistoryPointSchema] = Field(default_factory=list)
    by_provider: list[ProviderHistoryItem] = Field(default_factory=list)
    prompt_versions: dict[str, int] = Field(default_factory=dict)


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
        tokens_by_capability=summary.tokens_by_capability,
        estimated_cost_usd=summary.estimated_cost_usd,
        average_latency_ms=summary.average_latency_ms,
        error_rate=summary.error_rate,
        retry_rate=summary.retry_rate,
        fallback_rate=summary.fallback_rate,
        request_count=summary.request_count,
        window_hours=summary.window_hours,
        prompt_versions=summary.prompt_versions,
        source=summary.source,
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
                capability=row.capability,
                request_count=row.request_count,
                average_latency_ms=row.average_latency_ms,
                average_tokens=row.average_tokens,
                estimated_cost_usd=row.estimated_cost_usd,
                success_rate=row.success_rate,
                error_rate=row.error_rate,
                retry_rate=row.retry_rate,
                fallback_rate=row.fallback_rate,
            )
            for row in rows
        ],
    )


@router.get("/history", response_model=AIHistoryResponse)
async def ai_history(
    window_hours: int = Query(default=24, ge=1, le=168),
    _: AuthPrincipal = Depends(require_developer_admin),  # noqa: B008
) -> AIHistoryResponse:
    history = get_ai_metrics_recorder().history(window_hours=window_hours)
    return AIHistoryResponse(
        source=history.source,
        window_hours=history.window_hours,
        period_seconds=history.period_seconds,
        tokens=[HistoryPointSchema(timestamp=p.timestamp, value=p.value) for p in history.tokens],
        cost_usd=[
            HistoryPointSchema(timestamp=p.timestamp, value=p.value) for p in history.cost_usd
        ],
        latency_ms=[
            HistoryPointSchema(timestamp=p.timestamp, value=p.value) for p in history.latency_ms
        ],
        successes=[
            HistoryPointSchema(timestamp=p.timestamp, value=p.value) for p in history.successes
        ],
        errors=[HistoryPointSchema(timestamp=p.timestamp, value=p.value) for p in history.errors],
        retries=[
            HistoryPointSchema(timestamp=p.timestamp, value=p.value) for p in history.retries
        ],
        fallbacks=[
            HistoryPointSchema(timestamp=p.timestamp, value=p.value) for p in history.fallbacks
        ],
        by_provider=[
            ProviderHistoryItem(
                provider=row.provider,
                tokens=row.tokens,
                estimated_cost_usd=row.estimated_cost_usd,
                average_latency_ms=row.average_latency_ms,
                success_count=row.success_count,
                error_count=row.error_count,
                retry_count=row.retry_count,
                fallback_count=row.fallback_count,
                request_count=row.request_count,
                success_rate=row.success_rate,
            )
            for row in history.by_provider
        ],
        prompt_versions=history.prompt_versions,
    )
