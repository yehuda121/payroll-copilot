"""Integration tests for document upload persistence."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.infrastructure.persistence.models import DocumentModel


@pytest.mark.asyncio
async def test_upload_creates_document_row(
    client_with_storage: AsyncClient,
    db_session: AsyncSession,
    mock_document_processing: None,
) -> None:
    response = await client_with_storage.post(
        "/api/v1/documents/upload",
        files={"file": ("payslip.pdf", b"%PDF-1.4 test content", "application/pdf")},
        data={"document_type": "payslip"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "uploaded"
    assert data["document_id"]
    assert data["background_status"] == "queued"
    assert data["processing_job_id"] == "fake-celery-job-id"

    row_count = await db_session.scalar(
        select(func.count())
        .select_from(DocumentModel)
        .where(DocumentModel.id == UUID(data["document_id"]))
    )
    assert row_count == 1

    document = await db_session.get(DocumentModel, UUID(data["document_id"]))
    assert document is not None
    assert document.original_filename == "payslip.pdf"
    assert document.file_size_bytes == len(b"%PDF-1.4 test content")
    assert document.mime_type == "application/pdf"
    assert document.storage_key.startswith(f"documents/{data['document_id']}/")


@pytest.mark.asyncio
async def test_get_document_returns_persisted_document(
    client_with_storage: AsyncClient,
    mock_document_processing: None,
) -> None:
    upload_response = await client_with_storage.post(
        "/api/v1/documents/upload",
        files={"file": ("payslip.pdf", b"%PDF-1.4 persisted", "application/pdf")},
        data={"document_type": "payslip"},
    )
    assert upload_response.status_code == 201
    document_id = upload_response.json()["document_id"]

    get_response = await client_with_storage.get(f"/api/v1/documents/{document_id}")
    assert get_response.status_code == 200
    fetched = get_response.json()

    assert fetched["document_id"] == document_id
    assert fetched["document_type"] == "payslip"
    assert fetched["status"] == "uploaded"
    assert fetched["original_filename"] == "payslip.pdf"
    assert fetched["file_size_bytes"] == len(b"%PDF-1.4 persisted")


@pytest.mark.asyncio
async def test_upload_succeeds_when_celery_enqueue_fails(
    client_with_storage: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Broker/Redis being unreachable must not fail a persisted upload."""

    def _raise_connection_error(document_id: str) -> None:
        raise RedisConnectionError(
            "Error 11001 connecting to redis:6379. getaddrinfo failed."
        )

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.tasks.celery_app.process_document_ocr.delay",
        _raise_connection_error,
    )

    response = await client_with_storage.post(
        "/api/v1/documents/upload",
        files={"file": ("payslip.pdf", b"%PDF-1.4 no queue", "application/pdf")},
        data={"document_type": "payslip"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "uploaded"
    assert data["background_status"] == "not_queued"
    assert data["processing_job_id"] is None

    # The document must remain persisted despite the enqueue failure.
    document = await db_session.get(DocumentModel, UUID(data["document_id"]))
    assert document is not None


@pytest.mark.asyncio
async def test_get_unknown_document_returns_404(client_with_storage: AsyncClient) -> None:
    unknown_id = str(uuid4())

    response = await client_with_storage.get(f"/api/v1/documents/{unknown_id}")
    assert response.status_code == 404
    assert unknown_id in response.json()["detail"]
