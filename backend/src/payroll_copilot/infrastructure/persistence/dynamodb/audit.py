"""DynamoDB audit log repository."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from payroll_copilot.application.ports.employee_audit import (
    AuditLogEntry,
    AuditLogRecord,
    AuditLogRepository,
)
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI3, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import dumps_value, loads_datetime, loads_uuid


class DynamoAuditLogRepository(AuditLogRepository):
    """Append-only audit events. Numeric ids are time-derived for API compatibility."""

    GLOBAL_PK = "AUDIT#GLOBAL"

    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    @staticmethod
    def _new_numeric_id() -> int:
        # Millisecond timestamp + 3 random digits — unique enough for API consumers.
        return int(time.time() * 1000) * 1000 + (uuid4().int % 1000)

    def _pk(self, organization_id: UUID | None) -> str:
        if organization_id is None:
            return self.GLOBAL_PK
        return keys.org_pk(organization_id)

    async def append(self, entry: AuditLogEntry) -> AuditLogRecord:
        now = datetime.now(UTC)
        audit_id = self._new_numeric_id()
        sort_key = now.isoformat()
        details = dict(entry.details or {})
        item: dict = {
            "PK": self._pk(entry.organization_id),
            "SK": keys.audit_sk(sort_key=sort_key, audit_id=str(audit_id)),
            "entity_type": "audit_event",
            "id": audit_id,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": dumps_value(entry.resource_id),
            "organization_id": dumps_value(entry.organization_id),
            "user_id": dumps_value(entry.user_id),
            "details": dumps_value(details),
            "ip_address": entry.ip_address,
            "user_agent": entry.user_agent,
            "created_at": now.isoformat(),
        }
        dataset_id = details.get("dataset_id")
        if dataset_id:
            item["GSI3PK"] = keys.gsi3_dataset(str(dataset_id))
            item["GSI3SK"] = keys.audit_sk(sort_key=sort_key, audit_id=str(audit_id))
            item["dataset_id"] = str(dataset_id)
        await self._table.put_item({k: v for k, v in item.items() if v is not None})
        return AuditLogRecord(
            id=audit_id,
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            organization_id=entry.organization_id,
            user_id=entry.user_id,
            details=details,
            created_at=now,
        )

    async def list_recent(
        self,
        *,
        organization_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogRecord]:
        cap = min(max(1, limit), 500)
        if organization_id is not None:
            items = await self._table.query_eq_pk(
                self._pk(organization_id),
                sk_begins_with="AUDIT#",
                scan_index_forward=False,
            )
        else:
            # Cross-org listing is uncommon; query GLOBAL partition only.
            items = await self._table.query_eq_pk(
                self.GLOBAL_PK,
                sk_begins_with="AUDIT#",
                scan_index_forward=False,
            )
        start = max(0, offset)
        sliced = items[start : start + cap]
        return [
            AuditLogRecord(
                id=int(item.get("id") or 0),
                action=str(item.get("action") or ""),
                resource_type=str(item.get("resource_type") or ""),
                resource_id=loads_uuid(item.get("resource_id")),
                organization_id=loads_uuid(item.get("organization_id")),
                user_id=loads_uuid(item.get("user_id")),
                details=dict(item.get("details") or {}),
                created_at=loads_datetime(item.get("created_at")) or datetime.now(UTC),
            )
            for item in sliced
        ]

    async def delete_by_dataset_id(self, *, dataset_id: str) -> int:
        items = await self._table.query_eq_pk(keys.gsi3_dataset(dataset_id), index_name=GSI3)
        keys_to_delete = [
            {"PK": item["PK"], "SK": item["SK"]}
            for item in items
            if item.get("entity_type") == "audit_event"
        ]
        return await self._table.batch_delete(keys_to_delete)
