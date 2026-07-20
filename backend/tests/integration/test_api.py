"""API integration tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from payroll_copilot.presentation.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_guest_session_creation(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/guest/session")
    assert response.status_code == 201
    data = response.json()
    assert "guest_token" in data
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_document_upload_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("payslip.pdf", b"%PDF-1.4 validation", "application/pdf")},
        data={"document_type": "payslip"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_validation_run_requires_guest_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/validation/run",
        json={"document_id": "00000000-0000-4000-8000-000000000001"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_legal_rules_list_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/compliance/legal-rules")
    assert response.status_code == 401
