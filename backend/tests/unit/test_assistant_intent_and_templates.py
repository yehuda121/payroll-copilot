"""Tests for shared assistant intent terms and period parsing."""

from __future__ import annotations

from datetime import date

import pytest

from payroll_copilot.application.services.assistant_intent import (
    is_payroll_domain_message,
    is_personal_payroll_message,
    parse_message_period,
)
from payroll_copilot.application.services.assistant_response_templates import (
    sanitize_user_facing_answer,
    template_answer_from_facts,
)
from payroll_copilot.application.services.employee_ai_context_builder import (
    analyze_employee_context_intent,
)
from payroll_copilot.infrastructure.ai.guardrails.payroll_assistant_guardrails import (
    PayrollAssistantGuardrails,
)
from payroll_copilot.domain.assistant.types import AssistantGuardrailStatus


@pytest.mark.parametrize(
    ("message", "year", "month"),
    [
        ("2026-05", 2026, 5),
        ("2026/05", 2026, 5),
        ("2026.5", 2026, 5),
        ("מאי 2026", 2026, 5),
        ("ינואר 2026", 2026, 1),
        ("מרץ 2026", 2026, 3),
        ("דצמבר 2026", 2026, 12),
        ("May 2026", 2026, 5),
        ("January 2026", 2026, 1),
        ("December 2026", 2026, 12),
        ("2026 May", 2026, 5),
        ("2026 מאי", 2026, 5),
        ("last month", 2026, 6),
        ("previous month", 2026, 6),
        ("חודש שעבר", 2026, 6),
        ("current month", 2026, 7),
        ("this month", 2026, 7),
        ("החודש הנוכחי", 2026, 7),
    ],
)
def test_parse_message_period_natural_and_numeric(
    message: str,
    year: int,
    month: int,
) -> None:
    assert parse_message_period(message, today=date(2026, 7, 18)) == (year, month)


def test_hebrew_may_payslip_question_resolves_period() -> None:
    intent = analyze_employee_context_intent(
        "כמה שכר נטו קיבלתי בתלוש של חודש מאי 2026?",
        today=date(2026, 7, 18),
    )
    assert intent.payroll is True
    assert intent.year == 2026
    assert intent.month == 5
    assert intent.needs_period_clarification is False


def test_shared_intent_accepts_kibalti_for_guardrail_and_context() -> None:
    message = "כמה נטו קיבלתי?"
    normalized = " ".join(message.lower().split())
    assert is_personal_payroll_message(normalized) is True
    assert is_payroll_domain_message(normalized) is True
    result = PayrollAssistantGuardrails().evaluate_input(message)
    assert result.status == AssistantGuardrailStatus.PASSED


def test_vacation_law_stays_in_domain_without_personal_payroll_load() -> None:
    intent = analyze_employee_context_intent(
        "What does the law say about vacation?",
        today=date(2026, 7, 18),
    )
    assert intent.needs_employee_context is False
    result = PayrollAssistantGuardrails().evaluate_input(
        "What does the law say about vacation?"
    )
    assert result.status == AssistantGuardrailStatus.PASSED


def test_sanitize_strips_internal_labels() -> None:
    raw = "Based on Employee context and Prepared employee context: net is 9000"
    cleaned = sanitize_user_facing_answer(raw)
    assert "Employee context" not in cleaned
    assert "Prepared employee context" not in cleaned
    assert "9000" in cleaned


def test_template_answer_does_not_expose_internal_preamble() -> None:
    answer = template_answer_from_facts(
        "en",
        "Prepared employee context (facts only):\n{\"net\": 1}",
    )
    assert "Prepared employee context" not in answer
    assert "Based on the information available" in answer
