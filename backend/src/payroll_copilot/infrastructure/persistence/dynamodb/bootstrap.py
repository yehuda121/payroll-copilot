"""Organization / department bootstrap for DynamoDB."""

from __future__ import annotations

from uuid import UUID, uuid5, NAMESPACE_URL

from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI1, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import dumps_value

DEFAULT_DEPARTMENT_CODE = "GENERAL"


def default_department_id(organization_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"payroll-copilot:dept:{organization_id}:{DEFAULT_DEPARTMENT_CODE}")


class DynamoOrganizationBootstrap(OrganizationBootstrapPort):
    DEMO_ORG_SLUG = "demo-validation"

    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    async def ensure_demo_organization(self, organization_id: UUID) -> None:
        existing = await self._table.get_item({"PK": keys.org_pk(organization_id), "SK": "META"})
        if existing is not None:
            return
        await self._table.put_item(
            {
                "PK": keys.org_pk(organization_id),
                "SK": "META",
                "entity_type": "organization",
                "id": str(organization_id),
                "name": "Demo Validation Organization",
                "slug": self.DEMO_ORG_SLUG,
                "settings": {"temporary": True, "source": "demo_validation_bootstrap"},
            }
        )


class DynamoOrganizationWorkspaceBootstrap:
    """Creates org + default department when missing (dev/demo safe)."""

    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    async def ensure_organization(self, organization_id: UUID, *, name: str = "Organization") -> UUID:
        existing = await self._table.get_item({"PK": keys.org_pk(organization_id), "SK": "META"})
        if existing is None:
            await self._table.put_item(
                {
                    "PK": keys.org_pk(organization_id),
                    "SK": "META",
                    "entity_type": "organization",
                    "id": str(organization_id),
                    "name": name,
                    "slug": f"org-{str(organization_id)[:8]}",
                    "settings": {"source": "accountant_portal_bootstrap"},
                }
            )
        return organization_id

    async def ensure_default_department(self, organization_id: UUID) -> UUID:
        await self.ensure_organization(organization_id)
        dept_id = default_department_id(organization_id)
        existing = await self._table.get_item(
            {"PK": keys.org_pk(organization_id), "SK": keys.dept_sk(dept_id)}
        )
        if existing is None:
            await self._table.put_item(
                {
                    "PK": keys.org_pk(organization_id),
                    "SK": keys.dept_sk(dept_id),
                    "entity_type": "department",
                    "GSI1PK": keys.gsi1_dept(dept_id),
                    "GSI1SK": keys.org_pk(organization_id),
                    "id": str(dept_id),
                    "organization_id": str(organization_id),
                    "code": DEFAULT_DEPARTMENT_CODE,
                    "name": dumps_value({"en": "General", "he": "כללי", "ar": "عام"}),
                    "rule_profile": "payroll",
                    "is_active": True,
                }
            )
        return dept_id
