"""Landing workflow graph port — application depends on this, not LangGraph."""

from __future__ import annotations

from typing import Any, Protocol


class LandingWorkflowPort(Protocol):
    async def run_turn(
        self,
        *,
        session_id: str | None,
        message: str,
        files: list[Any],
        locale: str,
        explain_finding_id: str | None = None,
        explain_rule_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def resume_review(
        self,
        *,
        session_id: str,
        confirmed_fields: list[dict[str, Any]],
        locale: str | None = None,
    ) -> dict[str, Any]: ...
