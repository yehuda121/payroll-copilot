"""Organization resolution helpers — demo fallback only in local dev without Cognito."""

from __future__ import annotations

from uuid import UUID

from payroll_copilot.domain.seed_ids import DEMO_ORGANIZATION_ID
from payroll_copilot.infrastructure.auth.cognito import cognito_configured
from payroll_copilot.infrastructure.config.production_guards import is_local_dev_env
from payroll_copilot.infrastructure.config.settings import Settings, get_settings


class OrganizationBindingRequiredError(ValueError):
    """Raised when a production operation requires an explicit organization id."""


def allow_demo_organization_fallback(settings: Settings | None = None) -> bool:
    """True only for local/dev environments running without Cognito."""
    s = settings or get_settings()
    return not cognito_configured(s) and is_local_dev_env(s)


def resolve_organization_id(
    organization_id: UUID | None,
    *,
    settings: Settings | None = None,
) -> UUID:
    """Return an organization id or raise when production requires an explicit value."""
    if organization_id is not None:
        return organization_id
    if allow_demo_organization_fallback(settings):
        return DEMO_ORGANIZATION_ID
    raise OrganizationBindingRequiredError("organization_id is required")


class SettingsOrganizationIdResolver:
    """Infrastructure adapter implementing OrganizationIdResolver."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    def resolve(self, organization_id: UUID | None) -> UUID:
        return resolve_organization_id(organization_id, settings=self._settings)
