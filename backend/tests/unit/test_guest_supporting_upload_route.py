"""Guest supporting-upload API route."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from payroll_copilot.application.services.guest_ephemeral_store import (
    GuestEphemeralSession,
    get_guest_ephemeral_store,
    reset_guest_ephemeral_store_for_tests,
)
from payroll_copilot.presentation.main import app


@pytest.fixture(autouse=True)
def _reset_ephemeral() -> None:
    reset_guest_ephemeral_store_for_tests()
    yield
    reset_guest_ephemeral_store_for_tests()


def _seed_payslip_session() -> GuestEphemeralSession:
    session = GuestEphemeralSession(
        document_id=uuid4(),
        extraction_id=uuid4(),
        content=b"pdf",
        original_filename="slip.pdf",
        mime_type="application/pdf",
        language="he",
        ocr_status="completed",
        parser_status="completed",
        ocr_engine="tesseract",
        parser_model="test",
        raw_text="x",
        structured_data={},
        ocr_result={},
        warnings=[],
        error_message=None,
        field_confidences={},
        dynamic_entries=[],
    )
    get_guest_ephemeral_store().save(session)
    return session


@pytest.mark.asyncio
async def test_guest_supporting_upload_attaches_to_payslip() -> None:
    session = _seed_payslip_session()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/extraction/guest/supporting-upload",
            files={"file": ("id.png", b"fakepng", "image/png")},
            data={
                "document_type": "national_id",
                "payslip_document_id": str(session.document_id),
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_type"] == "national_id"
    assert body["status"] == "uploaded"
    assert body["document_id"]
    stored = get_guest_ephemeral_store().get(session.document_id)
    assert stored is not None
    assert len(stored.supporting_document_ids) == 1


@pytest.mark.asyncio
async def test_guest_supporting_upload_rejects_unknown_type() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/extraction/guest/supporting-upload",
            files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
            data={"document_type": "attendance"},
        )
    assert response.status_code == 422
