"""Domain types for the Payroll Investigation & Anomaly Agent.

Deterministic comparison facts live here. The LLM only explains these facts —
it never recalculates tax or salary rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class InvestigationOutcome(StrEnum):
    EXPLAINED = "explained"
    NEEDS_USER_INPUT = "needs_user_input"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class InvestigationFocus(StrEnum):
    GENERAL = "general"
    NET_GROSS = "net_gross"
    OVERTIME = "overtime"
    DEDUCTIONS = "deductions"
    PENSION = "pension"
    LEAVE = "leave"
    BASE_SALARY = "base_salary"


@dataclass(frozen=True, slots=True)
class PeriodRef:
    year: int
    month: int

    @property
    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    def __str__(self) -> str:
        return self.key


@dataclass(frozen=True, slots=True)
class LineItemDelta:
    """Deterministic variance between two periods for one field key."""

    field_key: str
    current_value: str | None
    prior_value: str | None
    absolute_delta: str | None
    direction: str  # increased | decreased | unchanged | appeared | disappeared | unknown


@dataclass(frozen=True, slots=True)
class ValidationFindingExcerpt:
    finding_id: str
    rule_id: str
    severity: str
    message: str
    period_key: str


@dataclass(slots=True)
class PeriodSnapshot:
    """Structured payslip snapshot for one employee period (auth-bound)."""

    period: PeriodRef
    document_id: UUID | None
    storage_key: str | None
    structured_fields: dict[str, Any] = field(default_factory=dict)
    finding_excerpts: list[ValidationFindingExcerpt] = field(default_factory=list)
    enrichment_applied: bool = False
    enrichment_notes: str | None = None


@dataclass(frozen=True, slots=True)
class CompletenessReport:
    is_complete: bool
    missing_essential_keys: tuple[str, ...]
    missing_enrichment_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvestigationPlan:
    focus: InvestigationFocus
    target_period: PeriodRef | None
    requested_field_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InvestigationResult:
    outcome: InvestigationOutcome
    answer: str
    target_period: PeriodRef | None
    comparison_period: PeriodRef | None
    deltas: tuple[LineItemDelta, ...]
    lookback_attempts: tuple[str, ...]
    used_tools: tuple[str, ...]
    sources: tuple[dict[str, str | None], ...]
    confidence: float
    clarification_prompt: str | None = None
    session_id: str = ""
