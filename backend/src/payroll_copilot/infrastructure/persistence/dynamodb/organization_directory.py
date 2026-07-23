"""DynamoDB organization directory (read-only scan of org META rows)."""

from __future__ import annotations

from uuid import UUID

from boto3.dynamodb.conditions import Attr

from payroll_copilot.application.ports.organization_directory import OrganizationDirectoryPort
from payroll_copilot.infrastructure.persistence.dynamodb.client import DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import loads_uuid


class DynamoOrganizationDirectory(OrganizationDirectoryPort):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    async def list_organization_ids(self) -> list[UUID]:
        items = await self._table.scan(
            filter_expression=Attr("entity_type").eq("organization") & Attr("SK").eq("META"),
        )
        ids: list[UUID] = []
        seen: set[UUID] = set()
        for item in items:
            org_id = loads_uuid(item.get("id"))
            if org_id is None:
                continue
            if org_id in seen:
                continue
            seen.add(org_id)
            ids.append(org_id)
        return sorted(ids, key=str)
