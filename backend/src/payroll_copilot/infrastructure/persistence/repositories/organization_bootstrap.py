"""Bootstrap prerequisite organization records for demo validation runs."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.application.ports.organization_bootstrap import OrganizationBootstrapPort
from payroll_copilot.infrastructure.persistence.models import OrganizationModel


class SqlAlchemyOrganizationBootstrap(OrganizationBootstrapPort):
    """Ensures the demo organization exists for validation FK constraints.

    This is temporary infrastructure support until real organization provisioning
    is implemented.
    """

    DEMO_ORG_SLUG = "demo-validation"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_demo_organization(self, organization_id: UUID) -> None:
        result = await self._session.execute(
            select(OrganizationModel).where(OrganizationModel.id == organization_id)
        )
        if result.scalar_one_or_none() is not None:
            return

        self._session.add(
            OrganizationModel(
                id=organization_id,
                name="Demo Validation Organization",
                slug=self.DEMO_ORG_SLUG,
                settings={"temporary": True, "source": "demo_validation_bootstrap"},
            )
        )
        await self._session.flush()
