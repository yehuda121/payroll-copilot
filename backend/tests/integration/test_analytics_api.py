"""Integration smoke tests for analytics auth gates."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_employee_salary_analytics_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/analytics/employee/salary")
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_org_payroll_analytics_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/analytics/org/payroll")
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_admin_census_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/analytics/admin/census")
    assert response.status_code in {401, 403}
