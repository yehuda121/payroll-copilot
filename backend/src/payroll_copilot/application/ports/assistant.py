"""Port interfaces for the payroll assistant."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from payroll_copilot.domain.assistant.types import AssistantSource, AssistantToolResult


@dataclass(frozen=True, slots=True)
class LaborLawSearchHit:
    rule_key: str
    title: str
    summary: str
    legal_reference: str | None
    source_file: str


@runtime_checkable
class ApprovedLaborLawSearchPort(Protocol):
    """Searches approved local legal rule content only — never external websites."""

    def search(self, query: str, *, locale: str = "en", limit: int = 5) -> list[LaborLawSearchHit]: ...


@runtime_checkable
class ValidationReportPort(Protocol):
    """Reads deterministic validation reports produced by the backend rule engine."""

    def get_report(
        self,
        validation_run_id: str,
        *,
        owner_guest_id: str | None = None,
    ) -> dict[str, object] | None: ...


@runtime_checkable
class DocumentSummaryPort(Protocol):
    """Returns safe metadata summaries for guest-scoped document IDs."""

    def get_summaries(
        self,
        document_ids: list[str],
        *,
        session_id: str,
    ) -> list[dict[str, str]]: ...


class PayrollAssistantToolsPort(ABC):
    """Tool adapter boundary for the LangGraph orchestrator."""

    @abstractmethod
    def search_approved_labor_law(
        self,
        query: str,
        *,
        locale: str = "en",
    ) -> AssistantToolResult: ...

    @abstractmethod
    def get_validation_report(self, validation_run_id: str | None) -> AssistantToolResult: ...

    @abstractmethod
    def get_uploaded_document_summary(
        self,
        document_ids: list[str],
        *,
        session_id: str,
    ) -> AssistantToolResult: ...

    @abstractmethod
    def explain_validation_finding(
        self,
        validation_run_id: str | None,
        finding_rule_id: str | None,
    ) -> AssistantToolResult: ...

    @abstractmethod
    def fallback_safe_response(self, reason: str) -> AssistantToolResult: ...


@runtime_checkable
class PayrollAssistantRunnerPort(Protocol):
    """Executes the assistant orchestration graph."""

    async def run(
        self,
        *,
        message: str,
        session_id: str,
        document_ids: list[str],
        validation_run_id: str | None,
        locale: str,
        prepared_employee_context: str | None = None,
        answer_strategy: str | None = None,
        period_label: str | None = None,
    ) -> dict[str, object]: ...
