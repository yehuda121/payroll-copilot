"""Payroll assistant chat use case."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from payroll_copilot.application.ports.assistant import PayrollAssistantRunnerPort


@dataclass(frozen=True, slots=True)
class AssistantChatCommand:
    message: str
    session_id: str | None = None
    document_ids: list[str] | None = None
    validation_run_id: str | None = None
    locale: str = "en"
    prepared_employee_context: str | None = None


@dataclass(frozen=True, slots=True)
class AssistantChatResult:
    answer: str
    session_id: str
    used_tools: list[str]
    sources: list[dict[str, str | None]]
    confidence: float
    requires_human_review: bool
    guardrail_status: str


class PayrollAssistantChatUseCase:
    """Application use case for public assistant chat."""

    def __init__(self, runner: PayrollAssistantRunnerPort) -> None:
        self._runner = runner

    async def execute(self, command: AssistantChatCommand) -> AssistantChatResult:
        session_id = command.session_id or str(uuid4())
        runner_args: dict[str, object] = {
            "message": command.message,
            "session_id": session_id,
            "document_ids": command.document_ids or [],
            "validation_run_id": command.validation_run_id,
            "locale": command.locale,
        }
        # Keep the public runner call byte-for-byte compatible when no employee
        # context exists. The authenticated employee endpoint is the only caller
        # that supplies this argument.
        if command.prepared_employee_context:
            runner_args["prepared_employee_context"] = command.prepared_employee_context
        payload = await self._runner.run(**runner_args)
        return AssistantChatResult(
            answer=str(payload["answer"]),
            session_id=str(payload["session_id"]),
            used_tools=list(payload.get("used_tools", [])),
            sources=list(payload.get("sources", [])),
            confidence=float(payload.get("confidence", 0.0)),
            requires_human_review=bool(payload.get("requires_human_review", False)),
            guardrail_status=str(payload.get("guardrail_status", "passed")),
        )
