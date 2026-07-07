"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.infrastructure.persistence.database import engine, get_db_session
from payroll_copilot.presentation.api import dependencies
from payroll_copilot.presentation.main import app


class FakeObjectStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str]] = []

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        self.uploads.append((key, data, content_type))
        return key


@pytest.fixture
def fake_object_storage() -> FakeObjectStorage:
    return FakeObjectStorage()


@pytest.fixture
def mock_document_processing(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAsyncResult:
        id = "fake-celery-job-id"

    monkeypatch.setattr(
        "payroll_copilot.infrastructure.tasks.celery_app.process_document_ocr.delay",
        lambda document_id: FakeAsyncResult(),
    )
    monkeypatch.setattr(
        "payroll_copilot.infrastructure.tasks.celery_app.import_employee_excel.delay",
        lambda document_id, organization_id: FakeAsyncResult(),
    )


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def client_with_storage(
    client: AsyncClient,
    fake_object_storage: FakeObjectStorage,
) -> AsyncClient:
    app.dependency_overrides[dependencies.get_object_storage] = lambda: fake_object_storage
    yield client
    app.dependency_overrides.pop(dependencies.get_object_storage, None)
