"""Regression: VacationRequest Dynamo serialization must accept float confidence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from payroll_copilot.domain.entities import VacationRequest
from payroll_copilot.infrastructure.persistence.dynamodb.vacations import (
    DynamoVacationRequestRepository,
)


def _vacation(*, confidence: float | None = 0.65) -> VacationRequest:
    now = datetime.now(UTC)
    return VacationRequest(
        id=uuid4(),
        organization_id=uuid4(),
        extracted_employee_email="ada@example.com",
        start_date=date(2026, 11, 12),
        end_date=date(2026, 11, 14),
        provider="imap",
        provider_message_id="msg-float-test",
        ai_confidence=confidence,
        intent="new",
        source="email",
        review_status="requires_attention",
        created_at=now,
        updated_at=now,
    )


def test_to_item_converts_ai_confidence_float_to_decimal() -> None:
    repo = DynamoVacationRequestRepository(table=None)  # type: ignore[arg-type]
    item = repo._to_item(_vacation(confidence=0.65))
    assert isinstance(item["ai_confidence"], Decimal)
    assert item["ai_confidence"] == Decimal("0.65")


def test_to_entity_round_trip_preserves_confidence() -> None:
    repo = DynamoVacationRequestRepository(table=None)  # type: ignore[arg-type]
    item = repo._to_item(_vacation(confidence=0.65))
    restored = repo._to_entity(item)
    assert restored.ai_confidence is not None
    assert abs(restored.ai_confidence - 0.65) < 1e-9


def test_none_confidence_omitted_from_item() -> None:
    repo = DynamoVacationRequestRepository(table=None)  # type: ignore[arg-type]
    item = repo._to_item(_vacation(confidence=None))
    assert "ai_confidence" not in item
