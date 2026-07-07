"""Port for bootstrapping prerequisite organization records."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class OrganizationBootstrapPort(ABC):
    @abstractmethod
    async def ensure_demo_organization(self, organization_id: UUID) -> None:
        ...
