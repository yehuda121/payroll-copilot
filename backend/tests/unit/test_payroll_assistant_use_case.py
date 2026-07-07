"""Unit tests for payroll assistant use case and tools."""

from __future__ import annotations

import httpx
import pytest

from payroll_copilot.application.ports import CompletionResult, Message
from payroll_copilot.application.ports.assistant import PayrollAssistantToolsPort
from payroll_copilot.application.use_cases.payroll_assistant import (
    AssistantChatCommand,
    PayrollAssistantChatUseCase,
)
from payroll_copilot.domain.assistant.types import (
    AssistantSource,
    AssistantSourceType,
    AssistantToolResult,
)
from payroll_copilot.infrastructure.ai.agents.approved_labor_law_search import YamlApprovedLaborLawSearch
from payroll_copilot.infrastructure.ai.agents.payroll_assistant_tools import PayrollAssistantTools
from payroll_copilot.infrastructure.ai.agents.validation_report_store import InMemoryValidationReportStore
from payroll_copilot.infrastructure.ai.agents.payroll_assistant_tools import InMemoryDocumentSummaryStore


class FakeAssistantRunner:
    async def run(
        self,
        *,
        message: str,
        session_id: str,
        document_ids: list[str],
        validation_run_id: str | None,
        locale: str,
    ) -> dict[str, object]:
        return {
            "answer": f"Echo: {message}",
            "session_id": session_id,
            "used_tools": ["search_approved_labor_law"],
            "sources": [{"title": "Minimum Wage", "type": "legal_rule", "reference": "labor_law.yaml"}],
            "confidence": 0.7,
            "requires_human_review": False,
            "guardrail_status": "passed",
        }


@pytest.mark.asyncio
async def test_assistant_use_case_returns_stable_response_structure() -> None:
    use_case = PayrollAssistantChatUseCase(runner=FakeAssistantRunner())
    result = await use_case.execute(AssistantChatCommand(message="Tell me about overtime rules"))
    assert result.answer.startswith("Echo:")
    assert result.session_id
    assert result.used_tools == ["search_approved_labor_law"]
    assert result.sources[0]["title"] == "Minimum Wage"
    assert result.guardrail_status == "passed"


def test_search_approved_labor_law_returns_empty_for_unknown_query() -> None:
    search = YamlApprovedLaborLawSearch("config/rules/labor_law")
    tools = PayrollAssistantTools(
        labor_law_search=search,
        validation_reports=InMemoryValidationReportStore(),
        document_summaries=InMemoryDocumentSummaryStore(),
    )
    result = tools.search_approved_labor_law("zzzznonexistenttopiczzzz")
    assert result.success is False
    assert result.sources == []


def test_search_approved_labor_law_returns_approved_local_content() -> None:
    search = YamlApprovedLaborLawSearch("config/rules/labor_law")
    tools = PayrollAssistantTools(
        labor_law_search=search,
        validation_reports=InMemoryValidationReportStore(),
        document_summaries=InMemoryDocumentSummaryStore(),
    )
    result = tools.search_approved_labor_law("minimum wage hourly")
    assert result.success is True
    assert result.sources
    assert result.sources[0].type.value == "legal_rule"


class _StubToolsWithContext(PayrollAssistantToolsPort):
    """Tools stub that always returns approved context so the model path is reached."""

    def search_approved_labor_law(self, query: str, *, locale: str = "en") -> AssistantToolResult:
        return AssistantToolResult(
            tool_name="search_approved_labor_law",
            success=True,
            content="- Minimum wage: approved local rule content.",
            sources=[
                AssistantSource(
                    title="Minimum Wage",
                    type=AssistantSourceType.LEGAL_RULE,
                    reference="labor_law.yaml",
                )
            ],
        )

    def get_validation_report(self, validation_run_id: str | None) -> AssistantToolResult:
        return AssistantToolResult(tool_name="get_validation_report", success=False, content="")

    def get_uploaded_document_summary(
        self, document_ids: list[str], *, session_id: str
    ) -> AssistantToolResult:
        return AssistantToolResult(
            tool_name="get_uploaded_document_summary", success=False, content=""
        )

    def explain_validation_finding(
        self, validation_run_id: str | None, finding_rule_id: str | None
    ) -> AssistantToolResult:
        return AssistantToolResult(
            tool_name="explain_validation_finding", success=False, content=""
        )

    def fallback_safe_response(self, reason: str) -> AssistantToolResult:
        return AssistantToolResult(tool_name="fallback_safe_response", success=True, content=reason)


class _UnavailableOllamaModel:
    """Model provider whose completion always fails as if Ollama is unreachable."""

    embedding_dimensions = 768

    async def complete(self, messages: list[Message], **_kwargs: object) -> CompletionResult:
        raise httpx.ConnectError("getaddrinfo failed")

    async def complete_structured(self, *_args: object, **_kwargs: object) -> object:
        raise httpx.ConnectError("getaddrinfo failed")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise httpx.ConnectError("getaddrinfo failed")


@pytest.mark.asyncio
async def test_assistant_does_not_crash_when_ollama_unavailable() -> None:
    pytest.importorskip("langgraph")
    from payroll_copilot.infrastructure.ai.agents.payroll_assistant_graph import (
        PayrollAssistantGraph,
    )

    graph = PayrollAssistantGraph(
        tools=_StubToolsWithContext(),
        model_provider=_UnavailableOllamaModel(),
    )
    use_case = PayrollAssistantChatUseCase(runner=graph)

    result = await use_case.execute(
        AssistantChatCommand(message="What is the minimum wage for payroll?")
    )

    assert result.guardrail_status != "blocked"
    assert result.answer
    assert "approved" in result.answer.lower()
