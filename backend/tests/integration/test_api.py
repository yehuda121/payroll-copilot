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
async def test_validation_run(
    client_with_storage: AsyncClient,
    mock_document_processing: None,
) -> None:
    upload_response = await client_with_storage.post(
        "/api/v1/documents/upload",
        files={"file": ("payslip.pdf", b"%PDF-1.4 validation", "application/pdf")},
        data={"document_type": "payslip"},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["document_id"]

    response = await client_with_storage.post(
        "/api/v1/validation/run",
        json={"document_id": document_id},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "completed"
    assert "findings" in data


@pytest.mark.asyncio
async def test_legal_rules_list(client: AsyncClient) -> None:
    response = await client.get("/api/v1/compliance/legal-rules")
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) > 0
    assert any(r["filename"] == "overtime.yaml" for r in rules)
