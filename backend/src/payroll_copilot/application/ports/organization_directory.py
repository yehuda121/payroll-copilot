"""Read-only organization directory for admin census (no bootstrap writes)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID


class OrganizationDirectoryPort(ABC):
    """Lists known organizations without mutating bootstrap state."""

    @abstractmethod
    async def list_organization_ids(self) -> list[UUID]:
        """Return organization ids discovered from persisted org meta rows."""
        ...
