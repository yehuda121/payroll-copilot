"""Tests for answer strategy, conversation summary, and response openings."""

from __future__ import annotations

from datetime import date

from payroll_copilot.application.services.answer_strategy import (
    AnswerStrategy,
    resolve_answer_strategy,
)
from payroll_copilot.application.services.assistant_response_templates import (
    apply_response_opening,
    format_response_opening,
)
from payroll_copilot.application.services.conversation_summary import (
    ConversationSummaryStore,
)


def test_resolve_personal_payslip_with_hebrew_month() -> None:
    plan = resolve_answer_strategy(
        "כמה שכר נטו קיבלתי בתלוש של חודש מאי 2026?",
        today=date(2026, 7, 18),
    )
    assert plan.strategy == AnswerStrategy.PERSONAL_PAYSLIP
    assert plan.needs.payslip is True
    assert plan.year == 2026
    assert plan.month == 5
    assert plan.period_key == "2026-05"


def test_resolve_labor_law_without_personal_payslip() -> None:
    plan = resolve_answer_strategy(
        "What does the law say about vacation?",
        today=date(2026, 7, 18),
    )
    assert plan.strategy == AnswerStrategy.LABOR_LAW
    assert plan.needs.labor_law is True
    assert plan.needs.payslip is False


def test_referential_same_month_uses_summary_period() -> None:
    plan = resolve_answer_strategy(
        "What about the same month?",
        today=date(2026, 7, 18),
        summary_period="2026-05",
        has_conversation_summary=True,
    )
    assert plan.uses_referential_period is True
    assert plan.year == 2026
    assert plan.month == 5
    assert plan.needs.payslip is True


def test_conversation_history_strategy() -> None:
    plan = resolve_answer_strategy(
        "What did I ask before?",
        today=date(2026, 7, 18),
        has_conversation_summary=True,
    )
    assert plan.strategy == AnswerStrategy.CONVERSATION_HISTORY
    assert plan.needs.conversation_summary is True


def test_conversation_summary_store_updates_period() -> None:
    store = ConversationSummaryStore(ttl_hours=1)
    item = store.update_from_turn(
        "sess-1",
        strategy="personal_payslip",
        period_key="2026-05",
        loaded_resource_keys=["payroll_month_detail:2026-05"],
        user_question="net pay?",
    )
    assert item.last_period == "2026-05"
    assert item.current_topic == "personal_payslip"
    assert store.get("sess-1") is not None


def test_response_opening_payslip_includes_period() -> None:
    opening = format_response_opening(
        strategy="personal_payslip",
        locale="en",
        period_label="2026-05",
    )
    assert "2026-05" in opening
    assert opening.lower().startswith("according to your payslip")


def test_apply_response_opening_does_not_duplicate() -> None:
    body = "According to your payslip for 2026-05: net was 9000."
    result = apply_response_opening(
        body,
        strategy="personal_payslip",
        locale="en",
        period_label="2026-05",
    )
    assert result.count("According to your payslip") == 1
