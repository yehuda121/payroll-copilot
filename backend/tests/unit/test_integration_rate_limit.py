"""Org-scoped rate limiting for n8n integration endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from payroll_copilot.infrastructure.security.rate_limiter import RateLimiter, reset_rate_limiter_for_tests
from payroll_copilot.presentation.api.rate_limit_deps import enforce_integration_org_rate_limit
from payroll_copilot.presentation.api.routes.integrations import (
    IntegrationPrincipal,
    _rate_limit_integration,
)


def _settings(**overrides: object) -> SimpleNamespace:
    base = {
        "rate_limit_enforced": True,
        "rate_limit_integration_per_hour_per_org": 3,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_integration_rate_limit_allows_normal_traffic(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_rate_limiter_for_tests()
    settings = _settings(rate_limit_integration_per_hour_per_org=5)
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.rate_limit_deps.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.rate_limit_deps.get_rate_limiter",
        lambda: RateLimiter(settings),
    )
    org = str(uuid4())
    for _ in range(5):
        enforce_integration_org_rate_limit(org)


def test_integration_rate_limit_exceeded_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_rate_limiter_for_tests()
    settings = _settings(rate_limit_integration_per_hour_per_org=2)
    limiter = RateLimiter(settings)
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.rate_limit_deps.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.rate_limit_deps.get_rate_limiter",
        lambda: limiter,
    )
    org = str(uuid4())
    enforce_integration_org_rate_limit(org)
    enforce_integration_org_rate_limit(org)
    with pytest.raises(HTTPException) as exc:
        enforce_integration_org_rate_limit(org)
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "rate_limit_exceeded"
    assert exc.value.detail["scope"] == "integration"


def test_integration_rate_limit_is_org_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_rate_limiter_for_tests()
    settings = _settings(rate_limit_integration_per_hour_per_org=1)
    limiter = RateLimiter(settings)
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.rate_limit_deps.get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        "payroll_copilot.presentation.api.rate_limit_deps.get_rate_limiter",
        lambda: limiter,
    )
    org_a = str(uuid4())
    org_b = str(uuid4())
    _rate_limit_integration(IntegrationPrincipal(organization_id=UUID(org_a)))
    # Org A exhausted
    with pytest.raises(HTTPException) as exc:
        enforce_integration_org_rate_limit(org_a)
    assert exc.value.status_code == 429
    # Org B still allowed
    enforce_integration_org_rate_limit(org_b)
