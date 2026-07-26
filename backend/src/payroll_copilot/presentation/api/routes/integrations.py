"""External integration routes (n8n). Org-bound API keys preferred."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from payroll_copilot.application.ports import AICapability
from payroll_copilot.application.use_cases.ingest_leave_batch import (
    InboundLeaveBatchItem,
    IngestLeaveBatchUseCase,
)
from payroll_copilot.application.use_cases.manage_sick_leaves import ManageSickLeavesUseCase
from payroll_copilot.application.use_cases.manage_vacations import (
    InboundVacationCommand,
    ManageVacationsUseCase,
)
from payroll_copilot.domain.enums import VacationPipelineEventType
from payroll_copilot.infrastructure.ai.agents.base import AgentRegistry
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.email.factory import create_email_service
from payroll_copilot.infrastructure.persistence import dynamodb as dynamo_persistence
from payroll_copilot.presentation.api.rate_limit_deps import enforce_integration_org_rate_limit

router = APIRouter()

CONFIDENCE_REVIEW_THRESHOLD = 0.85

ALLOWED_EVENT_METADATA_KEYS = frozenset(
    {"reason", "error_code", "classification", "guardrail", "latency_ms"}
)


@dataclass(frozen=True, slots=True)
class IntegrationPrincipal:
    organization_id: UUID
    credential_id: UUID | None = None
    auth_mode: str = "org_key"  # org_key | legacy_global


def _use_case() -> ManageVacationsUseCase:
    from payroll_copilot.infrastructure.storage.factory import create_object_storage

    settings = get_settings()
    return ManageVacationsUseCase(
        vacations=dynamo_persistence.get_vacation_request_repository(),
        settings_repo=dynamo_persistence.get_vacation_settings_repository(),
        otp_repo=dynamo_persistence.get_email_ownership_otp_repository(),
        pipeline=dynamo_persistence.get_vacation_pipeline_analytics_repository(),
        employees=dynamo_persistence.get_employee_repository(),
        audit=dynamo_persistence.get_audit_log_repository(),
        email=create_email_service(settings),
        object_storage=create_object_storage(settings),
        credentials=dynamo_persistence.get_integration_credential_repository(),
    )


def _sick_leave_use_case() -> ManageSickLeavesUseCase:
    from payroll_copilot.infrastructure.storage.factory import create_object_storage

    settings = get_settings()
    return ManageSickLeavesUseCase(
        sick_leaves=dynamo_persistence.get_sick_leave_request_repository(),
        settings_repo=dynamo_persistence.get_vacation_settings_repository(),
        employees=dynamo_persistence.get_employee_repository(),
        audit=dynamo_persistence.get_audit_log_repository(),
        object_storage=create_object_storage(settings),
    )


def _leave_batch_use_case() -> IngestLeaveBatchUseCase:
    return IngestLeaveBatchUseCase(
        vacations=_use_case(),
        sick_leaves=_sick_leave_use_case(),
        settings_repo=dynamo_persistence.get_vacation_settings_repository(),
    )


async def resolve_integration_principal(x_api_key: str) -> IntegrationPrincipal:
    """Resolve org from per-org key; fall back to legacy global key only if no org keys match."""
    provided = (x_api_key or "").strip()
    if not provided:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_api_key", "message": "Invalid API key"},
        )

    key_hash = hashlib.sha256(provided.encode("utf-8")).hexdigest()
    cred = await dynamo_persistence.get_integration_credential_repository().get_by_key_hash(
        key_hash
    )
    if cred is not None and cred.revoked_at is None:
        return IntegrationPrincipal(
            organization_id=cred.organization_id,
            credential_id=cred.id,
            auth_mode="org_key",
        )

    settings = get_settings()
    configured = (settings.n8n_api_key or "").strip()
    if configured and len(provided) == len(configured) and hmac.compare_digest(provided, configured):
        # Legacy global key: organization must still be supplied by a dedicated header
        # and is only accepted for backwards compatibility when explicitly enabled.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "org_api_key_required",
                "message": (
                    "Use an organization-bound integration API key "
                    "(create via accountant Vacations settings)."
                ),
            },
        )

    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "n8n_not_configured",
                "message": "N8N integration is not configured.",
            },
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_api_key", "message": "Invalid API key"},
    )


def _rate_limit_integration(principal: IntegrationPrincipal) -> None:
    enforce_integration_org_rate_limit(str(principal.organization_id))


# Keep legacy parse-leave for compatibility but document it does not persist.
class EmailParseLeaveRequest(BaseModel):
    organization_id: str
    from_email: str
    subject: str
    body_text: str
    received_at: str


class ParsedLeaveResponse(BaseModel):
    parsed: dict
    confidence: float
    action: str


@router.post("/email/parse-leave", response_model=ParsedLeaveResponse)
async def parse_leave_email(
    request: EmailParseLeaveRequest,
    x_api_key: str = Header(...),
) -> ParsedLeaveResponse:
    """Legacy extract-only endpoint. Does NOT persist VacationRequest.

    Prefer POST /integrations/email/inbound-vacation with n8n-owned extraction.
    """
    principal = await resolve_integration_principal(x_api_key)
    _rate_limit_integration(principal)
    settings = get_settings()
    provider = AIProviderRouter(settings).provider_for(AICapability.GENERAL)
    registry = AgentRegistry(provider)
    agent = registry.get("vacation_sick_leave")
    result = await agent.run(
        {
            "from_email": request.from_email,
            "subject": request.subject,
            "body_text": request.body_text,
        }
    )
    confidence = result.confidence
    action = "recorded" if confidence >= CONFIDENCE_REVIEW_THRESHOLD else "pending_review"
    return ParsedLeaveResponse(parsed=result.data, confidence=confidence, action=action)


class LeaveExtractionPayload(BaseModel):
    """n8n extraction object for vacation / sick-leave inbound items.

    All fields optional to match the live contract; malformed types fail at the
    HTTP boundary instead of deep in ingest.
    """

    model_config = ConfigDict(extra="ignore")

    employee_email: str | None = Field(default=None, max_length=320)
    employee_name: str | None = Field(default=None, max_length=500)
    start_date: str | None = Field(default=None, max_length=64)
    end_date: str | None = Field(default=None, max_length=64)
    confidence: float | None = None
    explanation: str | None = Field(default=None, max_length=5000)


class InboundVacationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="gmail", max_length=32)
    provider_message_id: str = Field(min_length=1, max_length=512)
    provider_thread_id: str | None = Field(default=None, max_length=512)
    from_email: str | None = Field(default=None, max_length=320)
    to_email: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=500)
    body_text: str | None = Field(default=None, max_length=200_000)
    received_at: datetime | None = None
    classification: str = Field(default="VACATION", max_length=32)
    intent: str = Field(default="new", max_length=32)
    extraction: LeaveExtractionPayload = Field(default_factory=LeaveExtractionPayload)
    n8n_attention_codes: list[str] = Field(default_factory=list, max_length=20)
    target_hints: dict[str, Any] | None = None


@router.get("/vacation/mailbox-config")
async def mailbox_config(x_api_key: str = Header(...)) -> dict[str, Any]:
    principal = await resolve_integration_principal(x_api_key)
    _rate_limit_integration(principal)
    uc = _use_case()
    settings = await uc.get_settings(principal.organization_id)
    return {"organizations": [await uc.mailbox_config_for_n8n(settings)]}


@router.post("/email/inbound-vacation")
async def inbound_vacation(
    body: InboundVacationRequest,
    x_api_key: str = Header(...),
) -> dict[str, Any]:
    principal = await resolve_integration_principal(x_api_key)
    _rate_limit_integration(principal)
    extraction = body.extraction
    command = InboundVacationCommand(
        provider=body.provider,
        provider_message_id=body.provider_message_id,
        provider_thread_id=body.provider_thread_id,
        from_email=body.from_email,
        to_email=body.to_email,
        subject=body.subject,
        body_text=body.body_text,
        received_at=body.received_at,
        classification=body.classification,
        intent=body.intent,
        employee_email=extraction.employee_email,
        employee_name=extraction.employee_name,
        start_date=extraction.start_date,
        end_date=extraction.end_date,
        confidence=extraction.confidence,
        explanation=extraction.explanation,
        n8n_attention_codes=list(body.n8n_attention_codes or []),
        target_hints=body.target_hints,
    )
    return await _use_case().ingest_inbound(principal.organization_id, command)


class InboundLeaveBatchItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="imap", max_length=32)
    provider_message_id: str = Field(min_length=1, max_length=512)
    provider_thread_id: str | None = Field(default=None, max_length=512)
    from_email: str | None = Field(default=None, max_length=320)
    to_email: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=500)
    body_text: str | None = Field(default=None, max_length=200_000)
    received_at: datetime | None = None
    classification: str = Field(min_length=3, max_length=32)
    intent: str = Field(default="new", max_length=32)
    extraction: LeaveExtractionPayload = Field(default_factory=LeaveExtractionPayload)
    n8n_attention_codes: list[str] = Field(default_factory=list, max_length=20)
    target_hints: dict[str, Any] | None = None


class InboundLeaveBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[InboundLeaveBatchItemRequest] = Field(min_length=1, max_length=100)


@router.post("/email/inbound-leave/batch")
async def inbound_leave_batch(
    body: InboundLeaveBatchRequest,
    x_api_key: str = Header(...),
) -> dict[str, Any]:
    """Process a mixed VACATION + SICK_LEAVE batch. Org comes from API key only."""
    principal = await resolve_integration_principal(x_api_key)
    _rate_limit_integration(principal)
    items: list[InboundLeaveBatchItem] = []
    for item in body.items:
        extraction = item.extraction
        items.append(
            InboundLeaveBatchItem(
                provider=item.provider,
                provider_message_id=item.provider_message_id,
                provider_thread_id=item.provider_thread_id,
                from_email=item.from_email,
                to_email=item.to_email,
                subject=item.subject,
                body_text=item.body_text,
                received_at=item.received_at,
                classification=item.classification,
                intent=item.intent,
                employee_email=extraction.employee_email,
                employee_name=extraction.employee_name,
                start_date=extraction.start_date,
                end_date=extraction.end_date,
                confidence=extraction.confidence,
                explanation=extraction.explanation,
                n8n_attention_codes=list(item.n8n_attention_codes or []),
                target_hints=item.target_hints,
            )
        )
    return await _leave_batch_use_case().execute(principal.organization_id, items)


class PipelineEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=8, max_length=128)
    event_type: str = Field(min_length=3, max_length=64)
    occurred_at: datetime | None = None
    provider: str | None = Field(default=None, max_length=32)
    provider_message_id: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] | None = None


@router.post("/email/events")
async def pipeline_events(
    body: PipelineEventRequest,
    x_api_key: str = Header(...),
) -> dict[str, Any]:
    principal = await resolve_integration_principal(x_api_key)
    _rate_limit_integration(principal)
    try:
        VacationPipelineEventType(body.event_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_event_type"},
        ) from exc
    meta = body.metadata or {}
    if any(key not in ALLOWED_EVENT_METADATA_KEYS for key in meta):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_metadata_keys"},
        )
    bounded = {k: str(v)[:200] for k, v in meta.items() if k in ALLOWED_EVENT_METADATA_KEYS}
    try:
        return await _use_case().record_pipeline_event(
            principal.organization_id,
            event_id=body.event_id,
            event_type=body.event_type,
            occurred_at=body.occurred_at,
            provider=body.provider,
            provider_message_id=body.provider_message_id,
            metadata=bounded,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


class MailboxHealthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monitored_email: str = Field(min_length=3, max_length=320)
    status: str = Field(pattern="^(ok|error)$")
    checked_at: datetime | None = None
    last_processed_at: datetime | None = None
    last_processed_message_id: str | None = Field(default=None, max_length=512)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=500)


@router.post("/mailbox/health")
async def mailbox_health(
    body: MailboxHealthRequest,
    x_api_key: str = Header(...),
) -> dict[str, Any]:
    principal = await resolve_integration_principal(x_api_key)
    _rate_limit_integration(principal)
    uc = _use_case()
    settings = await uc.apply_mailbox_health(
        principal.organization_id,
        monitored_email=body.monitored_email,
        status=body.status,
        checked_at=body.checked_at,
        last_processed_at=body.last_processed_at,
        last_processed_message_id=body.last_processed_message_id,
        error_code=body.error_code,
        error_message=body.error_message,
    )
    status_value = await uc.email_automation_status(principal.organization_id)
    return {
        "organization_id": str(principal.organization_id),
        "active_monitored_email": settings.active_monitored_email,
        "mailbox_connection_status": settings.mailbox_connection_status,
        "email_automation_status": status_value,
    }
