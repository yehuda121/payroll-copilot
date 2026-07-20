"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from payroll_copilot.domain.enums import UserRole
from payroll_copilot.infrastructure.persistence.database import engine, get_db_session
from payroll_copilot.presentation.api import dependencies
from payroll_copilot.presentation.api.security import (
    AuthPrincipal,
    get_auth_principal,
    require_accountant,
    require_org_operator,
)
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
def auth_as_org_operator() -> AuthPrincipal:
    """Authenticate integration clients as an org-bound accountant."""
    principal = AuthPrincipal(
        user_id=uuid4(),
        role=UserRole.ACCOUNTANT.value,
        organization_id=uuid4(),
        employee_id=None,
        email="integration-accountant@test.local",
    )

    async def _override() -> AuthPrincipal:
        return principal

    app.dependency_overrides[get_auth_principal] = _override
    app.dependency_overrides[require_org_operator] = _override
    app.dependency_overrides[require_accountant] = _override
    return principal


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
    if engine is None:
        pytest.skip(
            "DATABASE_URL is not set — legacy SQLAlchemy fixtures require Postgres "
            "(optional: docker compose --profile legacy-postgres up -d)."
        )
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
    auth_as_org_operator: AuthPrincipal,
) -> AsyncClient:
    del auth_as_org_operator  # fixture side-effect registers auth overrides
    app.dependency_overrides[dependencies.get_object_storage] = lambda: fake_object_storage
    yield client
    app.dependency_overrides.pop(dependencies.get_object_storage, None)
