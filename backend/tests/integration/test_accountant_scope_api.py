import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_accountant_employee_list_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/employees")
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_batch_jobs_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/batch/jobs")
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_accountant_chat_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/assistant/accountant/employee/chat",
        json={"employee_number": "E-1", "message": "What was the net salary?"},
    )
    assert response.status_code in {401, 403}
