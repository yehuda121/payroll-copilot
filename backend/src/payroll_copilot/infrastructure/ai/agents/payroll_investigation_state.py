"""LangGraph state for the payroll investigation agent."""

from __future__ import annotations

from typing import Any, TypedDict

from payroll_copilot.domain.investigation.types import (
    CompletenessReport,
    LineItemDelta,
    PeriodRef,
    PeriodSnapshot,
)


class InvestigationGraphState(TypedDict):
    message: str
    locale: str
    session_id: str
    organization_id: str
    employee_id: str
    include_unpublished: bool
    target_year: int | None
    target_month: int | None
    focus: str
    requested_field_keys: list[str]
    available_periods: list[str]
    target_period: PeriodRef | None
    comparison_period: PeriodRef | None
    lookback_attempts: list[str]
    current_snapshot: PeriodSnapshot | None
    prior_snapshot: PeriodSnapshot | None
    completeness: CompletenessReport | None
    enrichment_needed: bool
    deltas: list[LineItemDelta]
    outcome: str
    clarification_prompt: str | None
    answer: str
    confidence: float
    used_tools: list[str]
    sources: list[dict[str, str | None]]
    route_hint: str
    # Opaque bag for node-local notes (enrichment notes, errors).
    notes: list[str]
    # Keep Any for unused reserved keys without expanding TypedDict often.
    extra: dict[str, Any]
