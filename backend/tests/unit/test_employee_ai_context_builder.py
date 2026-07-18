"""Tests for authenticated Employee AI context routing and sanitization."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from payroll_copilot.application.services.employee_ai_context_builder import (
    EmployeeAIContextBuilder,
    _sanitize_for_llm,
    analyze_employee_context_intent,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What is my name?", {"profile": True}),
        ("What was my salary last month?", {"payroll": True, "year": 2026, "month": 6}),
        (
            "Does my salary comply with overtime rules?",
            {"payroll": True, "validation": False},
        ),
        ("Show my uploaded documents", {"documents": True}),
        ("מה השם שלי?", {"profile": True}),
        ("ما هو راتبي الشهر الماضي؟", {"payroll": True, "year": 2026, "month": 6}),
    ],
)
def test_employee_context_intent_is_deterministic(
    message: str,
    expected: dict[str, object],
) -> None:
    intent = analyze_employee_context_intent(
        message,
        today=date(2026, 7, 18),
    )
    for key, value in expected.items():
        assert getattr(intent, key) == value


def test_labor_law_only_question_does_not_request_employee_data() -> None:
    intent = analyze_employee_context_intent(
        "What does the law say about vacation?",
        today=date(2026, 7, 18),
    )
    assert intent.needs_employee_context is False


def test_llm_context_removes_identifiers_and_raw_national_id_fields() -> None:
    sanitized = _sanitize_for_llm(
        {
            "document_id": "private-document-id",
            "fields": [
                {
                    "key": "national_id",
                    "value": "123456782",
                    "source_text": "ID 123456782",
                    "status": "FOUND",
                },
                {"key": "net_salary", "value": 9000},
            ],
        }
    )
    rendered = str(sanitized)
    assert "private-document-id" not in rendered
    assert "123456782" not in rendered
    assert "net_salary" in rendered
    assert "9000" in rendered


@pytest.mark.asyncio
async def test_profile_context_uses_bound_employee_and_masks_national_id() -> None:
    employee = SimpleNamespace(
        id="employee-bound-by-auth",
        organization_id="org-bound-by-auth",
        employee_number="1005",
        first_name="Noa",
        last_name="Levi",
        status=SimpleNamespace(value="active"),
        metadata={"national_id_masked": "*****1234"},
    )
    # Profile intent does not touch repositories; sentinels prove the builder
    # can only use the already-bound employee object for this resource.
    builder = EmployeeAIContextBuilder(
        documents=object(),  # type: ignore[arg-type]
        validation_runs=object(),  # type: ignore[arg-type]
        validation_findings=object(),  # type: ignore[arg-type]
        extractions=object(),  # type: ignore[arg-type]
    )

    result = await builder.build(
        message="What is my name and national ID?",
        employee=employee,
        national_id_encrypted=b"must-never-reach-the-llm",
        today=date(2026, 7, 18),
    )

    assert result.profile is not None
    assert result.profile["full_name"] == "Noa Levi"
    assert result.profile["national_id_masked"] == "*****1234"
    assert "must-never-reach-the-llm" not in result.prepared_context
    assert "employee-bound-by-auth" not in result.prepared_context
    assert "org-bound-by-auth" not in result.prepared_context
