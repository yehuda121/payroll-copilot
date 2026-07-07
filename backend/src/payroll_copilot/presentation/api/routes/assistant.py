"""Public payroll assistant chat routes."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter
from pydantic import BaseModel, Field

from payroll_copilot.application.use_cases.payroll_assistant import (
    AssistantChatCommand,
    PayrollAssistantChatUseCase,
)
from payroll_copilot.infrastructure.ai.agents.approved_labor_law_search import YamlApprovedLaborLawSearch
from payroll_copilot.infrastructure.ai.agents.payroll_assistant_graph import PayrollAssistantGraph
from payroll_copilot.infrastructure.ai.agents.payroll_assistant_tools import (
    InMemoryDocumentSummaryStore,
    PayrollAssistantTools,
)
from payroll_copilot.infrastructure.ai.agents.validation_report_store import InMemoryValidationReportStore
from payroll_copilot.infrastructure.ai.ollama_provider import create_model_provider
from payroll_copilot.infrastructure.config.settings import get_settings

router = APIRouter()

_document_summary_store = InMemoryDocumentSummaryStore()
_validation_report_store = InMemoryValidationReportStore()


class AssistantSourceResponse(BaseModel):
    title: str
    type: str
    reference: str | None = None


class AssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    validation_run_id: str | None = None
    locale: str = Field(default="en", pattern="^(he|en|ar)$")


class AssistantChatResponse(BaseModel):
    answer: str
    session_id: str
    used_tools: list[str]
    sources: list[AssistantSourceResponse]
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool
    guardrail_status: str


@lru_cache
def _get_assistant_use_case() -> PayrollAssistantChatUseCase:
    settings = get_settings()
    labor_law_search = YamlApprovedLaborLawSearch(settings.legal_rules_path)
    tools = PayrollAssistantTools(
        labor_law_search=labor_law_search,
        validation_reports=_validation_report_store,
        document_summaries=_document_summary_store,
    )
    model_provider = None
    try:
        model_provider = create_model_provider(settings.model_provider, settings)
    except Exception:
        model_provider = None

    graph = PayrollAssistantGraph(tools=tools, model_provider=model_provider)
    return PayrollAssistantChatUseCase(runner=graph)


@router.post("/chat", response_model=AssistantChatResponse)
async def assistant_chat(request: AssistantChatRequest) -> AssistantChatResponse:
    """Public guest payroll assistant chat orchestrated by LangGraph."""
    use_case = _get_assistant_use_case()
    result = await use_case.execute(
        AssistantChatCommand(
            message=request.message,
            session_id=request.session_id,
            document_ids=request.document_ids,
            validation_run_id=request.validation_run_id,
            locale=request.locale,
        )
    )
    return AssistantChatResponse(
        answer=result.answer,
        session_id=result.session_id,
        used_tools=result.used_tools,
        sources=[
            AssistantSourceResponse(
                title=source["title"],
                type=source["type"],
                reference=source.get("reference"),
            )
            for source in result.sources
        ],
        confidence=result.confidence,
        requires_human_review=result.requires_human_review,
        guardrail_status=result.guardrail_status,
    )
