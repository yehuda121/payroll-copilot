"""Organization id resolution port (demo fallback policy stays in infrastructure)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class OrganizationIdResolver(Protocol):
    def resolve(self, organization_id: UUID | None) -> UUID: ...
