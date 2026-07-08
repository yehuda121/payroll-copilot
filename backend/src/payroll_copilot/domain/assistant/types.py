"""Domain-safe assistant types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AssistantSourceType(StrEnum):
    LEGAL_RULE = "legal_rule"
    VALIDATION_REPORT = "validation_report"
    DOCUMENT = "document"
    CONTRACT = "contract"
    ATTENDANCE = "attendance"
    SYSTEM = "system"


class AssistantGuardrailStatus(StrEnum):
    """Public assistant outcome statuses.

    Source-backed answers and greetings still use PASSED / ANSWERED_FROM_SOURCE.
    Missing exact sources on in-domain questions is LIMITED_IN_DOMAIN (safe), not blocked.
    """

    PASSED = "passed"
    ANSWERED_FROM_SOURCE = "answered_from_source"
    LIMITED_IN_DOMAIN = "limited_in_domain"
    BLOCKED_OFF_TOPIC = "blocked_off_topic"
    BLOCKED_SAFETY = "blocked_safety"
    # Legacy aliases kept for older callers/tests during transition.
    BLOCKED = "blocked"
    LIMITED = "limited"


@dataclass(frozen=True, slots=True)
class AssistantSource:
    title: str
    type: AssistantSourceType
    reference: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "type": self.type.value,
            "reference": self.reference,
        }


@dataclass(slots=True)
class AssistantToolResult:
    tool_name: str
    success: bool
    content: str
    sources: list[AssistantSource] = field(default_factory=list)
    requires_human_review: bool = False
