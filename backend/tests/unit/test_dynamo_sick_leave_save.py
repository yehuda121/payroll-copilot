"""Regression: DynamoSickLeaveRequestRepository.save must use sick_leave param."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from payroll_copilot.domain.entities import SickLeaveRequest
from payroll_copilot.infrastructure.persistence.dynamodb.sick_leaves import (
    DynamoSickLeaveRequestRepository,
)


class _FakeDynamoTable:
    def __init__(self) -> None:
        self.put_items: list[dict] = []

    async def put_item(self, item: dict) -> None:
        self.put_items.append(item)


@pytest.mark.asyncio
async def test_dynamo_sick_leave_save_uses_sick_leave_param_not_stale_vacation() -> None:
    table = _FakeDynamoTable()
    repo = DynamoSickLeaveRequestRepository(table)  # type: ignore[arg-type]
    org_id = uuid4()
    sick_id = uuid4()
    before = datetime.now(UTC) - timedelta(seconds=5)
    entity = SickLeaveRequest(
        id=sick_id,
        organization_id=org_id,
        employee_id=uuid4(),
        extracted_employee_email="ada@example.com",
        extracted_employee_name="Ada",
        start_date=date(2026, 12, 11),
        end_date=date(2026, 12, 12),
        provider="imap",
        provider_message_id="msg-1",
        source="email",
        intent="new",
        review_status="pending_approval",
        created_at=before,
        updated_at=before,
    )

    saved = await repo.save(entity)

    assert saved is entity
    assert saved.updated_at is not None
    assert saved.updated_at >= before
    assert saved.updated_at > before
    assert len(table.put_items) == 1
    item = table.put_items[0]
    assert item["entity_type"] == "sick_leave_request"
    assert item["SK"] == f"SICK#{sick_id}"
    assert item["PK"] == f"ORG#{org_id}"
