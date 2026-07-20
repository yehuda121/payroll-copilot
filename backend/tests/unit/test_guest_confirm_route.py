"""Guest confirm API route — freezes ephemeral extraction for validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from payroll_copilot.application.services.guest_ephemeral_store import (
    GuestEphemeralSession,
    get_guest_ephemeral_store,
    reset_guest_ephemeral_store_for_tests,
)
from payroll_copilot.application.use_cases.extract_guest_payslip import ExtractGuestPayslipUseCase
from payroll_copilot.infrastructure.config.settings import get_settings
from payroll_copilot.presentation.api.dependencies import get_extract_guest_payslip_use_case
from payroll_copilot.presentation.main import app


@pytest.fixture(autouse=True)
def _reset_ephemeral() -> None:
    reset_guest_ephemeral_store_for_tests()
    yield
    reset_guest_ephemeral_store_for_tests()


def _guest_auth_headers() -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "guest",
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "iat": datetime.now(UTC),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _seed_session() -> GuestEphemeralSession:
    document_id = uuid4()
    extraction_id = uuid4()
    session = GuestEphemeralSession(
        document_id=document_id,
        extraction_id=extraction_id,
        content=b"pdf",
        original_filename="slip.pdf",
        mime_type="application/pdf",
        language="he",
        ocr_status="completed",
        parser_status="completed",
        ocr_engine="tesseract",
        parser_model="test",
        raw_text="Net Salary 1000",
        structured_data={"dynamic_entries": []},
        ocr_result={},
        warnings=[],
        error_message=None,
        field_confidences={},
        dynamic_entries=[
            {
                "id": "e1",
                "key": "Net Salary",
                "value": "1000",
                "confidence": 0.9,
                "page": 1,
                "source": "ocr",
                "source_text": "1000",
            }
        ],
        confirmation_status="review_required",
    )
    get_guest_ephemeral_store().save(session)
    return session


@pytest.mark.asyncio
async def test_guest_confirm_route_freezes_session() -> None:
    session = _seed_session()
    use_case = ExtractGuestPayslipUseCase(
        document_repository=MagicMock(),
        extraction_repository=MagicMock(),
        object_storage=MagicMock(),
        organization_bootstrap=MagicMock(),
        ocr_use_case=MagicMock(),
        parse_use_case=MagicMock(),
    )
    app.dependency_overrides[get_extract_guest_payslip_use_case] = lambda: use_case
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/extraction/guest/{session.document_id}/confirm",
                headers=_guest_auth_headers(),
                json={
                    "entries": [
                        {
                            "id": "e1",
                            "key": "Net Salary",
                            "value": "1200",
                            "confidence": 0.95,
                            "page": 1,
                            "source": "user",
                            "source_text": "1200",
                        }
                    ]
                },
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["document_id"] == str(session.document_id)
        assert body["extraction_id"] == str(session.extraction_id)
        assert body["status"] == "confirmed"
        stored = get_guest_ephemeral_store().get(session.document_id)
        assert stored is not None
        assert stored.confirmation_status == "confirmed"
        assert stored.dynamic_entries[0]["value"] == "1200"
    finally:
        app.dependency_overrides.pop(get_extract_guest_payslip_use_case, None)


@pytest.mark.asyncio
async def test_guest_confirm_route_missing_session_returns_404() -> None:
    use_case = ExtractGuestPayslipUseCase(
        document_repository=MagicMock(),
        extraction_repository=MagicMock(),
        object_storage=MagicMock(),
        organization_bootstrap=MagicMock(),
        ocr_use_case=MagicMock(),
        parse_use_case=MagicMock(),
    )
    app.dependency_overrides[get_extract_guest_payslip_use_case] = lambda: use_case
    missing = uuid4()
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/extraction/guest/{missing}/confirm",
                headers=_guest_auth_headers(),
                json={},
            )
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "document_not_found"
    finally:
        app.dependency_overrides.pop(get_extract_guest_payslip_use_case, None)
