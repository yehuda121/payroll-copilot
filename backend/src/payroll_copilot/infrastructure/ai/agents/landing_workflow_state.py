"""Landing workflow state TypedDict — shared by the LangGraph agent.

Kept separate from graph orchestration so the oversized graph module can shrink
without changing node behavior.
"""

from __future__ import annotations

from typing import Any, TypedDict

INSUFFICIENT_INFO = "I don't have enough verified information."


class LandingWorkflowState(TypedDict, total=False):
    session_id: str
    locale: str
    message: str
    files: list[dict[str, Any]]
    intent: str
    route: str
    guardrail_status: str
    rejected: bool
    reject_reason: str
    document_id: str | None
    extraction_id: str | None
    document_ids: list[str]
    extracted_fields: list[dict[str, Any]]
    confirmed_fields: list[dict[str, Any]]
    validation_run_id: str | None
    validation_report: dict[str, Any] | None
    field_statuses: list[dict[str, Any]]
    answer: str
    sources: list[dict[str, str | None]]
    phase: str
    used_nodes: list[str]
    explain_finding_id: str | None
    explain_rule_id: str | None
    confidence: float
    requires_human_review: bool
    interrupt_payload: dict[str, Any] | None
