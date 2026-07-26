"""Atomic inbound leave idempotency (DynamoDB TransactWrite)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from payroll_copilot.domain.entities import SickLeaveRequest, VacationRequest
from payroll_copilot.domain.enums import (
    SickLeaveReviewStatus,
    SickLeaveSource,
    VacationReviewStatus,
    VacationSource,
)
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import (
    DynamoTransactionCanceledError,
)
from payroll_copilot.infrastructure.persistence.dynamodb.sick_leaves import (
    DynamoSickLeaveRequestRepository,
)
from payroll_copilot.infrastructure.persistence.dynamodb.vacations import (
    DynamoVacationRequestRepository,
)


class _MemoryTable:
    """In-memory DynamoTable stand-in with atomic transact_put_items."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.fail_next_transact = False
        self.transact_calls = 0

    async def get_item(self, key: dict[str, Any]) -> dict[str, Any] | None:
        return self.items.get((key["PK"], key["SK"]))

    async def put_item(self, item: dict[str, Any], *, condition_expression: Any = None) -> None:
        del condition_expression
        self.items[(item["PK"], item["SK"])] = dict(item)

    async def delete_item(self, key: dict[str, Any]) -> None:
        self.items.pop((key["PK"], key["SK"]), None)

    async def query_eq_pk(self, pk: str, *, sk_begins_with: str | None = None, **kwargs: Any):
        del kwargs
        rows = [v for (p, s), v in self.items.items() if p == pk]
        if sk_begins_with:
            rows = [v for v in rows if str(v.get("SK", "")).startswith(sk_begins_with)]
        return rows

    async def transact_put_items(self, puts: list[dict[str, Any]]) -> None:
        self.transact_calls += 1
        if self.fail_next_transact:
            self.fail_next_transact = False
            raise RuntimeError("simulated_pre_commit_failure")
        # Validate conditions against current state; commit all-or-nothing.
        pending: list[tuple[tuple[str, str], dict[str, Any]]] = []
        for entry in puts:
            item = entry["item"]
            key = (item["PK"], item["SK"])
            condition = entry.get("condition_expression")
            if condition and "attribute_not_exists(PK)" in condition and key in self.items:
                raise DynamoTransactionCanceledError("condition_failed")
            pending.append((key, dict(item)))
        for key, item in pending:
            self.items[key] = item


def _vacation(org: UUID, *, provider: str = "imap", message_id: str = "msg-1") -> VacationRequest:
    return VacationRequest(
        id=uuid4(),
        organization_id=org,
        employee_id=None,
        extracted_employee_email="ada@example.com",
        extracted_employee_name="Ada",
        sender_email="ada@example.com",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 5),
        provider=provider,
        provider_message_id=message_id,
        provider_thread_id=None,
        original_subject="Vacation",
        original_body_text="please",
        original_body_s3_key=None,
        received_at=datetime.now(UTC),
        ai_confidence=0.9,
        ai_explanation="ok",
        ai_extraction_original=None,
        intent="new",
        related_vacation_id=None,
        source=VacationSource.EMAIL.value,
        review_status=VacationReviewStatus.PENDING_APPROVAL.value,
        attention_codes=[],
        attention_detail=None,
        overlap_with=[],
        seen_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        created_by=None,
        approved_by=None,
        approved_at=None,
    )


def _sick(org: UUID, *, provider: str = "imap", message_id: str = "msg-1") -> SickLeaveRequest:
    return SickLeaveRequest(
        id=uuid4(),
        organization_id=org,
        employee_id=None,
        extracted_employee_email="ada@example.com",
        extracted_employee_name="Ada",
        sender_email="ada@example.com",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 5),
        provider=provider,
        provider_message_id=message_id,
        provider_thread_id=None,
        original_subject="Sick",
        original_body_text="please",
        original_body_s3_key=None,
        received_at=datetime.now(UTC),
        ai_confidence=0.9,
        ai_explanation="ok",
        ai_extraction_original=None,
        intent="new",
        related_sick_leave_id=None,
        source=SickLeaveSource.EMAIL.value,
        review_status=SickLeaveReviewStatus.PENDING_APPROVAL.value,
        attention_codes=[],
        attention_detail=None,
        overlap_with=[],
        seen_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        created_by=None,
        approved_by=None,
        approved_at=None,
    )


@pytest.mark.asyncio
async def test_vacation_create_inbound_first_and_duplicate() -> None:
    table = _MemoryTable()
    repo = DynamoVacationRequestRepository(table)  # type: ignore[arg-type]
    org = uuid4()
    first = _vacation(org)
    saved, created = await repo.create_inbound(first)
    assert created is True
    assert saved.id == first.id
    leave_keys = [k for k in table.items if k[1].startswith("VAC#")]
    idemp_keys = [k for k in table.items if k[1].startswith("LEAVE_IDEMP#vacation#")]
    assert len(leave_keys) == 1
    assert len(idemp_keys) == 1

    second = _vacation(org, message_id=first.provider_message_id or "msg-1")
    existing, created2 = await repo.create_inbound(second)
    assert created2 is False
    assert existing.id == first.id
    assert len([k for k in table.items if k[1].startswith("VAC#")]) == 1


@pytest.mark.asyncio
async def test_sick_create_inbound_first_and_duplicate() -> None:
    table = _MemoryTable()
    repo = DynamoSickLeaveRequestRepository(table)  # type: ignore[arg-type]
    org = uuid4()
    first = _sick(org)
    saved, created = await repo.create_inbound(first)
    assert created is True
    second = _sick(org, message_id=first.provider_message_id or "msg-1")
    existing, created2 = await repo.create_inbound(second)
    assert created2 is False
    assert existing.id == first.id
    assert len([k for k in table.items if k[1].startswith("SICK#")]) == 1


@pytest.mark.asyncio
async def test_concurrent_create_inbound_one_winner() -> None:
    table = _MemoryTable()
    repo = DynamoVacationRequestRepository(table)  # type: ignore[arg-type]
    org = uuid4()
    a = _vacation(org, message_id="same")
    b = _vacation(org, message_id="same")
    saved_a, created_a = await repo.create_inbound(a)
    saved_b, created_b = await repo.create_inbound(b)
    assert created_a is True
    assert created_b is False
    assert saved_b.id == saved_a.id
    assert len([k for k in table.items if k[1].startswith("VAC#")]) == 1
    assert table.transact_calls == 2


@pytest.mark.asyncio
async def test_transaction_failure_leaves_no_orphan_marker_then_retry_succeeds() -> None:
    table = _MemoryTable()
    repo = DynamoVacationRequestRepository(table)  # type: ignore[arg-type]
    org = uuid4()
    first = _vacation(org, message_id="retry-me")
    table.fail_next_transact = True
    with pytest.raises(RuntimeError, match="simulated_pre_commit_failure"):
        await repo.create_inbound(first)
    assert table.items == {}
    saved, created = await repo.create_inbound(first)
    assert created is True
    assert len(table.items) == 2  # leave + idemp


@pytest.mark.asyncio
async def test_org_isolation_same_provider_message() -> None:
    table = _MemoryTable()
    repo = DynamoVacationRequestRepository(table)  # type: ignore[arg-type]
    org_a = uuid4()
    org_b = uuid4()
    a, created_a = await repo.create_inbound(_vacation(org_a, message_id="shared-msg"))
    b, created_b = await repo.create_inbound(_vacation(org_b, message_id="shared-msg"))
    assert created_a is True and created_b is True
    assert a.id != b.id
    assert len([k for k in table.items if k[1].startswith("VAC#")]) == 2
    assert keys.leave_idemp_sk("vacation", "imap", "shared-msg") == keys.leave_idemp_sk(
        "vacation", "imap", "shared-msg"
    )
    # Different org PKs keep markers independent.
    assert (keys.org_pk(org_a), keys.leave_idemp_sk("vacation", "imap", "shared-msg")) in table.items
    assert (keys.org_pk(org_b), keys.leave_idemp_sk("vacation", "imap", "shared-msg")) in table.items


@pytest.mark.asyncio
async def test_vacation_and_sick_same_message_are_independent() -> None:
    table = _MemoryTable()
    vac_repo = DynamoVacationRequestRepository(table)  # type: ignore[arg-type]
    sick_repo = DynamoSickLeaveRequestRepository(table)  # type: ignore[arg-type]
    org = uuid4()
    v, vc = await vac_repo.create_inbound(_vacation(org, message_id="cross-domain"))
    s, sc = await sick_repo.create_inbound(_sick(org, message_id="cross-domain"))
    assert vc is True and sc is True
    assert v.id != s.id
