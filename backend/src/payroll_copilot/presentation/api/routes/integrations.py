"""External integration routes (n8n, webhooks)."""

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from payroll_copilot.application.ports import AICapability
from payroll_copilot.infrastructure.ai.agents.base import AgentRegistry
from payroll_copilot.infrastructure.ai.provider_router import AIProviderRouter
from payroll_copilot.infrastructure.config.settings import get_settings

router = APIRouter()

CONFIDENCE_REVIEW_THRESHOLD = 0.85


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
    settings = get_settings()
    if x_api_key != settings.n8n_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    provider = AIProviderRouter(settings).provider_for(AICapability.GENERAL)
    registry = AgentRegistry(provider)
    agent = registry.get("vacation_sick_leave")

    result = await agent.run({
        "from_email": request.from_email,
        "subject": request.subject,
        "body_text": request.body_text,
    })

    confidence = result.confidence
    action = "recorded" if confidence >= CONFIDENCE_REVIEW_THRESHOLD else "pending_review"

    return ParsedLeaveResponse(
        parsed=result.data,
        confidence=confidence,
        action=action,
    )
