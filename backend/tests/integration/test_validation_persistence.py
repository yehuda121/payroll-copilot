"""Integration tests for validation run persistence."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.infrastructure.persistence.models import (
    DocumentModel,
    ValidationFindingModel,
    ValidationRunModel,
)


async def _upload_document(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("payslip.pdf", b"%PDF-1.4 validation", "application/pdf")},
        data={"document_type": "payslip"},
    )
    assert response.status_code == 201
    return response.json()["document_id"]


@pytest.mark.asyncio
async def test_post_validation_with_existing_document_succeeds(
    client_with_storage: AsyncClient,
    db_session: AsyncSession,
    mock_document_processing: None,
) -> None:
    document_id = await _upload_document(client_with_storage)

    response = await client_with_storage.post(
        "/api/v1/validation/run",
        json={"document_id": document_id},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "completed"
    assert "id" in data
    assert data["document_id"] == document_id
    assert "validation_scope" in data
    assert len(data["validation_scope"]) > 0
    assert data["validation_confidence"] is not None
    assert data["confidence_explanation"]
    assert data["extraction_connected"] is False
    assert data["checks_passed_count"] >= 0
    for finding in data["findings"]:
        assert "id" in finding
        assert finding["id"]

    run_count = await db_session.scalar(
        select(func.count())
        .select_from(ValidationRunModel)
        .where(ValidationRunModel.id == UUID(data["id"]))
    )
    assert run_count == 1

    finding_count = await db_session.scalar(
        select(func.count())
        .select_from(ValidationFindingModel)
        .where(ValidationFindingModel.validation_run_id == UUID(data["id"]))
    )
    assert finding_count == len(data["findings"])


@pytest.mark.asyncio
async def test_post_validation_with_unknown_document_returns_404(
    client_with_storage: AsyncClient,
    db_session: AsyncSession,
) -> None:
    unknown_document_id = str(uuid4())
    document_count_before = await db_session.scalar(
        select(func.count()).select_from(DocumentModel)
    )

    response = await client_with_storage.post(
        "/api/v1/validation/run",
        json={"document_id": unknown_document_id},
    )
    assert response.status_code == 404
    assert unknown_document_id in response.json()["detail"]

    document_count_after = await db_session.scalar(
        select(func.count()).select_from(DocumentModel)
    )
    assert document_count_after == document_count_before


@pytest.mark.asyncio
async def test_post_validation_does_not_create_stub_document(
    client_with_storage: AsyncClient,
    db_session: AsyncSession,
) -> None:
    unknown_document_id = str(uuid4())

    await client_with_storage.post(
        "/api/v1/validation/run",
        json={"document_id": unknown_document_id},
    )

    stub_count = await db_session.scalar(
        select(func.count())
        .select_from(DocumentModel)
        .where(DocumentModel.id == UUID(unknown_document_id))
    )
    assert stub_count == 0


@pytest.mark.asyncio
async def test_get_validation_returns_persisted_result(
    client_with_storage: AsyncClient,
    mock_document_processing: None,
) -> None:
    document_id = await _upload_document(client_with_storage)

    post_response = await client_with_storage.post(
        "/api/v1/validation/run",
        json={"document_id": document_id},
    )
    assert post_response.status_code == 202
    created = post_response.json()

    get_response = await client_with_storage.get(f"/api/v1/validation/runs/{created['id']}")
    assert get_response.status_code == 200
    fetched = get_response.json()

    assert fetched["id"] == created["id"]
    assert fetched["status"] == created["status"]
    assert fetched["overall_result"] == created["overall_result"]
    assert len(fetched["findings"]) == len(created["findings"])
    assert fetched["validation_confidence"] == created["validation_confidence"]
    assert fetched["validation_scope"] == created["validation_scope"]


@pytest.mark.asyncio
async def test_get_unknown_validation_run_returns_404(client: AsyncClient) -> None:
    unknown_id = str(uuid4())

    response = await client.get(f"/api/v1/validation/runs/{unknown_id}")
    assert response.status_code == 404
    assert unknown_id in response.json()["detail"]
