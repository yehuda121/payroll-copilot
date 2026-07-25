"""Unit tests for vacation business rules and approval classification."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from payroll_copilot.application.services.vacation_rules import (
    classify_for_approval,
    collect_date_attention_codes,
    intervals_overlap,
    normalize_email,
)
from payroll_copilot.domain.entities import VacationRequest
from payroll_copilot.domain.enums import VacationAttentionCode, VacationReviewStatus


def test_normalize_email() -> None:
    assert normalize_email("  Ada@Example.com ") == "ada@example.com"
    assert normalize_email("  ") is None
    assert normalize_email(None) is None


def test_intervals_overlap() -> None:
    assert intervals_overlap(date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 5), date(2026, 1, 20))
    assert not intervals_overlap(
        date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 11), date(2026, 1, 20)
    )


def test_date_attention_codes() -> None:
    codes = collect_date_attention_codes(None, date(2026, 1, 2))
    assert VacationAttentionCode.MISSING_START_DATE.value in codes
    codes = collect_date_attention_codes(date(2026, 2, 1), date(2026, 1, 1))
    assert VacationAttentionCode.END_BEFORE_START.value in codes


def test_hard_block_employee_not_found() -> None:
    vac = VacationRequest(
        id=uuid4(),
        organization_id=uuid4(),
        review_status=VacationReviewStatus.REQUIRES_ATTENTION.value,
        attention_codes=[VacationAttentionCode.EMPLOYEE_NOT_FOUND.value],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    result = classify_for_approval(vac)
    assert result.classification == "BLOCKED"


def test_warning_overlap_when_employee_linked() -> None:
    vac = VacationRequest(
        id=uuid4(),
        organization_id=uuid4(),
        employee_id=uuid4(),
        review_status=VacationReviewStatus.PENDING_APPROVAL.value,
        attention_codes=[VacationAttentionCode.OVERLAP.value],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    result = classify_for_approval(vac)
    assert result.classification == "WARNING"
    assert VacationAttentionCode.OVERLAP.value in result.codes


def test_ready_when_clean() -> None:
    vac = VacationRequest(
        id=uuid4(),
        organization_id=uuid4(),
        employee_id=uuid4(),
        review_status=VacationReviewStatus.PENDING_APPROVAL.value,
        attention_codes=[],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 5),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert classify_for_approval(vac).classification == "READY"
