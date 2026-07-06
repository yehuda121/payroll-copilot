"""Rule engine domain interfaces and context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from payroll_copilot.domain.entities import (
    AttendanceRecord,
    Department,
    Employee,
    PayslipData,
)
from payroll_copilot.domain.enums import FindingSeverity, RuleCategory
from payroll_copilot.domain.value_objects import ConfidenceScore, PayPeriod, RuleFinding


@dataclass(frozen=True, slots=True)
class LegalRuleConfig:
    """Parsed configuration for a single legal rule from YAML."""

    rule_id: str
    description: dict[str, str]
    parameters: dict[str, Any]
    legal_reference: dict[str, str]
    severity: FindingSeverity


@dataclass(frozen=True, slots=True)
class LegalRulesBundle:
    """All loaded legal rule configurations."""

    version: str
    effective_from: str
    rules: dict[str, LegalRuleConfig]


@dataclass
class ValidationContext:
    """Immutable snapshot of all data needed for rule evaluation."""

    payslip: PayslipData
    employee: Employee
    department: Department
    period: PayPeriod
    legal_rules: LegalRulesBundle
    attendance_records: list[AttendanceRecord] = field(default_factory=list)
    historical_payslips: list[PayslipData] = field(default_factory=list)
    contract_clauses: list[dict[str, Any]] = field(default_factory=list)
    org_rule_configs: list[dict[str, Any]] = field(default_factory=list)
    field_confidences: dict[str, float] = field(default_factory=dict)
    disabled_rule_ids: frozenset[str] = frozenset()

    def field_confidence(self, field_name: str) -> ConfidenceScore:
        value = self.field_confidences.get(field_name, 0.0)
        from payroll_copilot.domain.enums import ConfidenceSource

        return ConfidenceScore(value=value, source=ConfidenceSource.OCR)


@runtime_checkable
class Rule(Protocol):
    """Protocol for all validation rules."""

    rule_id: str
    category: RuleCategory
    priority: int

    def applies_to(self, context: ValidationContext) -> bool: ...

    def evaluate(self, context: ValidationContext) -> RuleFinding | None: ...


class BaseRule(ABC):
    """Abstract base for rule implementations."""

    rule_id: str
    category: RuleCategory
    priority: int = 100

    @abstractmethod
    def applies_to(self, context: ValidationContext) -> bool:
        pass

    @abstractmethod
    def evaluate(self, context: ValidationContext) -> RuleFinding | None:
        pass

    @staticmethod
    def _violation(
        rule_id: str,
        category: RuleCategory,
        severity: FindingSeverity,
        message_key: str,
        expected: Any,
        actual: Any,
        confidence: ConfidenceScore,
        legal_reference: str | None = None,
        message_params: dict[str, Any] | None = None,
    ) -> RuleFinding:
        return RuleFinding(
            rule_id=rule_id,
            category=category,
            severity=severity,
            message_key=message_key,
            message_params=message_params or {"expected": str(expected), "actual": str(actual)},
            expected_value=str(expected),
            actual_value=str(actual),
            confidence=confidence,
            legal_reference=legal_reference,
        )

    @staticmethod
    def _missing_data(rule_id: str, category: RuleCategory, field_name: str) -> RuleFinding:
        return RuleFinding(
            rule_id=rule_id,
            category=category,
            severity=FindingSeverity.INFO,
            message_key="validation.missing_data",
            message_params={"field": field_name},
            expected_value=None,
            actual_value=None,
            confidence=ConfidenceScore.unknown(
                __import__(
                    "payroll_copilot.domain.enums", fromlist=["ConfidenceSource"]
                ).ConfidenceSource.OCR
            ),
        )


# Global rule registry populated at startup via decorator
_RULE_REGISTRY: dict[str, type[BaseRule]] = {}


def register_rule(cls: type[BaseRule]) -> type[BaseRule]:
    """Decorator to register a rule class in the global registry."""
    _RULE_REGISTRY[cls.rule_id] = cls  # type: ignore[attr-defined]
    return cls


def get_registered_rules() -> dict[str, type[BaseRule]]:
    return dict(_RULE_REGISTRY)
