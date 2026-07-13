"""Ensure organization + default department exist for accountant workflows."""

from __future__ import annotations

from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.infrastructure.persistence.models import DepartmentModel, OrganizationModel


DEFAULT_DEPARTMENT_CODE = "GENERAL"


def default_department_id(organization_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"payroll-copilot:dept:{organization_id}:{DEFAULT_DEPARTMENT_CODE}")


class OrganizationWorkspaceBootstrap:
    """Creates org + default department when missing (dev/demo safe)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_organization(self, organization_id: UUID, *, name: str = "Organization") -> UUID:
        result = await self._session.execute(
            select(OrganizationModel).where(OrganizationModel.id == organization_id)
        )
        if result.scalar_one_or_none() is None:
            self._session.add(
                OrganizationModel(
                    id=organization_id,
                    name=name,
                    slug=f"org-{str(organization_id)[:8]}",
                    settings={"source": "accountant_portal_bootstrap"},
                )
            )
            await self._session.flush()
        return organization_id

    async def ensure_default_department(self, organization_id: UUID) -> UUID:
        await self.ensure_organization(organization_id)
        dept_id = default_department_id(organization_id)
        result = await self._session.execute(
            select(DepartmentModel).where(DepartmentModel.id == dept_id)
        )
        if result.scalar_one_or_none() is None:
            self._session.add(
                DepartmentModel(
                    id=dept_id,
                    organization_id=organization_id,
                    code=DEFAULT_DEPARTMENT_CODE,
                    name={"en": "General", "he": "כללי", "ar": "عام"},
                    rule_profile="payroll",
                    is_active=True,
                )
            )
            await self._session.flush()
        return dept_id
