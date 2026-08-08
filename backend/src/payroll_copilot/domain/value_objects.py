"""Domain value objects."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from payroll_copilot.domain.enums import ConfidenceSource, FindingSeverity, RuleCategory


@dataclass(frozen=True, slots=True)
class ConfidenceScore:
    """Confidence score for an extracted or computed value."""

    value: float
    source: ConfidenceSource

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            msg = f"Confidence must be between 0.0 and 1.0, got {self.value}"
            raise ValueError(msg)

    @classmethod
    def certain(cls, source: ConfidenceSource = ConfidenceSource.RULE) -> ConfidenceScore:
        return cls(value=1.0, source=source)

    @classmethod
    def unknown(cls, source: ConfidenceSource) -> ConfidenceScore:
        return cls(value=0.0, source=source)

    def combine_with(self, other: ConfidenceScore) -> ConfidenceScore:
        """Return minimum confidence; prefer lower-confidence source."""
        if self.value <= other.value:
            return self
        return other


@dataclass(frozen=True, slots=True)
class PayPeriod:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            msg = f"Month must be 1-12, got {self.month}"
            raise ValueError(msg)

    @property
    def label(self) -> str:
        return f"{self.year}-{self.month:02d}"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "ILS"

    def __post_init__(self) -> None:
        if self.amount < 0:
            msg = f"Money amount cannot be negative: {self.amount}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class LocalizedText:
    """Localized message text keyed by locale."""

    translations: dict[str, str]

    def get(self, locale: str, fallback: str = "he") -> str:
        return self.translations.get(locale) or self.translations.get(fallback, "")


@dataclass(frozen=True, slots=True)
class RuleFinding:
    """A single validation finding from rule evaluation."""

    rule_id: str
    category: RuleCategory
    severity: FindingSeverity
    message_key: str
    message_params: dict[str, Any]
    expected_value: str | None
    actual_value: str | None
    confidence: ConfidenceScore
    legal_reference: str | None = None
    rag_citation: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RuleEvaluationOutcome:
    """Authoritative per-rule result from one orchestrator pass.

    outcome:
      - passed: rule executed and payslip satisfies the rule
      - failed: rule executed and produced a real violation (WARNING/CRITICAL)
      - uncertain: rule executed but evidence was insufficient (e.g. missing data INFO)
      - not_run: rule did not execute (not applicable, not ready, error, etc.)
      - skipped: legacy alias treated as not_run by consumers
    """

    rule_id: str
    outcome: str
    skip_reason: str | None = None
    reason_code: str | None = None
    message: str | None = None
    # Additive metadata for UI / developer visibility (optional on legacy rows).
    category: str | None = None
    display_category: str | None = None
    required_inputs: tuple[str, ...] = ()
    legal_source: str | None = None
    legal_version: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Aggregated result of a validation run."""

    validation_run_id: UUID
    overall_result: str
    overall_confidence: ConfidenceScore
    findings: tuple[RuleFinding, ...]
    rules_evaluated: int
    rules_failed: int
    # Additive: empty on legacy constructors / older persisted runs.
    rule_outcomes: tuple[RuleEvaluationOutcome, ...] = ()
    # Local YAML legal-rules bundle version used for this run (traceability).
    legal_rules_version: str | None = None
    legal_rules_effective_from: str | None = None

    @property
    def has_critical(self) -> bool:
        return any(f.severity == FindingSeverity.CRITICAL for f in self.findings)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.WARNING)
