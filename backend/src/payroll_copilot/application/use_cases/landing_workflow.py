"""Landing workflow application use case — thin facade over LangGraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from payroll_copilot.application.services.landing_file_guardrail import LandingFilePayload
from payroll_copilot.infrastructure.ai.agents.landing_workflow_graph import LandingWorkflowGraph


@dataclass(frozen=True, slots=True)
class LandingTurnCommand:
    message: str = ""
    session_id: str | None = None
    locale: str = "en"
    files: list[LandingFilePayload] = field(default_factory=list)
    explain_finding_id: str | None = None
    explain_rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class LandingResumeCommand:
    session_id: str
    confirmed_fields: list[dict[str, Any]]
    locale: str | None = None


class LandingWorkflowUseCase:
    def __init__(self, graph: LandingWorkflowGraph) -> None:
        self._graph = graph

    async def turn(self, command: LandingTurnCommand) -> dict[str, Any]:
        return await self._graph.run_turn(
            session_id=command.session_id,
            message=command.message,
            files=command.files,
            locale=command.locale,
            explain_finding_id=command.explain_finding_id,
            explain_rule_id=command.explain_rule_id,
        )

    async def resume(self, command: LandingResumeCommand) -> dict[str, Any]:
        return await self._graph.resume_review(
            session_id=command.session_id,
            confirmed_fields=command.confirmed_fields,
            locale=command.locale,
        )
