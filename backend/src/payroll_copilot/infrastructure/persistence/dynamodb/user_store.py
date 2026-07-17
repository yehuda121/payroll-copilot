"""DynamoDB user binding store (Cognito subject mirror)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI1, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import dumps_value, loads_uuid


@dataclass
class UserRecord:
    id: UUID
    email: str
    role: UserRole
    preferred_locale: str = "he"
    is_active: bool = True
    organization_id: UUID | None = None
    employee_id: UUID | None = None
    password_hash: str | None = None


class DynamoUserStore:
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _item_from_record(self, user: UserRecord) -> dict:
        org_id = user.organization_id
        pk = keys.org_pk(org_id) if org_id is not None else f"USERROOT#{user.id}"
        now = datetime.now(UTC).isoformat()
        item = {
            "PK": pk,
            "SK": keys.user_sk(user.id),
            "entity_type": "user_binding",
            "GSI1PK": keys.gsi1_user(user.id),
            "GSI1SK": pk,
            "id": str(user.id),
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "preferred_locale": user.preferred_locale,
            "is_active": user.is_active,
            "organization_id": dumps_value(user.organization_id),
            "employee_id": dumps_value(user.employee_id),
            "password_hash": user.password_hash,
            "updated_at": now,
        }
        return {k: v for k, v in item.items() if v is not None}

    def _record_from_item(self, item: dict) -> UserRecord:
        role_raw = str(item.get("role") or UserRole.EMPLOYEE.value)
        try:
            role = UserRole(role_raw)
        except ValueError:
            role = UserRole.EMPLOYEE
        return UserRecord(
            id=UUID(str(item["id"])),
            email=str(item.get("email") or ""),
            role=role,
            preferred_locale=str(item.get("preferred_locale") or "he"),
            is_active=bool(item.get("is_active", True)),
            organization_id=loads_uuid(item.get("organization_id")),
            employee_id=loads_uuid(item.get("employee_id")),
            password_hash=item.get("password_hash"),
        )

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        items = await self._table.query_eq_pk(
            keys.gsi1_user(user_id),
            index_name=GSI1,
            limit=1,
        )
        if not items:
            return None
        return self._record_from_item(items[0])

    async def save(self, user: UserRecord) -> UserRecord:
        existing = await self.get_by_id(user.id)
        if existing is not None and existing.organization_id != user.organization_id:
            # Move binding if org changed: delete old primary key.
            old_pk = (
                keys.org_pk(existing.organization_id)
                if existing.organization_id is not None
                else f"USERROOT#{user.id}"
            )
            await self._table.delete_item({"PK": old_pk, "SK": keys.user_sk(user.id)})
        await self._table.put_item(self._item_from_record(user))
        return user
