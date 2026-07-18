"""Public payroll assistant chat routes."""

from __future__ import annotations

from functools import lru_cache

from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field

from payroll_copilot.application.services.employee_ai_context_builder import (
    EmployeeAIContextBuilder,
    EmployeeAIContextResult,
)
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
from payroll_copilot.infrastructure.ai.guardrails.payroll_assistant_guardrails import (
    PayrollAssistantGuardrails,
)
from payroll_copilot.infrastructure.ai.ollama_provider import create_model_provider
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.infrastructure.i18n import resolve_locale
from payroll_copilot.infrastructure.persistence.dynamodb.factory import (
    get_document_extraction_repository,
    get_document_repository,
    get_validation_finding_repository,
    get_validation_run_repository,
)
from payroll_copilot.presentation.api.security import (
    BoundEmployeeContext,
    require_bound_employee,
)

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
    locale: str | None = Field(default=None, pattern="^(he|en|ar)$")


class AssistantChatResponse(BaseModel):
    answer: str
    session_id: str
    used_tools: list[str]
    sources: list[AssistantSourceResponse]
    confidence: float = Field(ge=0.0, le=1.0)
    requires_human_review: bool
    guardrail_status: str
    locale: str


class EmployeeAssistantChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    locale: str | None = Field(default=None, pattern="^(he|en|ar)$")
    # Availability hints only. The backend never accepts resource identifiers
    # or employee values from the browser as authoritative context.
    available_resource_keys: list[str] = Field(default_factory=list, max_length=200)


class EmployeeContextUpdatesResponse(BaseModel):
    profile: dict[str, Any] | None = None
    payroll_months: list[dict[str, Any]] = Field(default_factory=list)
    payroll_month_details: list[dict[str, Any]] = Field(default_factory=list)
    document_center: dict[str, Any] | None = None
    loaded_resource_keys: list[str] = Field(default_factory=list)


class EmployeeAssistantChatResponse(AssistantChatResponse):
    context_updates: EmployeeContextUpdatesResponse


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
async def assistant_chat(
    request: AssistantChatRequest,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> AssistantChatResponse:
    """Public guest payroll assistant chat orchestrated by LangGraph."""
    settings = get_settings()
    locale = resolve_locale(
        explicit=request.locale,
        accept_language=accept_language,
        default=settings.default_locale,
    )
    use_case = _get_assistant_use_case()
    result = await use_case.execute(
        AssistantChatCommand(
            message=request.message,
            session_id=request.session_id,
            document_ids=request.document_ids,
            validation_run_id=request.validation_run_id,
            locale=locale,
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
        locale=locale,
    )


@router.post("/employee/chat", response_model=EmployeeAssistantChatResponse)
async def employee_assistant_chat(
    request: EmployeeAssistantChatRequest,
    bound: BoundEmployeeContext = Depends(require_bound_employee),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> EmployeeAssistantChatResponse:
    """Authenticated assistant with canonical, employee-bound structured context.

    No employee/document identifiers are accepted from the client. All personal
    context is reconstructed from the authenticated binding before it reaches
    the assistant runner.
    """
    settings = get_settings()
    locale = resolve_locale(
        explicit=request.locale,
        accept_language=accept_language,
        default=settings.default_locale,
    )
    input_guardrail = PayrollAssistantGuardrails().evaluate_input(request.message)
    if input_guardrail.status.value in {"blocked", "blocked_safety"}:
        context_result = EmployeeAIContextResult()
    else:
        context_result = await EmployeeAIContextBuilder(
            documents=get_document_repository(),
            validation_runs=get_validation_run_repository(),
            validation_findings=get_validation_finding_repository(),
            extractions=get_document_extraction_repository(),
        ).build(
            message=request.message,
            employee=bound.employee,
            national_id_encrypted=bound.national_id_encrypted,
        )

    # available_resource_keys is intentionally not used for authorization or
    # data selection. It connects the frontend inventory while canonical data
    # remains backend-owned and bound to the authenticated employee.
    result = await _get_assistant_use_case().execute(
        AssistantChatCommand(
            message=request.message,
            session_id=request.session_id,
            locale=locale,
            prepared_employee_context=context_result.prepared_context or None,
        )
    )
    return EmployeeAssistantChatResponse(
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
        locale=locale,
        context_updates=EmployeeContextUpdatesResponse(
            profile=context_result.profile,
            payroll_months=context_result.payroll_months,
            payroll_month_details=context_result.payroll_month_details,
            document_center=context_result.document_center,
            loaded_resource_keys=context_result.loaded_resource_keys,
        ),
    )
